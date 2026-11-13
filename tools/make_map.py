"""Build the 3D map data for central Geneva -> <out>/ (default prototype/map/).

Real public data, fetched once (cached in data/cache/) and cut to the area:
  - building footprints + height + use + year: SITG CAD_BATIMENT_HORSOL           (Etat de Genève, open data)
  - heat index IDC, energy carriers, consumption: SITG SCANE_INDICE_MOYENNES_3_ANS (OCEN, open data)
  - boilers (fuel, year, power):                  SITG SCANE_CHAUDIERE
  - solar potential per building:                 SITG OCEN_SOLAIRE_PV_BATIMENT
  - terrain: swisstopo swissALTI3D 2 m (STAC)     - aerial photo: swisstopo SWISSIMAGE (WMS), tiled
  - place labels: swisstopo search API
Simulated (flagged "sim"): electricity and water per building. Not public; Quanthome provides them per EGID.

Run: .venv/bin/python tools/make_map.py [--box xmin,ymin,xmax,ymax] [--out DIR] [--step 8] [--px 0.8] [--tiles 2]
Outputs: buildings.json, terrain.bin (Int16 dm), aerial_<i>_<j>.jpg
"""
import argparse
import hashlib
import io
import json
import math
import random
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--box", default="2497800,1115800,2502200,1119640")
ap.add_argument("--out", default=str(ROOT / "prototype" / "map"))
ap.add_argument("--step", type=int, default=8, help="terrain grid, metres")
ap.add_argument("--px", type=float, default=0.8, help="aerial metres per pixel")
ap.add_argument("--tiles", type=int, default=2, help="aerial/terrain tiles per side")
A = ap.parse_args()
XMIN, YMIN, XMAX, YMAX = map(int, A.box.split(","))
STEP, NT = A.step, A.tiles
assert (XMAX - XMIN) % (STEP * NT) == 0 and (YMAX - YMIN) % (STEP * NT) == 0, "box must divide into step*tiles"
OUT = Path(A.out); OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("aerial*.jpg"):
    old.unlink()
CACHE = ROOT / "data" / "cache"; CACHE.mkdir(parents=True, exist_ok=True)
SITG = "https://vector.sitg.ge.ch/arcgis/rest/services/Hosted/{}/FeatureServer/0/query"
UA = {"User-Agent": "energiack-prototype/1.0"}
T0 = time.time()


def get(url, binary=False):
    f = CACHE / hashlib.sha1(url.encode()).hexdigest()
    if not f.exists():
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
            f.write_bytes(r.read())
    data = f.read_bytes()
    return data if binary else json.loads(data)


def lv95_to_wgs(e, n):
    """swisstopo approximate formulas (~1 m), enough for a search box."""
    y, x = (e - 2600000) / 1e6, (n - 1200000) / 1e6
    lam = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    phi = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return lam * 100 / 36, phi * 100 / 36


def sitg(layer, fields, geometry=True, where="1=1"):
    env = json.dumps({"xmin": XMIN, "ymin": YMIN, "xmax": XMAX, "ymax": YMAX, "spatialReference": {"wkid": 2056}})
    out, offset = [], 0
    while True:
        q = {"geometry": env, "geometryType": "esriGeometryEnvelope", "spatialRel": "esriSpatialRelIntersects",
             "where": where, "outFields": fields, "returnGeometry": str(geometry).lower(), "outSR": 2056, "f": "json",
             "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": "objectid"}
        d = get(SITG.format(layer) + "?" + urllib.parse.urlencode(q))
        assert "error" not in d, d
        feats = d.get("features", [])
        out += feats
        if not d.get("exceededTransferLimit") and len(feats) < 2000:
            return out
        offset += len(feats)


# ---------------------------------------------------------------- terrain (swissALTI3D 2 m)
print("terrain…")
lo0, la0 = lv95_to_wgs(XMIN - 200, YMIN - 200); lo1, la1 = lv95_to_wgs(XMAX + 200, YMAX + 200)
url = (f"https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissalti3d/items?"
       f"bbox={lo0:.5f},{la0:.5f},{lo1:.5f},{la1:.5f}&limit=100")
items = []
while url:
    d = get(url); items += d["features"]
    url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
