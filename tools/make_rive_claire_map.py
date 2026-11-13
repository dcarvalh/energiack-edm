"""Build the 3D map data for the fictional commune of Rive-Claire -> <out>/ (default prototype/map-rc/).

Rive-Claire has no real geometry: the dataset gives each building a position on a fictional plan (x_km, y_km),
its heated area (SRE), number of levels and type. This script turns that into schematic blocks:
  footprint area = SRE / levels, shape and storey height by type, orientation per neighbourhood;
  underground sites (civil-defence shelters, car park) are flat slabs. S48 (street lighting) is a network: not drawn.
Values per site come from the measured readings (2025): energy per m², heating system, electricity, solar, water.
Output uses the same schema as tools/make_map.py (buildings.json, terrain.bin, aerial_0_0.jpg), so map3d.js reads both.

Data: « Energ-IA Transition, Energ-IACK 2026 », CC BY 4.0. The CSVs are read from the guide HTML (embedded zip).
Run: .venv/bin/python tools/make_rive_claire_map.py [--out DIR] [--scale 1.0]
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "ENERG-IACK26-kDrive-OpenData/02-Defis-Données/1-Donnees-Rive-Claire/EIAK-RC-Guide-Donnees-vf.html"
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(ROOT / "prototype" / "map-rc"))
ap.add_argument("--scale", type=float, default=2.5, help="footprint and height scale, for legibility (declared in meta)")
ap.add_argument("--year", default="2025")
A = ap.parse_args()
OUT = Path(A.out); OUT.mkdir(parents=True, exist_ok=True)
K, YEAR = A.scale, A.year

# ---------------------------------------------------------------- read the CSVs from the guide's embedded zip
html = GUIDE.read_text(encoding="utf-8")
Z = None
for b64 in re.findall(r"base64,([A-Za-z0-9+/=]{1000,})", html):
    raw = base64.b64decode(b64)
    if raw[:2] == b"PK":
        Z = zipfile.ZipFile(io.BytesIO(raw))
assert Z, "no zip found in the guide"


def table(name):
    with Z.open(f"csv/rive-claire-{name}.csv") as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";"))


BAT, INST, MES = table("batiments"), table("installations"), table("mesures")

# ---------------------------------------------------------------- site values for YEAR (deduplicated readings)
seen, V = set(), defaultdict(lambda: defaultdict(float))
dupes = 0
for r in MES:
    key = (r["id_compteur"], r["mois"])
    if key in seen:
        dupes += 1
        continue
    seen.add(key)
    if r["mois"][:4] != YEAR or r["qualite"] == "manquant":
        continue
    code = r["id_compteur"].split("-", 1)[1]
    V[r["id_site"]][code] += float(r["energie_kwh"] or r["valeur"] or 0)

site_sre = defaultdict(float)
site_n = defaultdict(int)
for b in BAT:
    site_sre[b["id_site"]] += float(b["sre_m2"] or 0)
    site_n[b["id_site"]] += 1

HEAT_OF = {"chaudiere_gaz": "fossil", "chaudiere_mazout": "fossil", "sous_station_cad": "district", "pac_sol_eau": "heatpump",
           "pac_air_eau": "heatpump", "chaudiere_granules": "wood", "electrique_direct": "electric"}
inst = defaultdict(list)
for i in INST:
    inst[i["id_site"]].append({"t": i["libelle"], "type": i["type"], "kw": float(i["puissance_kw"]) if i["puissance_kw"] else None,
                               "from": i["mise_en_service"] or None, "to": i["retrait"] or None, "note": i["remarque"] or None})


def site_values(s):
    d = V[s]
    elec = d["EL"] + d["PV"] - d["EL-INJ"]                          # on-site use (dictionary rule)
    heat = 0.9 * d["GZ"] + d["CAD"] + d["MZ"] + d["GR"]              # gas PCS -> ~PCI (x 0.90), oil/pellets already PCI
    sre = site_sre[s]
    active = [HEAT_OF[x["type"]] for x in inst[s] if x["type"] in HEAT_OF and not x["to"]]
    return {
        "year": int(YEAR),
        "kwh_m2": round((d["EL"] + heat) / sre) if sre else None,   # energy purchased per m2, same as the app; None = n/a (SRE 0)
        "elec_kwh": round(elec), "heat_kwh": round(heat) or None,
        "pv_kwh": round(d["PV"]) or None, "water_m3": round(d["EAU"]) or None,
        "deliveries": bool(d["MZ"] or d["GR"]),
        "heat": active[0] if active else None,
    }


# ---------------------------------------------------------------- schematic geometry
# type -> (shape, length/width ratio, storey height m, underground)
SHAPE = {
    "Administration": ("rect", 1.6, 3.4, False), "École primaire": ("L", 1.0, 3.6, False), "École avec piscine": ("L", 1.2, 3.8, False),
    "Crèche (EVE)": ("rect", 1.4, 3.3, False), "Maison de quartier": ("rect", 1.3, 3.3, False), "Salle communale": ("rect", 1.5, 4.5, False),
    "Bibliothèque": ("rect", 1.2, 3.8, False), "Salle de spectacle": ("rect", 1.5, 5.0, False), "Installation sportive": ("rect", 1.7, 4.5, False),
    "Piscine couverte": ("rect", 1.7, 5.0, False), "Patinoire": ("rect", 1.5, 9.0, False), "Voirie et ateliers": ("L", 1.3, 4.5, False),
    "Caserne de pompiers": ("rect", 2.0, 4.5, False), "Logements communaux": ("rect", 2.6, 2.9, False), "Abri PC": ("rect", 1.2, 0.8, True),
    "Cimetière": ("rect", 1.5, 4.0, False), "Parking souterrain": ("rect", 1.4, 0.8, True),
}
ANGLE = {"Centre": 12, "Les Crêts": -8, "Bois-Joli": 22, "Prés-Verts": 4, "La Gravière": -16}   # street-grid angle per neighbourhood
PARK_M2 = 320 * 25 / 2   # S47 has SRE 0: footprint from its 320 places (~25 m² each, 2 levels). Assumption, not in the data.


def jitter(s, span):
    return (int(hashlib.md5(s.encode()).hexdigest()[:6], 16) / 0xFFFFFF - 0.5) * span


def outline(shape, area, ratio):
    """Footprint centred on 0,0 (unrotated), counter-clockwise; returns (points, half-length, half-width)."""
    if shape == "L":                               # L = big square minus a corner quarter: area = 0.75 * w * l
        w = math.sqrt(area / 0.75 / ratio); l = w * ratio
        a, b = l / 2, w / 2
        pts = [(-a, -b), (a, -b), (a, 0), (0, 0), (0, b), (-a, b)]
    else:
        w = math.sqrt(area / ratio); l = w * ratio
        a, b = l / 2, w / 2
        pts = [(-a, -b), (a, -b), (a, b), (-a, b)]
    return pts, a, b


LAKE_DEPTH = 450      # m of lake shown south of the plan (organisers: a town on the Lake Geneva shore)
# map box: plan coordinates (km) with a margin, metres from the box's south-west corner
xs = [float(b["x_km"]) for b in BAT if b["id_site"] != "S48"]
ys = [float(b["y_km"]) for b in BAT if b["id_site"] != "S48"]
STEP = 100
X0 = math.floor((min(xs) - 0.45) * 10) / 10 * 1000
Y0 = math.floor((min(ys) - 0.45) * 10) / 10 * 1000 - LAKE_DEPTH   # extra room south for the lake
W = math.ceil((max(xs) + 0.45) * 10) / 10 * 1000 - X0
H = math.ceil((max(ys) + 0.45) * 10) / 10 * 1000 - Y0
W, H = int(round(W / STEP) * STEP), int(round(H / STEP) * STEP)

blocks = []   # one per building row
for s in sorted(site_n):
    rows = [b for b in BAT if b["id_site"] == s]
    if s == "S48":
        continue
    q = rows[0]["quartier"]
    ang = math.radians(ANGLE.get(q, 0) + jitter(s, 10))
    cx, cy = float(rows[0]["x_km"]) * 1000 - X0, float(rows[0]["y_km"]) * 1000 - Y0
    parts = []
    for b in rows:
        shape, ratio, storey, under = SHAPE[b["typologie"]]
        lv = int(b["niveaux"] or 1)
        area = float(b["sre_m2"]) / (1 if under else lv) if float(b["sre_m2"] or 0) else PARK_M2
        pts, a, w2 = outline(shape, area * K * K, ratio)
        parts.append((b, pts, a, w2, (0.8 if under else lv * storey) * (1 if under else K), under))
    # two buildings on one site: side by side along the street axis, centred on the site point
    total = sum(2 * p[2] for p in parts) + 10 * K * (len(parts) - 1)
    off = -total / 2
    for b, pts, a, w2, h, under in parts:
        dx = off + a; off += 2 * a + 10 * K
        ca, sa = math.cos(ang), math.sin(ang)
        ring = [(round(cx + (x + dx) * ca - y * sa, 1), round(cy + (x + dx) * sa + y * ca, 1)) for x, y in pts]
        ring = ring[::-1]          # clockwise, like the SITG rings in the Geneva map
        ring.append(ring[0])
        blocks.append({"b": b, "ring": ring, "h": round(h, 1), "under": under, "r": math.hypot(a, w2)})


# overlaps: push whole sites apart (bounding circles), report the largest move
def centre(bl):
    pts = bl["ring"][:-1]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


moved = defaultdict(float)
for _ in range(200):
    hit = False
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            bi, bj = blocks[i], blocks[j]
            if bi["b"]["id_site"] == bj["b"]["id_site"]:
                continue
            (xi, yi), (xj, yj) = centre(bi), centre(bj)
            d, need = math.hypot(xj - xi, yj - yi), bi["r"] + bj["r"] + 6
            if d >= need:
                continue
            hit = True
            ux, uy = ((xj - xi) / d, (yj - yi) / d) if d > 0.01 else (1, 0)
            push = (need - d) / 2 + 0.5
            for bl, sg in ((bi, -1), (bj, 1)):
                for other in blocks:
                    if other["b"]["id_site"] == bl["b"]["id_site"]:
                        other["ring"] = [(round(x + sg * ux * push, 1), round(y + sg * uy * push, 1)) for x, y in other["ring"]]
                moved[bl["b"]["id_site"]] += push
    if not hit:
        break

# ---------------------------------------------------------------- buildings.json
out = []
for bl in blocks:
    b = bl["b"]
    s = b["id_site"]
    out.append({
        "id": b["id_batiment"], "site": s, "name": b["nom_site"], "bname": b["nom_batiment"] if site_n[s] > 1 else None,
        "addr": f"{s} · {b['nom_site']}" + (f" · {b['nom_batiment']}" if site_n[s] > 1 else ""),
        "use": b["typologie"], "q": b["quartier"], "year": int(b["annee_construction"]) if b["annee_construction"] else None,
        "reno": int(b["annee_renovation"]) if b["annee_renovation"] else None, "levels": int(b["niveaux"]) if b["niveaux"] else None,
        "sre": float(b["sre_m2"]) or None, "label": b["label"] or None, "homes": int(b["logements"]) if b["logements"] else None,
        "open": b["ouverture"] or None, "note": b["remarque"] or None, "under": bl["under"], "nb": site_n[s],
        "h": bl["h"], "z": 0, "rings": [bl["ring"]],
        "inst": [{k: v for k, v in x.items() if k != "type" and v is not None} for x in inst[s]],
        "rc": site_values(s),
    })

# neighbourhood labels: centre of their sites
QC = {"Centre": "#b04a3a", "Les Crêts": "#8a5aa0", "Bois-Joli": "#2f7a64", "Prés-Verts": "#4f6f8f", "La Gravière": "#9a7425"}
qpts = defaultdict(list)
for b in BAT:
    if b["quartier"] in QC:
        qpts[b["quartier"]].append((float(b["x_km"]) * 1000 - X0, float(b["y_km"]) * 1000 - Y0))
labels = [{"name": q, "x": round(sum(p[0] for p in v) / len(v)), "y": round(max(p[1] for p in v) + 180), "z": 0} for q, v in qpts.items()]

meta = {"area": "Rive-Claire", "kind": "rc", "fictional": True, "crs": "plan fictif (km)", "origin_km": [X0 / 1000, Y0 / 1000],
        "size": [W, H], "zmin": 0, "terrain": {"nx": W // STEP + 1, "ny": H // STEP + 1, "step": STEP, "scale": 0.1}, "tiles": 1,
        "labels": labels, "scale": K, "year": int(YEAR),
        "sources": {"data": "Energ-IA Transition, Energ-IACK 2026 (CC BY 4.0)", "geometry": "schematic, from SRE / levels / type",
                    "scenery": "generated: lake, roads, trees (not in the data)"}}
np.zeros((H // STEP + 1, W // STEP + 1), dtype="<i2").tofile(OUT / "terrain.bin")

# ---------------------------------------------------------------- scenery (generated, not data): lake, roads, trees
rng = np.random.default_rng(7)
SHORE0 = (min(ys) * 1000 - Y0) - 330          # shoreline ~330 m below the southernmost site


def shore(x):
    return SHORE0 + 45 * math.sin(x / 520) + 25 * math.sin(x / 190 + 1.3)


qc = {q: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v)) for q, v in qpts.items()}
site_c = {}
for bl in blocks:
    site_c.setdefault(bl["b"]["id_site"], []).append(centre(bl))
site_c = {k: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v)) for k, v in site_c.items()}
C = qc["Centre"]
lake_road = [(x, shore(x) + 70) for x in range(0, W + 1, 50)]


def curve(p0, p1, bend=0.12):
    """Gentle S-curve between two points, as a polyline."""
    (x0, y0), (x1, y1) = p0, p1
    nx, ny = -(y1 - y0) * bend, (x1 - x0) * bend
    pts = []
    for i in range(21):
        t = i / 20
        w = math.sin(t * math.pi) * (0.5 - t)
        pts.append((x0 + (x1 - x0) * t + nx * w * 2, y0 + (y1 - y0) * t + ny * w * 2))
    return pts


def near_lake(x):   # point on the lakeside road below x
    return (x, shore(x) + 70)


arterials = [lake_road]
for q in ("Les Crêts", "Bois-Joli", "Prés-Verts", "La Gravière"):
    arterials.append(curve(C, qc[q]))
arterials += [curve(qc["Les Crêts"], qc["Bois-Joli"], 0.18), curve(qc["Prés-Verts"], qc["La Gravière"], -0.1),
              curve(qc["Prés-Verts"], near_lake(qc["Prés-Verts"][0] + 150)), curve(qc["La Gravière"], near_lake(qc["La Gravière"][0] - 120)),
              curve(C, near_lake(C[0] + 60), 0.05), curve(qc["Les Crêts"], qc["Prés-Verts"], 0.15)]


def nearest_on(pt, lines):
    best = (1e18, None)
    for ln in lines:
        for a, b in zip(ln, ln[1:]):
            ax, ay, bx, by = *a, *b
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / (dx * dx + dy * dy or 1)))
            q = (ax + t * dx, ay + t * dy)
            d2 = (q[0] - pt[0]) ** 2 + (q[1] - pt[1]) ** 2
            if d2 < best[0]:
                best = (d2, q)
    return best


streets = [[c, nearest_on(c, arterials)[1]] for c in site_c.values()]    # each site gets a street to the network

# trees: lakeside promenade, along the arterials, a wood in Bois-Joli, a park on the Crêts slope
blk = [(centre(bl), bl["r"]) for bl in blocks]
def free(x, y, gap=6):
    if not (20 < x < W - 20 and shore(x) + 25 < y < H - 20):
        return False
    if any((x - c[0]) ** 2 + (y - c[1]) ** 2 < (r + gap + 8) ** 2 for c, r in blk):
        return False
    return nearest_on((x, y), arterials + streets)[0] > (11 + gap) ** 2
trees = []
for x in range(10, W, 22):                                             # promenade row
    y = shore(x) + 40
    if free(x, y, 0):
        trees.append((x, y, 5.5))
for ln in arterials[1:]:                                               # street trees on both sides
    for a, b in zip(ln, ln[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        for k in np.arange(0, L, 34):
            for side in (-1, 1):
                x, y = a[0] + ux * k - uy * 17 * side, a[1] + uy * k + ux * 17 * side
                if free(x, y, 0):
                    trees.append((x, y, 4.5))
for (cx, cy, n, sp) in ((qc["Bois-Joli"][0] + 380, qc["Bois-Joli"][1] + 260, 380, 260), (qc["Les Crêts"][0] - 250, qc["Les Crêts"][1] + 300, 160, 200),
                        (C[0] - 120, C[1] + 520, 70, 120), (qc["La Gravière"][0] - 300, qc["La Gravière"][1] + 250, 90, 160)):
    for _ in range(n):                                                   # woods and parks
        x, y = rng.normal(cx, sp * 0.55), rng.normal(cy, sp * 0.5)
        if free(x, y):
            trees.append((x, y, float(rng.uniform(4.5, 8.5))))
meta["trees"] = [round(v, 1) for t3 in trees for v in t3]
meta["labels"].append({"name": "Le Léman", "x": round(W * 0.55), "y": round(SHORE0 - 330), "z": 0})
(OUT / "buildings.json").write_text(json.dumps({"meta": meta, "buildings": out}, ensure_ascii=False, separators=(",", ":")))

# ---------------------------------------------------------------- ground texture: tints, lake, roads, site codes
PX = 2048
SX = PX / W                                # px per metre
IH = round(PX * H / W)
P = lambda x, y: (x * SX, IH - y * SX)
tint = Image.new("RGB", (PX, IH), (243, 242, 234))
for q, pts in qpts.items():
    layer = Image.new("L", (PX, IH), 0); d = ImageDraw.Draw(layer)
    for x, y in pts:
        r = 330 * SX
        d.ellipse([x * SX - r, IH - y * SX - r, x * SX + r, IH - y * SX + r], fill=255)
    layer = layer.filter(ImageFilter.GaussianBlur(60))
    tint = Image.composite(Image.new("RGB", (PX, IH), QC[q]), tint, layer.point(lambda v: int(v * 0.16)))
img = tint
d = ImageDraw.Draw(img)
# lake, with a pale beach line and the promenade
lake = [P(x, shore(x)) for x in range(0, W + 1, 20)]
d.polygon(lake + [(PX, IH), (0, IH)], fill=(176, 205, 219))
d.line(lake, fill=(222, 214, 190), width=max(2, round(14 * SX)))
d.line([P(x, shore(x) + 40) for x in range(0, W + 1, 20)], fill=(232, 226, 210), width=max(2, round(12 * SX)))
for ln, wd, col in [(arterials[0], 16, (184, 185, 182))] + [(ln, 14, (184, 185, 182)) for ln in arterials[1:]] + [(ln, 9, (198, 199, 196)) for ln in streets]:
    d.line([P(*p) for p in ln], fill=col, width=max(2, round(wd * SX)), joint="curve")
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
except OSError:
    font = ImageFont.load_default()
done = set()
for bl in blocks:
    s = bl["b"]["id_site"]
    if s in done:
        continue
    done.add(s)
    pts = [p for o in blocks if o["b"]["id_site"] == s for p in o["ring"]]
    x = max(p[0] for p in pts) * SX + 6
    y = IH - min(p[1] for p in pts) * SX + 2
    d.text((x, y), s, font=font, fill=QC.get(bl["b"]["quartier"], "#444"))
img.save(OUT / "aerial_0_0.jpg", quality=86)

for f in OUT.iterdir():
    f.chmod(0o644)
print(f"{len(out)} blocks, {len(done)} sites, {len(trees)} trees, box {W}x{H} m at plan ({X0/1000},{Y0/1000}) km, scale x{K}, year {YEAR}; "
      f"duplicate readings skipped {dupes}; largest overlap push {max(moved.values(), default=0):.0f} m "
      f"({', '.join(f'{k} {v:.0f}' for k, v in sorted(moved.items(), key=lambda x: -x[1])[:4])})")
