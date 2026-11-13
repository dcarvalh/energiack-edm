"""Import the organisers' Rive-Claire dataset -> prototype/data.json (replaces the old simulation, tools/make_data.py).

Source: « Energ-IA Transition, Energ-IACK 2026 », Rive-Claire v2 (fictional commune, CC BY 4.0). The 11 CSVs are read
from the zip embedded in the guide HTML. Rules from the dataset's dictionary are applied and stated in meta.rules.

data.json (open, documented in the app's "How it works" page):
  meta              commune, source, period, units, rules, CO2 factors (dataset), prices (ASSUMED, not in the data),
                    targets (ours), climate (monthly + 1991-2020 normals)
  sites[]           id, name, type (typology code), quarter, area_m2 (SRE of the site), year_built, pv_kwp (in service
                    end 2025), buildings[] (all columns), installations[] (all columns)
  heating_history   site -> [{from_month, carrier}]  (month index from 2021-01; carriers gas/oil/district/heat_pump/wood/electric/none)
  series            site -> 60 monthly values: elec_grid, pv_prod, pv_inject (kWh), heat (kWh, gas at net value = x0.90),
                    water (m3), co2 (kg, dataset factors: direct on-site emissions), cost (CHF, assumed prices)
  meters            site -> every meter: id, label, fluid, unit, level, measure, parent, reading, supplier, start, end,
                    v[60] raw values, kwh[60] (as given), q{month: quality} (estimated, missing, duplicate, replaced)
  events[]          installation changes, openings, data-quality findings (site, month, kind, text fr/en)
  quality           import report from tools/rc_quality.py: rows read / loaded / rejected, re-import test, one entry per
                    check (rejected rows never reach the figures; flagged rows are loaded and listed for a person to check)

Run: .venv/bin/python tools/import_rive_claire.py [--out prototype/data.json]
"""
import argparse
import base64
import csv
import io
import json
import re
import zipfile

import rc_quality
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "rive-claire/EIAK-RC-Guide-Donnees-vf.html"
ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(ROOT / "prototype" / "data.json"))
A = ap.parse_args()

Z = None
for b64 in re.findall(r"base64,([A-Za-z0-9+/=]{1000,})", GUIDE.read_text(encoding="utf-8")):
    raw = base64.b64decode(b64)
    if raw[:2] == b"PK":
        Z = zipfile.ZipFile(io.BytesIO(raw))
assert Z, "no zip in the guide"


def table(name):
    with Z.open(f"csv/rive-claire-{name}.csv") as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";"))


BAT, INST, CPT, MES = table("batiments"), table("installations"), table("compteurs"), table("mesures")
CLIM, NORM, TYPO = table("ref-climat"), table("ref-climat-normale"), table("ref-typologies")
QUALITY, REJ = rc_quality.run({"batiments": BAT, "installations": INST, "compteurs": CPT, "mesures": MES,
                               "ref-conversion": table("ref-conversion"), "ref-vecteurs": table("ref-vecteurs")})
START, MONTHS = (2021, 1), 60
num = lambda s: float(s) if s not in (None, "") else None


def midx(ym):
    """'2023-08' -> month index from 2021-01 (may be negative or >= 60)."""
    y, m = map(int, ym.split("-"))
    return (y - START[0]) * 12 + m - START[1]


TYPE_CODE = {t["typologie"]: t["code"] for t in TYPO}
CARRIER = {"chaudiere_gaz": "gas", "chaudiere_mazout": "oil", "sous_station_cad": "district", "pac_sol_eau": "heat_pump",
           "pac_air_eau": "heat_pump", "chaudiere_granules": "wood", "electrique_direct": "electric"}
EN = {  # installation labels
    "Chaudière à gaz": "Gas boiler", "Chaudière à mazout": "Oil boiler", "Chaudière à granulés de bois": "Wood-pellet boiler",
    "Sous-station de chauffage à distance": "District-heating substation",
    "Pompe à chaleur sol-eau (sondes géothermiques)": "Ground-source heat pump (boreholes)", "Pompe à chaleur air-eau": "Air-source heat pump",
    "Installation photovoltaïque": "Solar PV", "Chauffage électrique direct": "Direct electric heating",
    "Capteurs solaires thermiques (eau chaude sanitaire)": "Solar thermal collectors (hot water)", "Groupe froid de la patinoire": "Ice-rink chiller",
    "Bornes de recharge": "EV chargers",
}
CO2 = {"GZ": 2.086, "MZ": 2.65, "GR": 0.0}           # kg per raw unit (m3, litre, kg); electricity and district heat: 0
PRICE = {"elec": 0.27, "gas": 0.14, "oil": 0.13, "district": 0.12, "wood": 0.09, "water": 2.6}   # CHF, ASSUMED
HEAT_PRICE = {"GZ": "gas", "MZ": "oil", "GR": "wood", "CAD": "district"}