nx, ny = (XMAX - XMIN) // STEP + 1, (YMAX - YMIN) // STEP + 1
H = np.full((ny, nx), np.nan, dtype=np.float32)
xs = XMIN + np.arange(nx) * STEP
ys = YMAX - np.arange(ny) * STEP          # row 0 = north
tifs = {}
for it in items:   # keep the newest tile per 1 km square
    tif = next((a["href"] for k, a in it["assets"].items() if k.endswith("_2_2056_5728.tif")), None)
    if tif:
        sq = it["id"].rsplit("_", 1)[-1]
        if sq not in tifs or it["id"] > tifs[sq][0]:
            tifs[sq] = (it["id"], tif)
for _, tif in tifs.values():
    with rasterio.open(io.BytesIO(get(tif, binary=True))) as src:
        b = src.bounds
        if b.right < XMIN or b.left > XMAX or b.top < YMIN or b.bottom > YMAX:
            continue
        arr = src.read(1)
        cx = np.floor((xs - b.left) / 2).astype(int)
        cy = np.floor((b.top - ys) / 2).astype(int)
        mx, my = (cx >= 0) & (cx < arr.shape[1]), (cy >= 0) & (cy < arr.shape[0])
        H[np.ix_(np.where(my)[0], np.where(mx)[0])] = arr[np.ix_(cy[my], cx[mx])]
assert not np.isnan(H).any(), f"terrain has {np.isnan(H).sum()} gaps"
ZMIN = float(np.floor(H.min()))
((H - ZMIN) * 10).round().astype("<i2").tofile(OUT / "terrain.bin")
print(f"  grid {nx}x{ny} ({len(tifs)} tiles), altitude {H.min():.1f}-{H.max():.1f} m, {time.time()-T0:.0f}s")


def ground(x, y):
    i = int(round((YMAX - y) / STEP)); j = int(round((x - XMIN) / STEP))
    return float(H[min(max(i, 0), ny - 1), min(max(j, 0), nx - 1)])


# ---------------------------------------------------------------- aerial photo (SWISSIMAGE), NT x NT tiles
print("aerial…")
tw, th = (XMAX - XMIN) / NT, (YMAX - YMIN) / NT
tpx = [round(tw / A.px), round(th / A.px)]
assert max(tpx) <= 4096, tpx
for i in range(NT):          # i = column (west -> east)
    for j in range(NT):      # j = row (north -> south)
        x0, x1 = XMIN + i * tw, XMIN + (i + 1) * tw
        y1, y0 = YMAX - j * th, YMAX - (j + 1) * th
        raw = get("https://wms.geo.admin.ch/?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=ch.swisstopo.swissimage"
                  f"&STYLES=&CRS=EPSG:2056&BBOX={x0},{y0},{x1},{y1}&WIDTH={tpx[0]}&HEIGHT={tpx[1]}&FORMAT=image/jpeg", binary=True)
        assert raw[:2] == b"\xff\xd8", f"tile {i},{j} is not a JPEG: {raw[:200]!r}"
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img = ImageEnhance.Color(img).enhance(0.35)
        img = ImageEnhance.Brightness(img).enhance(1.06)
        img.save(OUT / f"aerial_{i}_{j}.jpg", quality=76, optimize=True, progressive=True)
print(f"  {NT}x{NT} tiles of {tpx[0]}x{tpx[1]} px, {time.time()-T0:.0f}s")

# ---------------------------------------------------------------- place labels (swisstopo search)
PLACES = [("Jonction", "Pointe de la Jonction"), ("Plainpalais", "Plaine de Plainpalais"), ("Gare Cornavin", "Genève Gare Cornavin"),
          ("Vieille-Ville", "Place du Bourg-de-Four"), ("Jet d'eau", "Jet d'eau Genève"), ("Eaux-Vives", "Genève, Eaux-Vives"),
          ("Pâquis", "Genève, Pâquis"), ("Servette", "Genève, Servette"), ("Champel", "Genève, Champel"),
          ("Parc des Bastions", "Parc des Bastions"), ("Carouge", "Carouge GE, Marché"), ("Rhône", "Pont du Mont-Blanc")]
