"""Fetch a 3D map for a French zone from the IGN Géoplateforme (data.geopf.fr). Pure standard library.

Mirrors tools/fetch_swiss_map.py's fetch() and output schema, so prototype/map3d.js reads it the same way.
Coordinates are Lambert-93 (EPSG:2154), the French national projection.
  - buildings + official id: BD TOPO V3 'batiment' (WFS GetFeature) -> real footprint + hauteur + floors +
    ground altitude + the RNB id (identifiants_rnb); the RNB id goes in the same field as the Swiss EGID.
  - aerial photo:            BD ORTHO (WMS GetMap), one JPEG per tile.
  - terrain:                 RGE ALTI, sampled to a grid via the elevation REST API (WGS points, batched).

fetch(bbox, step, px, tiles, name, progress, osm) -> {meta, buildings, terrain (bytes), tiles: [(i, j, jpg)]}
bbox = (xmin, ymin, xmax, ymax) in Lambert-93 (EPSG:2154).
"""
import json
import math
import struct
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "openedm/1.0 (energiack prototype)"}
WFS = "https://data.geopf.fr/wfs/ows"
WMS = "https://data.geopf.fr/wms-r/wms"
ALTI = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
BDTOPO = "BDTOPO_V3:batiment"
ORTHO = "HR.ORTHOIMAGERY.ORTHOPHOTOS"
STOREY_M = 3.0
MAX_TILES = 10
TERRAIN_STEP = 12.0        # target output terrain grid step (m)
MAX_CELLS = 160            # cap the terrain grid per side (bounds the number of elevation points)
WFS_PAGE = 1000


def _get(url, data=None, binary=False, timeout=90):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw if binary else json.loads(raw)


def _report(progress, pct, step):
    if progress:
        try:
            progress(int(pct), step)
        except Exception:
            pass


def _l93_to_wgs(x, y):
    """Inverse Lambert-93 (EPSG:2154) -> WGS84 (lon, lat) in degrees. For the elevation API, which takes lon/lat."""
    a, f = 6378137.0, 1 / 298.257222101
    e = math.sqrt(2 * f - f * f)
    lon0, lat0, lat1, lat2 = map(math.radians, (3.0, 46.5, 44.0, 49.0))
    x0, y0 = 700000.0, 6600000.0

    def mm(p):
        return math.cos(p) / math.sqrt(1 - e * e * math.sin(p) ** 2)

    def tt(p):
        return math.tan(math.pi / 4 - p / 2) / ((1 - e * math.sin(p)) / (1 + e * math.sin(p))) ** (e / 2)

    n = (math.log(mm(lat1)) - math.log(mm(lat2))) / (math.log(tt(lat1)) - math.log(tt(lat2)))
    fF = mm(lat1) / (n * tt(lat1) ** n)
    r0 = a * fF * tt(lat0) ** n
    dx, dy = x - x0, r0 - (y - y0)
    rho = math.copysign(math.hypot(dx, dy), n)
    theta = math.atan2(dx, dy)
    lon = lon0 + theta / n
    t = (rho / (a * fF)) ** (1 / n)
    lat = math.pi / 2 - 2 * math.atan(t)
    for _ in range(6):
        lat = math.pi / 2 - 2 * math.atan(t * ((1 - e * math.sin(lat)) / (1 + e * math.sin(lat))) ** (e / 2))
    return math.degrees(lon), math.degrees(lat)


def _buildings(bbox, progress=None, p0=0, p1=0):
    """BD TOPO V3 buildings in bbox (Lambert-93), paged. Each: footprint ring + height + floors + ground z + RNB id."""
    xmin, ymin, xmax, ymax = bbox
    rows, start = [], 0
    while True:
        _report(progress, p0 + (p1 - p0) * min(1.0, start / 3000.0), "buildings")
        q = urllib.parse.urlencode({
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": BDTOPO,
            "SRSNAME": "EPSG:2154", "COUNT": WFS_PAGE, "STARTINDEX": start,
            "OUTPUTFORMAT": "application/json", "BBOX": f"{xmin},{ymin},{xmax},{ymax},EPSG:2154"})
        try:
            d = _get(f"{WFS}?{q}")
        except Exception:
            break
        feats = d.get("features", [])
        for f in feats:
            p = f.get("properties", {})
            g = f.get("geometry", {})
            if g.get("type") == "MultiPolygon":
                ring = g["coordinates"][0][0]
            elif g.get("type") == "Polygon":
                ring = g["coordinates"][0]
            else:
                continue
            rnb = (p.get("identifiants_rnb") or "").strip()
            rows.append({
                "id": (rnb.split("/")[0] if rnb else (p.get("cleabs") or "")),
                "ring": ring, "h": p.get("hauteur"), "etages": p.get("nombre_d_etages"),
                "logements": p.get("nombre_de_logements"), "zsol": p.get("altitude_minimale_sol"),
                "usage": p.get("usage_1"),
            })
        start += len(feats)
        if len(feats) < WFS_PAGE or start >= (d.get("numberMatched") or 0):
            break
    return rows