# ---------------------------------------------------------------- readings: per meter, 60 months, with quality
meters = defaultdict(dict)
seen = set()
events = []
for c in CPT:
    meters[c["id_site"]][c["id_compteur"]] = {
        "id": c["id_compteur"], "label": c["libelle"], "fluid": c["fluide"], "unit": c["unite"], "level": c["niveau"],
        "measure": c["mesure"], "parent": c["parent"] or None, "supplier": c["fournisseur_donnee"], "reading": c["releve"],
        "start": c["debut"] or None, "end": c["fin"] or None, "v": [None] * MONTHS, "kwh": [None] * MONTHS, "q": {}}
dupes = []
for n, r in enumerate(MES):
    if n in REJ and (r["id_compteur"], r["mois"]) not in seen:   # rejected by the checks (duplicates are marked below)
        continue
    i = midx(r["mois"])
    if not 0 <= i < MONTHS:
        continue
    m = meters[r["id_site"]][r["id_compteur"]]
    key = (r["id_compteur"], r["mois"])
    if key in seen:                                   # dictionary: id_compteur + mois must be unique; keep the first
        m["q"][i] = "duplicate"
        dupes.append(key)
        continue
    seen.add(key)
    if r["qualite"] == "manquant":
        m["q"][i] = "missing"
        continue
    m["v"][i] = num(r["valeur"])
    m["kwh"][i] = num(r["energie_kwh"])
    if r["qualite"] == "estimé":
        m["q"][i] = "estimated"
for mid, mo, est, est_kwh in QUALITY["replacements"]:  # negative values and spikes: replaced by an estimate
    m = meters[mid.split("-", 1)[0]][mid]
    i = midx(mo)
    m["v"][i], m["kwh"][i] = est, est_kwh
    m["q"][i] = "replaced"

# ---------------------------------------------------------------- sites
by_site = defaultdict(list)
for b in BAT:
    by_site[b["id_site"]].append(b)
inst = defaultdict(list)
for i in INST:
    inst[i["id_site"]].append(i)

sites, history, series = [], {}, {}
for sid in sorted(by_site):
    rows = by_site[sid]
    b0 = rows[0]
    active = [i for i in inst[sid] if not i["retrait"]]
    sites.append({
        "id": sid, "name": {"fr": b0["nom_site"], "en": b0["nom_site"]}, "type": TYPE_CODE[b0["typologie"]],
        "quarter": b0["quartier"], "area_m2": round(sum(num(b["sre_m2"]) or 0 for b in rows)),
        "year_built": min(int(b["annee_construction"]) for b in rows) if b0["annee_construction"] else None,
        "pv_kwp": sum(num(i["puissance_kw"]) or 0 for i in active if i["type"] == "pv"),
        "open": b0["ouverture"] or None,
        "buildings": [{"id": b["id_batiment"], "name": b["nom_batiment"], "built": num(b["annee_construction"]),
                       "renovated": num(b["annee_renovation"]), "sre_m2": num(b["sre_m2"]), "levels": num(b["niveaux"]),
                       "label": b["label"] or None, "homes": num(b["logements"]), "open": b["ouverture"] or None,
                       "x_km": num(b["x_km"]), "y_km": num(b["y_km"]), "note": b["remarque"] or None} for b in rows],
        "installations": [{"id": i["id_installation"], "type": i["type"], "label": {"fr": i["libelle"], "en": EN.get(i["libelle"], i["libelle"])},
                           "carrier": i["vecteur"], "kw": num(i["puissance_kw"]), "from": i["mise_en_service"] or None,
                           "to": i["retrait"] or None, "note": i["remarque"] or None} for i in inst[sid]],
    })
    # heating carrier over time, from the heating installations
    heat_inst = sorted((i for i in inst[sid] if i["type"] in CARRIER), key=lambda i: i["mise_en_service"])
    h = []
    for i in heat_inst:
        if i["retrait"] and midx(i["retrait"]) < 0:
            continue
        h.append({"from_month": max(0, midx(i["mise_en_service"])), "carrier": CARRIER[i["type"]]})
    history[sid] = h or [{"from_month": 0, "carrier": "none"}]

    # aggregated monthly series from the meters (dictionary rules)
    M = {m["id"].split("-", 1)[1]: m for m in meters[sid].values()}
    z = lambda code, k="kwh": [(M[code][k][i] or 0) if code in M else 0 for i in range(MONTHS)]
    s = {"elec_grid": z("EL"), "pv_prod": z("PV"), "pv_inject": z("EL-INJ"), "water": z("EAU", "v")}
    s["heat"] = [round(0.9 * z("GZ")[i] + z("CAD")[i] + z("MZ")[i] + z("GR")[i]) for i in range(MONTHS)]
    s["co2"] = [round(sum(CO2[c] * z(c, "v")[i] for c in CO2)) for i in range(MONTHS)]
    s["cost"] = [round(s["elec_grid"][i] * PRICE["elec"] + s["water"][i] * PRICE["water"]
                       + sum(PRICE[HEAT_PRICE[c]] * (0.9 if c == "GZ" else 1) * z(c)[i] for c in HEAT_PRICE)) for i in range(MONTHS)]
    if not any(s["pv_prod"]):
        del s["pv_prod"], s["pv_inject"]
    series[sid] = {k: [round(x) for x in v] for k, v in s.items()}