labels = []
for name, q in PLACES:
    d = get("https://api3.geo.admin.ch/rest/services/api/SearchServer?" +
            urllib.parse.urlencode({"searchText": q, "type": "locations", "sr": 2056, "limit": 1}))
    if d.get("results"):
        a = d["results"][0]["attrs"]; e, n = a["y"], a["x"]
        if XMIN + 100 < e < XMAX - 100 and YMIN + 100 < n < YMAX - 100:
            labels.append({"name": name, "x": round(e - XMIN), "y": round(n - YMIN), "z": round(ground(e, n) - ZMIN)})
print("  labels:", [l["name"] for l in labels])

# ---------------------------------------------------------------- energy data (SITG)
print("energy layers…")
idc = {}
for f in sitg("SCANE_INDICE_MOYENNES_3_ANS",
              "egid,annee,indice,sre,adresse,agent_energetique_1,agent_energetique_2,"
              "quantite_agent_energetique_1,unite_agent_energetique_1", geometry=False):
    a = f["attributes"]
    if a["egid"] and a["indice"] and (a["egid"] not in idc or a["annee"] > idc[a["egid"]]["annee"]):
        idc[a["egid"]] = a
boilers = defaultdict(list)
for f in sitg("SCANE_CHAUDIERE", "egid,libelle_combustible,annee_chaudiere,puiss_nom_chaudiere,etat_installation,adresse",
              geometry=False):
    a = f["attributes"]
    if a["egid"] and a["etat_installation"] == "Active":
        boilers[a["egid"]].append(a)
solar = {}
for f in sitg("OCEN_SOLAIRE_PV_BATIMENT", "egid,pv_an_tot,p_kwc_tot,area_pv_tot,adresse", geometry=False):
    a = f["attributes"]
    if a["egid"]:
        solar[a["egid"]] = a
print(f"  {time.time()-T0:.0f}s")

# ---------------------------------------------------------------- buildings
print("buildings…")
FOSSIL_WORDS = ("gaz", "mazout", "huile", "fioul", "charbon", "propane")


def carrier_kind(name):
    n = (name or "").lower()
    if not n:
        return None
    if any(w in n for w in FOSSIL_WORDS) or n.strip() == "hel":   # HEL = heating oil, extra light
        return "fossil"
    if "pac" in n or "pompe" in n:
        return "heatpump"
    if "bois" in n or "pellet" in n:
        return "wood"
    if "cad" in n or "distance" in n:
        return "district"
    if "élec" in n or "elec" in n:
        return "electric"
    return "other"


ELEC_RATE = {"school": 28, "office": 60, "housing": 30, "other": 40}      # kWh/m2/yr, rough orders of magnitude
WATER_RATE = {"school": 0.35, "office": 0.25, "housing": 1.1, "other": 0.4}  # m3/m2/yr


def use_class(dest):
    d = (dest or "").lower()
    if "école" in d or "ecole" in d or "enseign" in d:
        return "school"
    if "habitation" in d or "logement" in d or "résidence" in d:
        return "housing"
    if "bureau" in d or "administr" in d or "commerc" in d:
        return "office"
    return "other"


def ring_area(r):
    return sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r))) / 2