def _terrain(bbox, tiles, progress=None, p0=0, p1=0):
    """RGE ALTI terrain for bbox. Returns (terrain_bytes, nx, ny, step, zmin). Grid row 0 = north."""
    xmin, ymin, xmax, ymax = bbox
    W, H = xmax - xmin, ymax - ymin
    cells = max(tiles, min(MAX_CELLS, round(max(W, H) / TERRAIN_STEP)))
    cells = math.ceil(cells / tiles) * tiles                 # divisible by tiles -> integer plane segments per tile
    nx = ny = cells + 1
    step = W / (nx - 1)
    pts = []                                                 # (E, N) row-major, row 0 = north
    for r in range(ny):
        n = ymax - r * step
        for c in range(nx):
            pts.append((xmin + c * step, n))
    elev = [None] * len(pts)
    B = 150                                                  # points per GET call (the elevation API rejects POST)
    for i in range(0, len(pts), B):
        _report(progress, p0 + (p1 - p0) * i / len(pts), "terrain")
        chunk = pts[i:i + B]
        lons, lats = [], []
        for e, n in chunk:
            lo, la = _l93_to_wgs(e, n)
            lons.append(f"{lo:.6f}")
            lats.append(f"{la:.6f}")
        q = "lon=" + "|".join(lons) + "&lat=" + "|".join(lats) + "&resource=ign_rge_alti_wld&zonly=true"
        for attempt in range(3):                             # retry: a dropped batch leaves a terrain hole that distorts the drape
            try:
                vals = _get(f"{ALTI}?{q}").get("elevations", [])
                for j, v in enumerate(vals):
                    if isinstance(v, (int, float)) and v > -1000:
                        elev[i + j] = float(v)
                break
            except Exception:
                if attempt < 2:
                    time.sleep(0.6 * (attempt + 1))
    valid = [v for v in elev if v is not None]
    zmin = math.floor(min(valid)) if valid else 0.0
    # Fill holes (a failed elevation batch) by spreading neighbouring heights in, so the surface stays smooth rather than
    # stepping to a stale value — otherwise the orthophoto draped over it looks torn.
    grid = _fill_gaps(elev, nx, ny, (sum(valid) / len(valid)) if valid else zmin)
    terrain = struct.pack(f"<{nx * ny}h", *[int(round((v - zmin) * 10)) for v in grid])
    return terrain, nx, ny, step, float(zmin)


def _fill_gaps(raw, nx, ny, fillv):
    """Replace None cells (elevation holes) by iteratively averaging known 4-neighbours; anything unreached -> mean."""
    grid = list(raw)
    missing = [i for i, v in enumerate(grid) if v is None]
    for _ in range(80):
        if not missing:
            break
        updates, still = [], []
        for idx in missing:
            r, c = divmod(idx, nx)
            acc = k = 0
            for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if 0 <= rr < ny and 0 <= cc < nx:
                    v = grid[rr * nx + cc]
                    if v is not None:
                        acc += v; k += 1
            (updates if k else still).append((idx, acc / k) if k else (idx, None))
        for idx, v in updates:
            grid[idx] = v
        if len(still) == len(missing):
            break
        missing = [idx for idx, _ in still]
    for idx in missing:
        grid[idx] = fillv
    return grid