# ---------------------------------------------------------------- events: installation changes, openings, data quality
for i in INST:
    a = midx(i["mise_en_service"]) if i["mise_en_service"] else -1
    lab_fr, lab_en = i["libelle"], EN.get(i["libelle"], i["libelle"])
    kw = num(i["puissance_kw"])
    p = f" ({kw:g} kW{'c' if i['type'] == 'pv' else ''})" if kw else ""
    pe = f" ({kw:g} kW{'p' if i['type'] == 'pv' else ''})" if kw else ""
    if 0 <= a < MONTHS:
        events.append({"site": i["id_site"], "month": a, "kind": "heating_change" if i["type"] in CARRIER else "installation",
                       "text": {"fr": f"Mise en service : {lab_fr}{p}", "en": f"Commissioned: {lab_en}{pe}"}})
    if i["retrait"] and 0 <= midx(i["retrait"]) < MONTHS:
        events.append({"site": i["id_site"], "month": midx(i["retrait"]), "kind": "heating_change" if i["type"] in CARRIER else "installation",
                       "text": {"fr": f"Retrait : {lab_fr}", "en": f"Removed: {lab_en}"}})
# a heating system retired and the next one starting later: heat source unknown in between (e.g. S04, Aug 2022)
for sid, h_inst in inst.items():
    hs = sorted((i for i in h_inst if i["type"] in CARRIER), key=lambda i: i["mise_en_service"])
    for a, b in zip(hs, hs[1:]):
        if a["retrait"] and midx(b["mise_en_service"]) - midx(a["retrait"]) > 1:
            gap = list(range(midx(a["retrait"]) + 1, midx(b["mise_en_service"])))
            events.append({"site": sid, "month": gap[0], "kind": "quality", "months": gap,
                           "text": {"fr": "Source de chaleur inconnue entre deux installations", "en": "Heat source unknown between two systems"}})
NOTE_EN = {"Puissance en kWc": "Capacity in kWp", "Production de glace": "Ice production", "24 m² de capteurs, non comptés": "24 m² of collectors, not metered",
           "Exploitation saisonnière : septembre à mars (saison 2022-23 écourtée par mesure de sobriété : glace arrêtée fin février 2023).":
               "Seasonal operation: September to March (2022-23 season cut short to save energy: ice stopped at the end of February 2023).",
           "Non chauffé : pas de surface de référence énergétique.": "Unheated: no energy reference area.",
           "Réseau, pas un bâtiment. 2400 points lumineux ; passage aux LED 2021 à 2025, environ 15 % du parc par an.":
               "A network, not a building. 2,400 street lights; switched to LED 2021 to 2025, about 15 % of them per year."}
for st in sites:
    for x in st["buildings"] + st["installations"]:
        if x["note"]:
            n = x["note"]
            x["note"] = {"fr": n, "en": NOTE_EN.get(n) or re.sub(r"COP annuel visé (\d)(?:,(\d))?", lambda m: "Target annual COP " + m[1] + ("." + m[2] if m[2] else ""), n)}