uses = Counter(); dropped = 0
buildings = []
for f in sitg("CAD_BATIMENT_HORSOL", "egid,hauteur,niveaux_horsol,destination,annee_construction,surface", where="surface>=20"):
    a, g = f["attributes"], f.get("geometry")
    if not g or not g.get("rings"):
        continue
    h = a.get("hauteur") or ((a.get("niveaux_horsol") or 1) * 3.0)
    if (a.get("surface") or 0) < 30 and h < 4:
        continue
    outer = max(g["rings"], key=lambda r: abs(ring_area(r)))
    cx = sum(p[0] for p in outer) / len(outer); cy = sum(p[1] for p in outer) / len(outer)
    if not (XMIN + 5 < cx < XMAX - 5 and YMIN + 5 < cy < YMAX - 5):
        dropped += 1
        continue
    pts = [p for r in g["rings"] for p in r]
    if any(not (XMIN <= x <= XMAX and YMIN <= y <= YMAX) for x, y in pts):
        dropped += 1      # straddles the map edge: drop instead of overhanging the terrain
        continue
    rings = [[[round(x - XMIN, 1), round(y - YMIN, 1)] for x, y in r] for r in g["rings"]]
    base = min(ground(x, y) for x, y in pts)
    e = a.get("egid")
    b = {"egid": e, "h": round(max(h, 2.5), 1), "z": round(base - ZMIN, 1), "rings": rings,
         "use": a.get("destination"), "year": a.get("annee_construction"), "levels": a.get("niveaux_horsol")}
    uses[b["use"]] += 1
    i = idc.get(e)
    if i:
        b["addr"] = i["adresse"]
        b["idc"] = {"year": i["annee"], "mj_m2": i["indice"], "kwh_m2": round(i["indice"] / 3.6), "sre": i["sre"],
                    "carriers": list(dict.fromkeys(c for c in (i["agent_energetique_1"], i["agent_energetique_2"]) if c)),
                    "kwh": i["quantite_agent_energetique_1"] if i["unite_agent_energetique_1"] == "kWh" else None}
        b["sre"] = i["sre"]
    bl = boilers.get(e)
    if bl:
        b["addr"] = b.get("addr") or bl[0]["adresse"]
        b["boilers"] = [{"fuel": x["libelle_combustible"], "year": x["annee_chaudiere"], "kw": x["puiss_nom_chaudiere"]} for x in bl]
    s = solar.get(e)
    if s and s["pv_an_tot"]:
        b["addr"] = b.get("addr") or (s["adresse"] or "").split(" - ")[0]
        b["pv"] = {"kwh": round(s["pv_an_tot"]), "kwp": round(s["p_kwc_tot"] or 0, 1), "m2": round(s["area_pv_tot"] or 0)}
    kind = carrier_kind((((b.get("idc") or {}).get("carriers")) or [None])[0]) or (carrier_kind(bl[0]["libelle_combustible"]) if bl else None)
    if kind:
        b["heat"] = kind
    floor = b.get("sre") or (a.get("surface") or 0) * (a.get("niveaux_horsol") or max(1, round(h / 3)))
    if floor and floor > 50:
        rnd = random.Random(e or len(buildings))
        u = use_class(b["use"])
        b["sim"] = {"elec_kwh": round(floor * ELEC_RATE[u] * rnd.uniform(0.7, 1.4), -2),
                    "water_m3": round(floor * WATER_RATE[u] * rnd.uniform(0.7, 1.4))}
    buildings.append({k: v for k, v in b.items() if v is not None})

meta = {"area": "Genève centre", "crs": "EPSG:2056", "origin": [XMIN, YMIN], "size": [XMAX - XMIN, YMAX - YMIN],
        "zmin": ZMIN, "terrain": {"nx": nx, "ny": ny, "step": STEP, "scale": 0.1}, "tiles": NT, "labels": labels,
        "sources": {"buildings": "SITG CAD_BATIMENT_HORSOL", "idc": "SITG SCANE_INDICE_MOYENNES_3_ANS (OCEN)",
                    "boilers": "SITG SCANE_CHAUDIERE", "solar": "SITG OCEN_SOLAIRE_PV_BATIMENT",
                    "terrain": "swisstopo swissALTI3D", "aerial": "swisstopo SWISSIMAGE"},
        "simulated": ["sim.elec_kwh", "sim.water_m3"]}
(OUT / "buildings.json").write_text(json.dumps({"meta": meta, "buildings": buildings}, ensure_ascii=False, separators=(",", ":")))
print(f"  {len(buildings)} buildings ({dropped} on the edge dropped); IDC {sum('idc' in b for b in buildings)}, "
      f"boilers {sum('boilers' in b for b in buildings)}, solar {sum('pv' in b for b in buildings)}, heat {sum('heat' in b for b in buildings)}")
print("  heat kinds:", Counter(b.get("heat") for b in buildings).most_common())
cov = sum(c for _, c in uses.most_common(45)) / sum(uses.values())
print(f"  top uses (45 cover {cov:.0%}):", [u for u, _ in uses.most_common(45)])
print("  carriers:", [c for c, _ in Counter(c for b in buildings for c in (b.get("idc") or {}).get("carriers", [])).most_common(30)])
print("  fuels:", [c for c, _ in Counter(x["fuel"] for b in buildings for x in b.get("boilers", [])).most_common(15)])
for p in sorted(OUT.iterdir()):
    print(f"  {p.name}: {p.stat().st_size // 1024} KB")
print(f"done in {time.time()-T0:.0f}s")
