"""Fetch a real 3D map for any Swiss zone from the national geo.admin.ch platform.

No SITG / canton dependency, no GDAL/rasterio/PIL: pure standard library.
  - buildings + EGID: GWR  ch.bfs.gebaeude_wohnungs_register  (identify, GeoJSON, LV95)
                      point + area (GAREA) + floors (GASTW) -> extruded square block
  - aerial photo:     swisstopo SWISSIMAGE (WMS GetMap), one JPEG per tile, passed through as-is
  - terrain:          swisstopo swissALTI3D 2 m, read from the ASCII XYZ asset (zip of "E N Z" lines),
                      sampled to a grid; the aerial is draped over the relief and buildings sit on the ground.

fetch(bbox, step, px, tiles) -> {meta, buildings, terrain (bytes), tiles: [(i, j, jpg_bytes)]}
matching the buildings.json / terrain.bin / aerial schema that prototype/map3d.js already reads.

bbox = (xmin, ymin, xmax, ymax) in LV95 (EPSG:2056).
geocode(text) -> [{label, x, y, bbox}] to turn a place name into a zone.
"""
import array
import concurrent.futures
import io
import json
import math
import os
import struct
import time
import urllib.parse
import urllib.request
import zipfile

UA = {"User-Agent": "openedm/1.0 (energiack prototype)"}
IDENTIFY = "https://api3.geo.admin.ch/rest/services/ech/MapServer/identify"
SEARCH = "https://api3.geo.admin.ch/rest/services/ech/SearchServer"
WMS = "https://wms.geo.admin.ch/"
STAC_ALTI = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissalti3d/items"
# Overpass endpoints. Override with OVERPASS_URLS (comma-separated) to use a private/self-hosted instance and dodge the
# public rate limits — e.g. OVERPASS_URLS="https://my-overpass.example.com/api/interpreter". Falls back to public mirrors.
OVERPASS = [u.strip() for u in os.environ.get("OVERPASS_URLS", "").split(",") if u.strip()] or [
    "https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
OSM_BUDGET_PER_TILE_S = 12  # best-effort OSM budget scales with the number of ~1 km sub-boxes (big zones get more time)
OSM_BUDGET_MAX_S = 180      # but never spend more than this on footprints; the rest keep the square shape
OSM_CALL_S = 20            # per-Overpass-call timeout: fail a dead mirror fast, but long enough for a slow-but-live one
OSM_CACHE_DIR = os.environ.get("OSM_CACHE_DIR")   # if set, cache OSM footprints per 1 km cell so re-imports are consistent
GWR_LAYER = "ch.bfs.gebaeude_wohnungs_register"
IDENTIFY_CAP = 200          # the identify endpoint returns at most ~200 features per call
MAX_TILES = 10              # aerial tiles per side (bounds the fetch); large zones are split into several blocks
STOREY_M = 3.0              # metres per floor when GASTW is present
ALTI_RES = 2                # swissALTI3D XYZ grid step (m); one .xyz.zip per 1 km square
ALTI_N = 1000 // ALTI_RES   # samples per side in a 1 km tile (500)
TERRAIN_STEP = 10.0         # target output terrain grid step (m) — relief without a huge grid


def _get(url, binary=False, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else json.loads(data)


def _report(progress, pct, step):
    if progress:
        try:
            progress(int(pct), step)
        except Exception:
            pass


def _lv95_to_wgs(e, n):
    """swisstopo approximate formulas (~1 m), enough for a STAC bbox query. Returns (lon, lat)."""
    y, x = (e - 2600000) / 1e6, (n - 1200000) / 1e6
    lam = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    phi = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return lam * 100 / 36, phi * 100 / 36


def _wgs_to_lv95(lon, lat):
    """swisstopo approximate inverse (~1 m): WGS84 (lon, lat) -> LV95 (E, N). For placing OSM footprints on the map."""
    p = (lat * 3600 - 169028.66) / 10000.0
    l = (lon * 3600 - 26782.5) / 10000.0
    e = 2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p - 44.54 * l ** 3
    n = 1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p - 194.56 * l * l * p + 119.79 * p ** 3
    return e, n


def _pt_in_ring(x, y, ring):
    c = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            c = not c
        j = i
    return c


def _osm_footprints(bbox, progress=None, p0=0, p1=0):
    """Real OpenStreetMap building footprints in bbox, as LV95 rings behind a spatial index.
    Returns a find(E, N) -> ring|None lookup and the footprint count. ([], 0) if OSM is unreachable.
    The Overpass query is TILED (~1 km sub-boxes) so a big zone does not blow the per-query timeout/limit."""
    xmin, ymin, xmax, ymax = bbox
    # Fixed 1 km LV95-aligned cells: each cell is fetched from Overpass once and CACHED to disk, so later imports of the
    # same area reuse it instantly and always get the same real footprints (no more intermittent all-cube fallbacks).
    cells = [(cx * 1000, cy * 1000)
             for cx in range(int(xmin // 1000), int(xmax // 1000) + 1)
             for cy in range(int(ymin // 1000), int(ymax // 1000) + 1)]
    budget = min(OSM_BUDGET_MAX_S, max(90, OSM_BUDGET_PER_TILE_S * len(cells)))
    deadline = time.monotonic() + budget                      # best-effort: stop asking OSM past this, keep what we have

    def fetch_cell(idx_cell):
        idx, (cx, cy) = idx_cell
        cf = os.path.join(OSM_CACHE_DIR, f"{cx}_{cy}.json") if OSM_CACHE_DIR else None
        if cf and os.path.exists(cf):
            try:
                return json.loads(open(cf, encoding="utf-8").read())   # cached LV95 rings for this 1 km cell
            except Exception:
                pass
        if time.monotonic() > deadline:
            return []
        c0 = _lv95_to_wgs(cx, cy)
        c1 = _lv95_to_wgs(cx + 1000, cy + 1000)
        south, west, north, east = min(c0[1], c1[1]), min(c0[0], c1[0]), max(c0[1], c1[1]), max(c0[0], c1[0])
        q = f'[out:json][timeout:25];way["building"]({south:.6f},{west:.6f},{north:.6f},{east:.6f});out geom;'
        elements = None
        for k in range(len(OVERPASS)):                        # start at a per-cell mirror, then fall back
            if time.monotonic() > deadline:
                break
            ep = OVERPASS[(idx + k) % len(OVERPASS)]
            try:
                elements = _get(f"{ep}?data={urllib.parse.quote(q)}", timeout=OSM_CALL_S).get("elements", [])
                break
            except Exception:
                continue
        if elements is None:
            return []                                          # fetch failed -> do NOT cache, so it is retried next time
        rings = [[[round(x, 1), round(y, 1)] for x, y in (_wgs_to_lv95(p["lon"], p["lat"]) for p in w["geometry"])]
                 for w in elements if w.get("geometry") and len(w["geometry"]) >= 4]
        if cf:
            try:
                os.makedirs(OSM_CACHE_DIR, exist_ok=True)
                with open(cf, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(rings))
            except Exception:
                pass
        return rings

    rings = []                                                # (bx0, by0, bx1, by1, ring_lv95)
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(cells))) as ex:
        for cell_rings in ex.map(fetch_cell, list(enumerate(cells))):
            done += 1
            _report(progress, p0 + (p1 - p0) * done / len(cells), "footprints")
            for ring in cell_rings or []:
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                rings.append((min(xs), min(ys), max(xs), max(ys), ring))
    CELL = 40.0                                               # grid index so point lookup is ~O(1)
    grid = {}
    for i, (bx0, by0, bx1, by1, _) in enumerate(rings):
        for cx in range(int(bx0 // CELL), int(bx1 // CELL) + 1):
            for cy in range(int(by0 // CELL), int(by1 // CELL) + 1):
                grid.setdefault((cx, cy), []).append(i)

    def find(e, n):
        for i in grid.get((int(e // CELL), int(n // CELL)), ()):
            bx0, by0, bx1, by1, ring = rings[i]
            if bx0 <= e <= bx1 and by0 <= n <= by1 and _pt_in_ring(e, n, ring):
                return ring
        return None

    return find, len(rings)


def _alti_tiles(bbox, progress=None, p0=0, p1=0):
    """Download the swissALTI3D 2 m XYZ tiles covering bbox -> {(tileE,tileN): array('f', 500*500)} (NaN = gap)."""
    xmin, ymin, xmax, ymax = bbox
    lo0, la0 = _lv95_to_wgs(xmin - 50, ymin - 50)
    lo1, la1 = _lv95_to_wgs(xmax + 50, ymax + 50)
    items, url = [], f"{STAC_ALTI}?bbox={lo0:.5f},{la0:.5f},{lo1:.5f},{la1:.5f}&limit=100"
    while url:
        d = _get(url)
        items += d.get("features", [])
        url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
    newest = {}                                           # keep the newest asset per 1 km square
    for it in items:
        href = next((a["href"] for k, a in it["assets"].items()
                     if k.endswith(f"_{ALTI_RES}_2056_5728.xyz.zip")), None)
        if not href:
            continue
        sq = it["id"].rsplit("_", 1)[-1]
        if sq not in newest or it["id"] > newest[sq][0]:
            newest[sq] = (it["id"], href)
    nan = float("nan")
    hrefs = [href for _, href in newest.values()]
    total = len(hrefs) or 1

    def load_tile(href):                                      # download + parse one 1 km XYZ tile -> (key, grid)
        for attempt in range(3):                              # retry: a dropped terrain tile leaves a hole that buries buildings
            try:
                zf = zipfile.ZipFile(io.BytesIO(_get(href, binary=True)))
                with zf.open(zf.namelist()[0]) as f:
                    g, key = None, None
                    for line in f:
                        parts = line.split()
                        if len(parts) != 3 or parts[0] in (b"X", b"x"):
                            continue
                        e = int(float(parts[0])); n = int(float(parts[1])); z = float(parts[2])
                        te, tn = (e // 1000) * 1000, (n // 1000) * 1000
                        if g is None:
                            key = (te, tn); g = array.array("f", [nan]) * (ALTI_N * ALTI_N)
                        col = min(max((e - te) // ALTI_RES, 0), ALTI_N - 1)
                        row = min(max((n - tn) // ALTI_RES, 0), ALTI_N - 1)
                        g[row * ALTI_N + col] = z
                    return (key, g) if g is not None else None
            except Exception:
                if attempt == 2:
                    return None
                time.sleep(0.6 * (attempt + 1))
        return None

    grids, done = {}, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, total)) as ex:
        for res in ex.map(load_tile, hrefs):
            done += 1
            _report(progress, p0 + (p1 - p0) * done / total, "terrain")
            if res:
                grids[res[0]] = res[1]
    return grids


def _terrain(bbox, tiles, progress=None, p0=0, p1=0):
    """Real swissALTI3D terrain for bbox. Returns (terrain_bytes, nx, ny, step, zmin, ground(E,N))."""
    xmin, ymin, xmax, ymax = bbox
    W, H = xmax - xmin, ymax - ymin
    grids = _alti_tiles(bbox, progress, p0, p1)

    def sample(e, n):                                     # nearest 2 m post, with a tiny spiral to fill gaps
        te, tn = (int(e) // 1000) * 1000, (int(n) // 1000) * 1000
        g = grids.get((te, tn))
        if g is None:
            return None
        c0 = min(max((int(e) - te) // ALTI_RES, 0), ALTI_N - 1)
        r0 = min(max((int(n) - tn) // ALTI_RES, 0), ALTI_N - 1)
        for rad in range(0, 4):
            for dr in range(-rad, rad + 1):
                for dc in range(-rad, rad + 1):
                    r, c = r0 + dr, c0 + dc
                    if 0 <= r < ALTI_N and 0 <= c < ALTI_N:
                        v = g[r * ALTI_N + c]
                        if v == v:                        # not NaN
                            return v
        return None

    def flat():                                           # fetch failed everywhere -> flat fallback
        nx = ny = tiles + 1
        return struct.pack(f"<{nx * ny}h", *([0] * (nx * ny))), nx, ny, W / (nx - 1), 0.0, (lambda e, n: 0.0)

    if not grids:
        return flat()

    cells = max(tiles, round(max(W, H) / TERRAIN_STEP))   # divisible by tiles -> integer plane segments per tile
    cells = math.ceil(cells / tiles) * tiles
    nx = ny = cells + 1
    step = W / (nx - 1)
    raw = []                                              # row 0 = north (N = ymax), to match make_map / terrain.bin
    for r in range(ny):
        n = ymax - r * step
        for c in range(nx):
            raw.append(sample(xmin + c * step, n))        # None where no terrain tile covers this post
    known = [v for v in raw if v is not None]
    if not known:
        return flat()
    # Fill holes (a dropped XYZ tile) by spreading neighbouring heights inward, so the surface stays smooth instead of
    # getting a cliff — and crucially so ground() below matches it, otherwise buildings would sink under a raised patch.
    grid = _fill_gaps(raw, nx, ny, sum(known) / len(known))
    zmin = math.floor(min(grid))

    def ground(e, n):                                     # bilinear on the FINAL grid: a building always sits on the drawn relief
        fc = min(max((e - xmin) / step, 0.0), nx - 1.0)
        fr = min(max((ymax - n) / step, 0.0), ny - 1.0)
        c0, r0 = int(fc), int(fr)
        c1, r1 = min(c0 + 1, nx - 1), min(r0 + 1, ny - 1)
        tx, ty = fc - c0, fr - r0
        top = grid[r0 * nx + c0] * (1 - tx) + grid[r0 * nx + c1] * tx
        bot = grid[r1 * nx + c0] * (1 - tx) + grid[r1 * nx + c1] * tx
        return top * (1 - ty) + bot * ty - zmin

    terrain = struct.pack(f"<{nx * ny}h", *[int(round((v - zmin) * 10)) for v in grid])
    return terrain, nx, ny, step, float(zmin), ground


def _fill_gaps(raw, nx, ny, fillv):
    """Replace None cells (holes where no terrain tile was available) by iteratively averaging known 4-neighbours, so a
    missing 1 km tile is filled by its surroundings spreading in rather than left as a cliff. Any cell still unreached
    (a whole-corner gap) falls back to the mean. Returns a list with no None."""
    grid = list(raw)
    missing = [i for i, v in enumerate(grid) if v is None]
    for _ in range(80):                                   # 80 passes fill a gap ~800 m wide from each edge (a 1 km hole closes)
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
        if len(still) == len(missing):                    # no progress this pass -> fill the rest with the mean
            break
        missing = [idx for idx, _ in still]
    for idx in missing:
        grid[idx] = fillv
    return grid


def geocode(text, limit=6):
    """Swiss place name -> candidate zones (LV95 centre + bbox)."""
    q = urllib.parse.urlencode({"searchText": text, "type": "locations", "sr": "2056", "limit": limit})
    out = []
    for r in _get(f"{SEARCH}?{q}").get("results", []):
        a = r.get("attrs", {})
        # geom_st_box2d: "BOX(xmin ymin,xmax ymax)"
        bb = None
        box = a.get("geom_st_box2d", "")
        if box.startswith("BOX("):
            try:
                lo, hi = box[4:-1].split(",")
                xmin, ymin = map(float, lo.split())
                xmax, ymax = map(float, hi.split())
                bb = [xmin, ymin, xmax, ymax]
            except ValueError:
                bb = None
        label = (a.get("label", "") or "").replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        out.append({"label": label.strip(), "x": a.get("y"), "y": a.get("x"), "bbox": bb, "crs": "EPSG:2056"})
    return out


# Lambert-93 (EPSG:2154) forward projection — so France zones use the same metre-based bbox logic as LV95.
def _wgs_to_lambert93(lon, lat):
    a, f = 6378137.0, 1 / 298.257222101
    e = math.sqrt(2 * f - f * f)
    lon0, lat0, lat1, lat2 = map(math.radians, (3.0, 46.5, 44.0, 49.0))
    x0, y0 = 700000.0, 6600000.0
    def mm(p): return math.cos(p) / math.sqrt(1 - e * e * math.sin(p) ** 2)
    def tt(p): return math.tan(math.pi / 4 - p / 2) / ((1 - e * math.sin(p)) / (1 + e * math.sin(p))) ** (e / 2)
    n = (math.log(mm(lat1)) - math.log(mm(lat2))) / (math.log(tt(lat1)) - math.log(tt(lat2)))
    fF = mm(lat1) / (n * tt(lat1) ** n)
    r0 = a * fF * tt(lat0) ** n
    lo, la = math.radians(lon), math.radians(lat)
    r = a * fF * tt(la) ** n
    theta = n * (lo - lon0)
    return x0 + r * math.sin(theta), y0 + r0 - r * math.cos(theta)


BAN = "https://api-adresse.data.gouv.fr/search/"


def geocode_fr(text, limit=6):
    """French place name -> candidate zones (Lambert-93 centre + bbox), via the BAN (adresse.data.gouv.fr)."""
    q = urllib.parse.urlencode({"q": text, "limit": limit})
    out = []
    for feat in _get(f"{BAN}?{q}").get("features", []):
        g = feat.get("geometry", {})
        p = feat.get("properties", {})
        if g.get("type") != "Point":
            continue
        e, n = _wgs_to_lambert93(g["coordinates"][0], g["coordinates"][1])
        out.append({"label": p.get("label", "").strip(), "x": round(e, 1), "y": round(n, 1), "bbox": None, "crs": "EPSG:2154"})
    return out


def _tile_boxes(xmin, ymin, xmax, ymax, n):
    """Split a bbox into n*n sub-boxes (to stay under the identify feature cap)."""
    dx, dy = (xmax - xmin) / n, (ymax - ymin) / n
    for r in range(n):
        for c in range(n):
            yield (xmin + c * dx, ymin + r * dy, xmin + (c + 1) * dx, ymin + (r + 1) * dy)


def _identify_box(bx):
    """Raw GWR identify features intersecting one envelope (up to the ~200 cap). [] on error."""
    geom = ",".join(f"{v:.1f}" for v in bx)
    q = urllib.parse.urlencode({
        "geometryType": "esriGeometryEnvelope", "geometry": geom,
        "layers": f"all:{GWR_LAYER}", "sr": "2056",
        "geometryFormat": "geojson", "returnGeometry": "true",
        "imageDisplay": "100,100,96", "mapExtent": geom, "tolerance": "0",
    })
    try:
        res = _get(f"{IDENTIFY}?{q}", timeout=40)
        return res.get("results") or res.get("features") or []
    except Exception:
        return []


def _buildings(bbox, progress=None, p0=0, p1=0):
    """All GWR buildings in bbox, de-duplicated by EGID. The identify endpoint returns at most ~200 features per call,
    so the bbox is tiled into ~300 m sub-boxes AND any sub-box that still comes back full is recursively split into four
    — otherwise dense city blocks silently lose every building past the 200th. Sub-boxes are fetched in parallel."""
    xmin, ymin, xmax, ymax = bbox
    span = max(xmax - xmin, ymax - ymin)
    sub = max(1, math.ceil(span / 300))          # ~300 m sub-boxes: usually under the cap, split further where not
    boxes = list(_tile_boxes(xmin, ymin, xmax, ymax, sub))

    seen, rows = set(), []

    def keep(feats):
        for f in feats:
            p = f.get("properties", {}) or f.get("attributes", {})
            egid = str(p.get("egid") or "").strip()
            if not egid or egid in seen:
                continue
            seen.add(egid)
            e, n = p.get("gkode"), p.get("gkodn")       # LV95 easting/northing of the building
            if e is None or n is None:
                g = f.get("geometry", {})
                if g.get("type") == "Point":
                    e, n = g["coordinates"]
            if e is None or n is None:
                continue
            rows.append({
                "egid": egid, "e": float(e), "n": float(n),
                "garea": p.get("garea"), "gastw": p.get("gastw"),
                "year": p.get("gbauj") or None,
                "addr": (p.get("strname_deinr") or p.get("doffadr") or "").strip() or None,
            })

    done, total = 0, [len(boxes)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        pending = {ex.submit(_identify_box, bx): bx for bx in boxes}
        while pending:
            fut = next(concurrent.futures.as_completed(pending))
            bx = pending.pop(fut)
            feats = fut.result()
            if len(feats) >= IDENTIFY_CAP and (bx[2] - bx[0]) > 40:   # full box -> too dense, split into quarters and retry
                x0, y0, x1, y1 = bx; mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                quads = [(x0, y0, mx, my), (mx, y0, x1, my), (x0, my, mx, y1), (mx, my, x1, y1)]
                total[0] += len(quads)
                for q in quads:
                    pending[ex.submit(_identify_box, q)] = q
            else:
                keep(feats)
            done += 1
            _report(progress, p0 + (p1 - p0) * min(done / total[0], 1.0), "buildings")
    return rows


def _aerial(bbox, tiles, px, progress=None, p0=0, p1=0):
    """One SWISSIMAGE JPEG per tile, passed through as-is. Tiles are fetched in parallel. Returns (tiles[], tile_px)."""
    xmin, ymin, xmax, ymax = bbox
    W, H = xmax - xmin, ymax - ymin
    tpx = max(256, min(int(round(max(W, H) / tiles / px)), 1024))
    ntiles = tiles * tiles
    ij = [(i, j) for i in range(tiles) for j in range(tiles)]  # i = column west->east, j = row north->south

    def fetch_tile(ij_):
        i, j = ij_
        x0, x1 = xmin + i * W / tiles, xmin + (i + 1) * W / tiles
        y1, y0 = ymax - j * H / tiles, ymax - (j + 1) * H / tiles
        q = urllib.parse.urlencode({
            "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
            "LAYERS": "ch.swisstopo.swissimage", "STYLES": "", "CRS": "EPSG:2056",
            "BBOX": f"{x0},{y0},{x1},{y1}", "WIDTH": str(tpx), "HEIGHT": str(tpx), "FORMAT": "image/jpeg",
        })
        for attempt in range(4):                              # the WMS intermittently 400s on a tile; retry so it is not left blank
            try:
                data = _get(f"{WMS}?{q}", binary=True)
                if len(data) > 2000:                          # a real JPEG, not a WMS error page / blank body
                    return (i, j, data)
            except Exception:
                pass
            time.sleep(0.5 * (attempt + 1))
        return (i, j, b"")

    out, done = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, ntiles)) as ex:
        for tile in ex.map(fetch_tile, ij):
            done += 1
            _report(progress, p0 + (p1 - p0) * done / ntiles, "aerial")
            out.append(tile)
    return out, tpx


def fetch(bbox, step=16, px=1.0, tiles=1, name=None, progress=None, osm=True):
    """Build the map for a zone. Returns meta, buildings (map-local), flat terrain bytes, aerial tiles.
    progress(pct:int, step:str) is called through the (slow) network stages, 2..96 %.
    osm=True: replace the square footprint with the real OpenStreetMap footprint where the GWR point sits in one."""
    tiles = max(1, min(tiles, MAX_TILES))
    xmin, ymin, xmax, ymax = (float(v) for v in bbox)
    W, H = xmax - xmin, ymax - ymin
    _report(progress, 2, "start")

    # real swissALTI3D terrain (relief); buildings then sit on the ground at their base elevation
    terrain, nx, ny, step, zmin, ground = _terrain((xmin, ymin, xmax, ymax), tiles, progress, 4, 40)

    # GWR gives EGID + location + floors; OSM (optional) gives the real footprint shape
    raw = _buildings((xmin, ymin, xmax, ymax), progress, 38, 55)
    osm_find, osm_n = (None, 0)
    if osm:
        osm_find, osm_n = _osm_footprints((xmin, ymin, xmax, ymax), progress, 55, 72)
    _report(progress, 73, "buildings")
    buildings, n_osm = [], 0
    for b in raw:
        x, y = b["e"] - xmin, b["n"] - ymin              # map-local (origin at the SW corner)
        if not (0 <= x <= W and 0 <= y <= H):
            continue
        floors = b["gastw"] if isinstance(b["gastw"], (int, float)) and b["gastw"] else 3
        height = max(3.0, float(floors) * STOREY_M)
        shape = osm_find(b["e"], b["n"]) if osm_find else None
        if shape:                                        # real OSM footprint -> map-local ring
            ring = [[round(px - xmin, 1), round(py - ymin, 1)] for px, py in shape]
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            n_osm += 1
        else:                                            # fall back to a square sized from GWR area
            area = b["garea"] if isinstance(b["garea"], (int, float)) and b["garea"] else 80.0
            hs = max(4.0, math.sqrt(area)) / 2
            ring = [[round(x - hs, 1), round(y - hs, 1)], [round(x + hs, 1), round(y - hs, 1)],
                    [round(x + hs, 1), round(y + hs, 1)], [round(x - hs, 1), round(y + hs, 1)],
                    [round(x - hs, 1), round(y - hs, 1)]]
        buildings.append({
            "egid": b["egid"], "rings": [ring], "h": round(height, 1), "z": round(ground(b["e"], b["n"]), 1),
            "use": None, "year": b["year"], "levels": floors, "addr": b["addr"],
        })

    tiles_out, tpx = _aerial((xmin, ymin, xmax, ymax), tiles, px, progress, 74, 96)
    _report(progress, 96, "assemble")
    flat = all(v == 0 for v in struct.unpack(f"<{nx * ny}h", terrain))

    meta = {
        "kind": "imported", "area": name or f"{xmin:.0f},{ymin:.0f}",
        "crs": "EPSG:2056", "origin": [xmin, ymin], "size": [round(W), round(H)],
        "zmin": zmin, "terrain": {"nx": nx, "ny": ny, "step": step, "scale": 0.1},
        "tiles": tiles, "labels": [],
        "sources": {"buildings": "GWR ch.bfs.gebaeude_wohnungs_register (swisstopo/BFS)"
                    + (f" + OpenStreetMap footprints ({n_osm}/{len(buildings)}, ODbL)" if osm and osm_n else ""),
                    "aerial": "swisstopo SWISSIMAGE (WMS)",
                    "terrain": "flat" if flat else "swisstopo swissALTI3D (2 m, XYZ)"},
    }
    return {"meta": meta, "buildings": buildings, "terrain": terrain, "tiles": tiles_out}


if __name__ == "__main__":
    import sys
    box = tuple(float(v) for v in sys.argv[1].split(",")) if len(sys.argv) > 1 else (2500000, 1118000, 2500600, 1118600)
    r = fetch(box, tiles=1)
    print("buildings:", len(r["buildings"]), "| with egid:", sum(1 for b in r["buildings"] if b["egid"]))
    print("terrain bytes:", len(r["terrain"]), "| tiles:", [(i, j, len(j_)) for i, j, j_ in r["tiles"]])
    print("meta:", json.dumps(r["meta"]))
