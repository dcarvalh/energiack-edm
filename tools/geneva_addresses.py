"""Official building addresses for the Geneva map, from SITG CAD_ADRESSE (plan item 19).

Used by tools/make_map.py. Also runs on its own to fix the addresses of an existing map without rebuilding it:
  .venv/bin/python tools/geneva_addresses.py prototype/map/buildings.json --out <scratch dir>
It prints a before/after count and 20 random pairs to check by hand on map.geo.admin.ch.

Per building (EGID): the official addresses (offadr = Oui) are grouped by street. The street with the most entrances
gives the shown address, numbers joined as a range ("Rue de Bâle 28-30"); every other address goes to `alias`, which
only feeds the search. Buildings whose EGID has no address get an address point inside their footprint, if any.
Names are written in normal case: the register writes family names in capitals ("Rue Jacques-DALPHIN").
"""
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict

URL = "https://vector.sitg.ge.ch/arcgis/rest/services/Hosted/CAD_ADRESSE/FeatureServer/0/query"
FIELDS = "egid,edid,adresse,no_adresse,no_postal,nom_npa"
ROMAN = re.compile(r"^[IVXLCDM]+$")


def fetch(box):
    """Official address points intersecting box = (xmin, ymin, xmax, ymax) in LV95."""
    env = json.dumps({"xmin": box[0], "ymin": box[1], "xmax": box[2], "ymax": box[3], "spatialReference": {"wkid": 2056}})
    out, offset = [], 0
    while True:
        q = {"geometry": env, "geometryType": "esriGeometryEnvelope", "spatialRel": "esriSpatialRelIntersects",
             "where": "offadr='Oui'", "outFields": FIELDS, "returnGeometry": "true", "outSR": 2056, "f": "json",
             "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": "objectid"}
        req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "openedm-map/1.0"})
        d = json.load(urllib.request.urlopen(req, timeout=120))
        assert "error" not in d, d
        feats = d.get("features", [])
        out += feats
        if not d.get("exceededTransferLimit") and len(feats) < 2000:
            return out
        offset += len(feats)


def nice(s):
    """Normal case for words the register writes in capitals; Roman numerals and 1-letter words stay."""
    return re.sub(r"[^\W\d_]{2,}", lambda m: m[0] if not m[0].isupper() or ROMAN.match(m[0]) else m[0].capitalize(), s)


def numkey(n):
    m = re.match(r"(\d+)(.*)", n or "")
    return (int(m[1]), m[2]) if m else (10 ** 9, n or "")


def street_of(a):
    """'Rue Jacques-DALPHIN 41A' -> 'Rue Jacques-Dalphin' (the register's full address minus the number)."""
    full, no = (a.get("adresse") or "").strip(), (a.get("no_adresse") or "").strip()
    if no and full.endswith(" " + no):
        full = full[: -len(no) - 1]
    return nice(full)


def inside(x, y, ring):
    c = False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def assign(buildings, feats, origin):
    """Set addr / npa / alias on buildings (dicts with egid and rings relative to origin). Returns counts."""
    by_egid, points = defaultdict(list), []
    for f in feats:
        a, g = f["attributes"], f.get("geometry") or {}
        if not a.get("adresse"):
            continue
        if a.get("egid"):
            by_egid[a["egid"]].append(a)
        if "x" in g:
            points.append((g["x"] - origin[0], g["y"] - origin[1], a))
    n = {"egid": 0, "footprint": 0, "none": 0}
    for b in buildings:
        for k in ("addr", "npa", "alias"):
            b.pop(k, None)
        rows = by_egid.get(b.get("egid"))
        if rows:
            n["egid"] += 1
        else:
            outer = max(b["rings"], key=len)
            xs, ys = [p[0] for p in outer], [p[1] for p in outer]
            rows = [a for x, y, a in points
                    if min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys) and inside(x, y, outer)]
            if not rows:
                n["none"] += 1
                continue
            n["footprint"] += 1
        streets = defaultdict(list)
        for a in sorted(rows, key=lambda a: a.get("edid") or 0):
            streets[street_of(a)].append(a)
        main = max(streets, key=lambda s: len(streets[s]))       # ties: the first entrance's street
        nos = sorted({(a.get("no_adresse") or "").strip() for a in streets[main]} - {""}, key=numkey)
        b["addr"] = main + (" " + (nos[0] if len(nos) == 1 else nos[0] + "-" + nos[-1]) if nos else "")
        first = streets[main][0]
        if first.get("no_postal"):
            b["npa"] = f"{first['no_postal']} {first.get('nom_npa') or ''}".strip()
        alias = [f"{s} {(a.get('no_adresse') or '').strip()}".strip() for s, rs in streets.items() for a in rs]
        alias = [x for x in dict.fromkeys(alias) if x != b["addr"]]
        if alias:
            b["alias"] = " · ".join(alias)
    return n


if __name__ == "__main__":
    import argparse
    import random
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("buildings", help="an existing buildings.json (prototype/map/buildings.json)")
    ap.add_argument("--out", required=True, help="folder for the fixed buildings.json (never prototype/ directly)")
    A = ap.parse_args()
    data = json.loads(Path(A.buildings).read_text(encoding="utf-8"))
    (x0, y0), (w, h) = data["meta"]["origin"], data["meta"]["size"]
    B = data["buildings"]
    before = [b.get("addr") for b in B]
    feats = fetch((x0, y0, x0 + w, y0 + h))
    n = assign(B, feats, (x0, y0))
    data["meta"]["sources"]["addresses"] = "SITG CAD_ADRESSE (official addresses)"
    out = Path(A.out); out.mkdir(parents=True, exist_ok=True)
    (out / "buildings.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(feats)} official address points; {len(B)} buildings: by EGID {n['egid']}, by footprint {n['footprint']}, none {n['none']}")
    print(f"without address: before {sum(not a for a in before)}, after {sum(not b.get('addr') for b in B)}")
    dup = lambda xs: max((xs.count(x) for x in set(xs) if x), default=0)
    print(f"most buildings sharing one address: before {dup(before)}, after {dup([b.get('addr') for b in B])}")
    for i in sorted(random.Random(19).sample(range(len(B)), 20)):
        print(f"  EGID {B[i].get('egid')}: {before[i]!r} -> {B[i].get('addr')!r} {B[i].get('npa', '')}")