def _aerial(bbox, tiles, px, progress=None, p0=0, p1=0):
    """BD ORTHO JPEG per tile (EPSG:2154). j = north -> south, like fetch_swiss_map (so it matches the terrain)."""
    xmin, ymin, xmax, ymax = bbox
    W, H = xmax - xmin, ymax - ymin
    tpx = max(256, min(int(round(max(W, H) / tiles / px)), 1024))
    out, done, ntiles = [], 0, tiles * tiles
    for i in range(tiles):
        for j in range(tiles):
            _report(progress, p0 + (p1 - p0) * done / ntiles, "aerial")
            done += 1
            x0, x1 = xmin + i * W / tiles, xmin + (i + 1) * W / tiles
            y1, y0 = ymax - j * H / tiles, ymax - (j + 1) * H / tiles
            q = urllib.parse.urlencode({
                "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": ORTHO, "STYLES": "",
                "CRS": "EPSG:2154", "BBOX": f"{x0},{y0},{x1},{y1}",
                "WIDTH": str(tpx), "HEIGHT": str(tpx), "FORMAT": "image/jpeg"})
            jpg = b""
            for attempt in range(4):                          # IGN WMS intermittently 400s on a tile; retry so it is not left blank
                try:
                    data = _get(f"{WMS}?{q}", binary=True)
                    if len(data) > 2000:                      # a real JPEG, not a WMS error page / blank body
                        jpg = data
                        break
                except Exception:
                    pass
                time.sleep(0.5 * (attempt + 1))
            out.append((i, j, jpg))
    return out, tpx


def fetch(bbox, step=16, px=1.0, tiles=1, name=None, progress=None, osm=True):
    """Build the map for a French zone. Same return schema as fetch_swiss_map.fetch(). osm is ignored (BD TOPO already
    gives real footprints). The RNB id is written to the building 'egid' field, so EGID/RNB matching is identical."""
    tiles = max(1, min(tiles, MAX_TILES))
    xmin, ymin, xmax, ymax = (float(v) for v in bbox)
    W, H = xmax - xmin, ymax - ymin
    _report(progress, 2, "start")

    terrain, nx, ny, tstep, zmin = _terrain((xmin, ymin, xmax, ymax), tiles, progress, 4, 44)
    raw = _buildings((xmin, ymin, xmax, ymax), progress, 44, 74)
    _report(progress, 75, "buildings")

    buildings, n_rnb = [], 0
    for b in raw:
        ring = [[round(pt[0] - xmin, 1), round(pt[1] - ymin, 1)] for pt in b["ring"]]   # BD TOPO rings are 3D (x,y,z)
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        h = b["h"] if isinstance(b["h"], (int, float)) and b["h"] else max(3.0, (b["etages"] or 2) * STOREY_M)
        z = round(b["zsol"] - zmin, 1) if isinstance(b["zsol"], (int, float)) else 0.0
        if b["id"]:
            n_rnb += 1
        buildings.append({
            "egid": str(b["id"] or ""), "rings": [ring], "h": round(float(h), 1), "z": z,
            "use": b["usage"], "year": None, "levels": b["etages"], "addr": None,
        })

    tiles_out, tpx = _aerial((xmin, ymin, xmax, ymax), tiles, px, progress, 75, 96)
    _report(progress, 96, "assemble")
    meta = {
        "kind": "imported", "area": name or f"{xmin:.0f},{ymin:.0f}", "crs": "EPSG:2154",
        "origin": [xmin, ymin], "size": [round(W), round(H)], "zmin": zmin,
        "terrain": {"nx": nx, "ny": ny, "step": tstep, "scale": 0.1}, "tiles": tiles, "labels": [],
        "sources": {"buildings": f"IGN BD TOPO V3 batiment + RNB ({n_rnb}/{len(buildings)} RNB), geoservices IGN",
                    "aerial": "IGN BD ORTHO (WMS)", "terrain": "IGN RGE ALTI"},
    }
    return {"meta": meta, "buildings": buildings, "terrain": terrain, "tiles": tiles_out}


def geocode(text, limit=6):
    """France place name -> candidate zones (Lambert-93 centre). Thin wrapper kept here for symmetry with the Swiss module."""
    import fetch_swiss_map as ch
    return ch.geocode_fr(text, limit)


if __name__ == "__main__":
    import sys
    box = tuple(float(v) for v in sys.argv[1].split(",")) if len(sys.argv) > 1 else (950600, 6570700, 951100, 6571200)
    r = fetch(box, tiles=1, name="FR test")
    print("buildings:", len(r["buildings"]), "| with RNB/id:", sum(1 for b in r["buildings"] if b["egid"]))
    print("source:", r["meta"]["sources"]["buildings"])
    print("terrain bytes:", len(r["terrain"]), "| tiles:", [(i, j, len(j_)) for i, j, j_ in r["tiles"]])