for sid, rows in by_site.items():
    o = rows[0]["ouverture"]
    if o and 0 <= midx(o) < MONTHS:
        events.append({"site": sid, "month": midx(o), "kind": "opening", "text": {"fr": "Ouverture du bâtiment", "en": "Building opens"}})
QTXT = {"missing": ("Relevé manquant", "Missing reading"), "duplicate": ("Relevé en double (ignoré)", "Duplicate reading (ignored)"),
        "estimated": ("Valeur estimée par le distributeur", "Value estimated by the utility"),
        "replaced": ("Valeur aberrante remplacée par une estimation (médiane du même mois)", "Abnormal value replaced by an estimate (median of the same month)")}
for sid, ms in meters.items():
    for m in ms.values():
        runs = defaultdict(list)
        for i, q in sorted(m["q"].items()):
            runs[q].append(i)
        for q, idx in runs.items():   # one event per meter and kind, months listed
            first = idx[0]
            span = f"{len(idx)} mois" if len(idx) > 1 else ""
            events.append({"site": sid, "month": first, "kind": "quality", "meter": m["id"], "months": idx,
                           "text": {"fr": f"{m['id']} : {QTXT[q][0]}" + (f" ({span})" if span else ""),
                                    "en": f"{m['id']}: {QTXT[q][1]}" + (f" ({len(idx)} months)" if len(idx) > 1 else "")}})
events.sort(key=lambda e: (e["month"], e["site"]))

clim = [{"month": c["mois"], **{k: num(v) for k, v in c.items() if k != "mois"}} for c in CLIM]
norm = [{k: (num(v) if k != "mois" else v) for k, v in c.items()} for c in NORM]

data = {
    "meta": {
        "commune": "Rive-Claire", "fictional": True, "inhabitants": 25000,
        "source": "Energ-IA Transition, Energ-IACK 2026 · Rive-Claire v2 (CC BY 4.0)",
        "generated_by": "tools/import_rive_claire.py",
        "start": "2021-01", "months": MONTHS,
        "units": {"energy": "kWh", "water": "m3", "co2": "kg", "money": "CHF"},
        "rules": ["on-site electricity = EL + PV - EL-INJ", "heat = gas x 0.90 (gross -> net) + district heat + oil + pellets",
                  "oil and pellets: deliveries, not measured use", "duplicate readings: first kept",
                  "negative values and abnormal spikes found by the import checks: replaced by the median of the same month in other years", "SRE 0: per-m2 ratio not applicable",
                  "municipal housing: electricity covers common areas only"],
        "co2_kg_per_unit": {"gas_m3": 2.086, "oil_l": 2.65, "pellets_kg": 0, "elec_kwh": 0, "district_kwh": 0},
        "co2_scope": "direct on-site emissions (dataset convention)",
        "price_chf": PRICE, "price_assumed": True,
        "fossil_carriers": ["gas", "oil"], "baseline_year": 2021,
        "targets": {"2030": {"energy": -0.30, "co2": -0.60}, "2050": {"energy": -0.50, "co2": -1.0}}, "targets_source": "City of Geneva climate strategy (our choice)",
        "climate": clim, "climate_normal": norm,
    },
    "sites": sites, "heating_history": history, "series": series,
    "meters": {sid: list(ms.values()) for sid, ms in sorted(meters.items())}, "events": events, "quality": QUALITY,
}
out = Path(A.out)
out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
out.chmod(0o644)
tot = {y: sum(sum(s["heat"][(y - 2021) * 12:(y - 2020) * 12]) + sum(s["elec_grid"][(y - 2021) * 12:(y - 2020) * 12]) for s in series.values()) for y in range(2021, 2026)}
co2 = {y: sum(sum(s["co2"][(y - 2021) * 12:(y - 2020) * 12]) for s in series.values()) for y in range(2021, 2026)}
print(f"wrote {out} ({out.stat().st_size // 1024} KB): {len(sites)} sites, {sum(len(m) for m in meters.values())} meters, "
      f"{len(events)} events, duplicates {dupes}")
print("energy purchased GWh:", {y: round(v / 1e6, 2) for y, v in tot.items()})
print("quality:", QUALITY["loaded"], "loaded,", QUALITY["rejected"], "rejected,", QUALITY["flagged"], "flagged")
print("CO2 t:", {y: round(v / 1000) for y, v in co2.items()})
