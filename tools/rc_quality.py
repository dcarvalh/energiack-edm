"""Quality and consistency checks for a Rive-Claire style import (first user story).

run(tables) takes the raw CSV rows (lists of dicts, as csv.DictReader gives them) and returns (report, rejected):
  report    goes into data.json as "quality": rows read / loaded / rejected, the re-import test, and one entry per check
            {code, kind: "rejected" | "flagged", n, items: [{m: id, s: site, mo: "YYYY-MM", v: value, x: detail}]}
  rejected  set of indexes into tables["mesures"] that must not be loaded (duplicates included: the first copy is kept)
  report["replacements"]   [[meter, "YYYY-MM", estimated value, estimated kWh], ...] used instead of the raw value

Rejected rows never reach the figures. Negative values and spikes are replaced by an estimate: the median of the same
month in the meter's other years, converted to kWh with that month's factor (David, 13 Nov). Flagged rows are loaded as
they are and listed to be checked by a person.
Wording lives in the app (T.fr / T.en, keys qc_<code>), not here.

Self-test: python tools/rc_quality.py --selftest  (injects one defect of each kind and checks the real data's known ones)
"""
import re
import statistics
from collections import defaultdict

START, MONTHS = (2021, 1), 60
YM = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
QUALITY = {"mesuré", "estimé", "manquant"}
DELIVERY = "bon de livraison"            # oil and pellets: deliveries, a month without a row is normal
MAX_ITEMS = 60
EXCLUDE = ("negative", "spike")          # replaced by an estimate, with a note


def midx(ym):
    y, m = map(int, ym.split("-"))
    return (y - START[0]) * 12 + m - START[1]


def ym(i):
    return f"{START[0] + i // 12}-{i % 12 + 1:02d}"


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def run(tables):
    BAT, INST, CPT, MES = (tables[k] for k in ("batiments", "installations", "compteurs", "mesures"))
    conv = defaultdict(dict)                       # vecteur -> {"YYYY-MM" | "toujours": factor}
    for c in tables.get("ref-conversion", []):
        conv[c["vecteur"]][c["mois"]] = num(c["facteur"])
    vect = {v["fluide_mesures"]: v["vecteur_conversion"] for v in tables.get("ref-vecteurs", [])}

    found = defaultdict(list)                     # code -> items
    add = lambda code, **it: found[code].append({k: v for k, v in it.items() if v is not None})

    # ------------------------------------------------------------ reference tables
    sites = set()
    for tab, rows, key in (("batiments", BAT, "id_batiment"), ("compteurs", CPT, "id_compteur"), ("installations", INST, "id_installation")):
        seen = set()
        for r in rows:
            k = (r.get(key) or "").strip()
            if not k or k in seen:
                add("ref_ids", m=k or "(vide)", x=tab)
            seen.add(k)
    sites = {b["id_site"] for b in BAT}
    meters = {c["id_compteur"]: c for c in CPT}
    for c in CPT:
        if c["id_site"] not in sites:
            add("ref_links", m=c["id_compteur"], s=c["id_site"], x="site")
        if c["parent"] and c["parent"] not in meters:
            add("ref_links", m=c["id_compteur"], s=c["id_site"], x="parent " + c["parent"])
    for i in INST:
        if i["id_site"] not in sites:
            add("ref_links", m=i["id_installation"], s=i["id_site"], x="site")

    # ------------------------------------------------------------ readings: reject what cannot be loaded
    rejected, keys, store = set(), {}, {}
    for n, r in enumerate(MES):
        mid, mo = r.get("id_compteur", ""), r.get("mois", "")
        c = meters.get(mid)
        if not c:
            add("unknown_meter", m=mid or "(vide)", s=r.get("id_site"), mo=mo); rejected.add(n); continue
        if not YM.match(mo or ""):
            add("bad_month", m=mid, s=c["id_site"], x=mo or "(vide)"); rejected.add(n); continue
        if not 0 <= midx(mo) < MONTHS:
            add("bad_month", m=mid, s=c["id_site"], mo=mo, x="period"); rejected.add(n); continue
        diff = [f for f, cf in (("id_site", "id_site"), ("fluide", "fluide"), ("mesure", "mesure")) if r.get(f) != c[cf]]
        if diff:
            add("link_mismatch", m=mid, s=c["id_site"], mo=mo, x=", ".join(f"{f}: {r.get(f)}" for f in diff)); rejected.add(n); continue
        if r.get("unite") != c["unite"]:
            add("unit_mismatch", m=mid, s=c["id_site"], mo=mo, x=f"{r.get('unite')} ≠ {c['unite']}"); rejected.add(n); continue
        q, v = r.get("qualite"), num(r.get("valeur"))
        if q not in QUALITY or (q != "manquant" and v is None):
            add("bad_value", m=mid, s=c["id_site"], mo=mo, x=(r.get("valeur") or "(vide)") if q in QUALITY else f"qualite: {q}")
            rejected.add(n); continue
        key = (mid, mo)
        if key in keys:
            first = MES[keys[key]]
            add("duplicate", m=mid, s=c["id_site"], mo=mo, v=v, x="same" if first["valeur"] == r["valeur"] else first["valeur"])
            rejected.add(n); continue
        keys[key] = n
        store[key] = r

    # ------------------------------------------------------------ re-import: load the accepted rows a second time
    def upsert(db, rows):
        added = same = conflict = 0
        for r in rows:
            k = (r["id_compteur"], r["mois"])
            if k not in db:
                db[k] = (r["valeur"], r["qualite"]); added += 1
            elif db[k] == (r["valeur"], r["qualite"]):
                same += 1
            else:
                conflict += 1
        return {"added": added, "same": same, "conflicts": conflict}
    accepted = [MES[n] for n in range(len(MES)) if n not in rejected]
    db = {}
    first, second = upsert(db, accepted), upsert(db, accepted)

    # ------------------------------------------------------------ flagged: loaded, to be checked by a person
    series = defaultdict(lambda: [None] * MONTHS)  # meter -> 60 values (None = no value)
    for (mid, mo), r in store.items():
        c, i = meters[mid], midx(mo)
        if r["qualite"] == "manquant":
            add("missing", m=mid, s=c["id_site"], mo=mo, x="marked")
            continue
        v = num(r["valeur"])
        series[mid][i] = v
        if r["qualite"] == "estimé":
            add("estimated", m=mid, s=c["id_site"], mo=mo, v=v)
        if (c["debut"] and mo < c["debut"]) or (c["fin"] and mo > c["fin"]):
            add("out_of_window", m=mid, s=c["id_site"], mo=mo, v=v, x=f"{c['debut'] or '…'} – {c['fin'] or '…'}")
        if v < 0:
            add("negative", m=mid, s=c["id_site"], mo=mo, v=v)
        kwh = num(r.get("energie_kwh"))
        if c["unite"] == "kWh":
            exp = v
        elif r["fluide"] in vect:
            f = conv[vect[r["fluide"]]]
            exp = v * f[mo] if mo in f else (v * f["toujours"] if "toujours" in f else None)
        else:
            exp = None                                   # water: no energy value expected
        if exp is not None and (kwh is None or abs(kwh - exp) > max(1, 0.01 * abs(exp))):
            add("conversion", m=mid, s=c["id_site"], mo=mo, v=kwh, x=round(exp))
    for mid, c in meters.items():                       # months with no row inside the meter's own dates
        if c["releve"] == DELIVERY:
            continue
        lo, hi = max(0, midx(c["debut"]) if c["debut"] else 0), min(MONTHS - 1, midx(c["fin"]) if c["fin"] else MONTHS - 1)
        for i in range(lo, hi + 1):
            if (mid, ym(i)) not in store:
                add("missing", m=mid, s=c["id_site"], mo=ym(i), x="no_row")

    for mid, s in series.items():
        c = meters[mid]
        if c["releve"] == DELIVERY:
            continue
        same_month = lambda i: [s[j] for j in range(i % 12, MONTHS, 12) if j != i and s[j] is not None]
        med = {i: statistics.median(same_month(i)) if same_month(i) else None for i in range(MONTHS)}
        for i, v in enumerate(s):                       # spike: far above the same month in other years and its neighbours
            if v is None or not med[i] or med[i] <= 0:
                continue
            nb = [x for x in (s[i - 1] if i else None, s[i + 1] if i + 1 < MONTHS else None) if x is not None]
            if v > 5 * med[i] and nb and v > 3 * max(nb):
                add("spike", m=mid, s=c["id_site"], mo=ym(i), v=v, x=round(med[i]))
        run_ = []                                        # zeros where other years have real values, 2+ months in a row
        for i in range(MONTHS + 1):
            z = i < MONTHS and s[i] == 0 and med[i] and med[i] > 100
            if z:
                run_.append(i)
            else:
                if len(run_) >= 2:
                    add("zero_run", m=mid, s=c["id_site"], mo=ym(run_[0]), v=0, x=f"{ym(run_[0])} – {ym(run_[-1])}")
                run_ = []
        zeros = [i for i, v in enumerate(s) if v == 0 and i + 1 < MONTHS and s[i + 1] and s[i + 1] > 0]
        alt = [i for i in zeros if i + 2 in zeros]       # 0, x, 0, x: read every two months, entered monthly
        if len(alt) >= 2:
            add("alternating", m=mid, s=c["id_site"], mo=ym(alt[0]), v=0, x=f"{ym(alt[0])} – {ym(max(alt) + 3)}")

    bad = {(it["m"], it["mo"]) for code in EXCLUDE for it in found[code]}
    replacements = []                                    # estimate = median of the same month in the other years
    for mid, mo in sorted(bad):
        s, i, c = series[mid], midx(mo), meters[mid]
        same = [s[j] for j in range(i % 12, MONTHS, 12) if j != i and s[j] is not None and s[j] >= 0 and (mid, ym(j)) not in bad]
        if not same:
            continue
        est = round(statistics.median(same))
        if c["unite"] == "kWh":
            kwh = est
        elif c["fluide"] in vect:
            f = conv[vect[c["fluide"]]]
            kwh = round(est * (f[mo] if mo in f else f["toujours"]))
        else:
            kwh = None
        replacements.append([mid, mo, est, kwh])
        for code in EXCLUDE:
            for it in found[code]:
                if (it["m"], it["mo"]) == (mid, mo):
                    it["e"] = est

    kids = defaultdict(list)                             # sub-meters must not exceed their parent
    for c in CPT:
        if c["parent"] in meters:
            kids[c["parent"]].append(c["id_compteur"])
    for p, ks in kids.items():
        sid = meters[p]["id_site"]
        pv, inj = series.get(f"{sid}-PV"), series.get(f"{sid}-EL-INJ")
        for i in range(MONTHS):
            pv_i = pv[i] or 0 if pv and p == f"{sid}-EL" else 0
            inj_i = inj[i] or 0 if inj and p == f"{sid}-EL" else 0
            par = series[p][i] if p in series else None
            sub = [series[k][i] for k in ks if k in series and series[k][i] is not None]
            if par is None or not sub:
                continue
            onsite = par + pv_i - inj_i
            if sum(sub) > 1.02 * onsite + 1:
                add("submeter", m=p, s=sid, mo=ym(i), v=round(sum(sub)), x=round(onsite))

    order = ["ref_ids", "ref_links", "unknown_meter", "bad_month", "link_mismatch", "unit_mismatch", "bad_value", "duplicate",
             "missing", "estimated", "negative", "spike", "zero_run", "alternating", "conversion", "submeter", "out_of_window"]
    kind = lambda code: ("rejected" if order.index("unknown_meter") <= order.index(code) < order.index("missing")
                         else "excluded" if code in EXCLUDE else "flagged")
    checks = [{"code": c, "kind": kind(c), "n": len(found[c]), "items": found[c][:MAX_ITEMS]} for c in order]
    report = {
        "read": {k: len(tables[k]) for k in ("batiments", "compteurs", "installations", "mesures")},
        "loaded": len(MES) - len(rejected), "rejected": len(rejected),
        "flagged": sum(ch["n"] for ch in checks if ch["kind"] == "flagged"),
        "excluded": sum(ch["n"] for ch in checks if ch["kind"] == "excluded"),
        "replacements": replacements,
        "reimport": {"first": first, "second": second},
        "checks": checks,
    }
    return report, rejected


# ---------------------------------------------------------------- self-test
def _tables():
    import csv
    from pathlib import Path
    d = Path(__file__).resolve().parent.parent / "rive-claire/csv"
    names = ("batiments", "installations", "compteurs", "mesures", "ref-conversion", "ref-vecteurs")
    return {n: list(csv.DictReader(open(d / f"rive-claire-{n}.csv", encoding="utf-8-sig"), delimiter=";")) for n in names}


def selftest():
    import copy
    T = _tables()
    rep, rej = run(T)
    has = lambda r, code, m, mo=None: any(it.get("m") == m and (mo is None or it.get("mo") == mo)
                                          for ch in r["checks"] if ch["code"] == code for it in ch["items"])
    known = [("duplicate", "S03-EL", "2024-06"), ("missing", "S25-GZ", "2021-05"), ("missing", "S25-GZ", "2021-06"),
             ("missing", "S44-EL", "2023-11"), ("estimated", "S40-EL", "2023-05"), ("estimated", "S40-EL", "2023-08"),
             ("negative", "S14-GZ", "2022-03"), ("spike", "S38-GZ", "2022-11"), ("zero_run", "S26-PV", "2023-07"),
             ("alternating", "S41-EAU", None)]
    for k in known:
        assert has(rep, *k), f"real data: {k} not found"
    assert rep["reimport"]["second"]["added"] == 0 and rep["reimport"]["second"]["conflicts"] == 0
    assert rep["loaded"] + rep["rejected"] == len(T["mesures"])
    rk = {(m, mo): (v, k) for m, mo, v, k in rep["replacements"]}
    assert ("S38-GZ", "2022-11") in rk and ("S14-GZ", "2022-03") in rk and all(v >= 0 for v, _ in rk.values())

    # inject one defect of each kind into a copy and check each is caught
    X = copy.deepcopy(T)
    base = next(r for r in X["mesures"] if r["id_compteur"] == "S01-EL" and r["mois"] == "2022-01")
    row = lambda **kw: {**base, **kw}
    X["mesures"] += [
        row(id_compteur="S99-EL", id_site="S99"),                    # unknown_meter
        row(mois="2022-13"), row(mois="2019-05"),                     # bad_month: format, period
        row(mois="2022-02", id_site="S02"),                           # link_mismatch
        row(mois="2022-03", unite="Wh"),                              # unit_mismatch
        row(mois="2022-04", valeur="12,5"),                           # bad_value
        row(mois="2022-01", valeur="1"),                              # duplicate with a different value
    ]
    X["mesures"] = [r for r in X["mesures"] if not (r["id_compteur"] == "S02-EL" and r["mois"] == "2023-02")]  # gap
    for r in X["mesures"]:
        if r["id_compteur"] == "S05-EL" and r["mois"] == "2022-06":
            r["energie_kwh"] = str(float(r["valeur"]) * 2)                # conversion
        if r["id_compteur"] == "S04-PAC" and r["mois"] == "2024-01":
            r["valeur"] = r["energie_kwh"] = "99999999"                   # submeter > parent (and a spike)
    gz = next(r for r in X["mesures"] if r["id_compteur"] == "S01-GZ" and r["mois"] == "2024-06")
    X["mesures"].append({**gz, "mois": "2024-09"})                         # out_of_window (S01-GZ ends 2024-06)
    X["compteurs"].append({**X["compteurs"][0]})                           # ref_ids: duplicate meter id
    X["installations"].append({**X["installations"][0], "id_installation": "S98-I1", "id_site": "S98"})  # ref_links
    r2, _ = run(X)
    n = {c["code"]: c["n"] for c in r2["checks"]}
    n0 = {c["code"]: c["n"] for c in rep["checks"]}
    for code, k in (("unknown_meter", 1), ("bad_month", 2), ("link_mismatch", 1), ("unit_mismatch", 1), ("bad_value", 1),
                    ("duplicate", 1), ("missing", 1), ("conversion", 1), ("submeter", 1), ("out_of_window", 1),
                    ("ref_ids", 1), ("ref_links", 1)):
        assert n[code] >= n0[code] + k, f"injected {code}: {n0[code]} -> {n[code]}"
    assert has(r2, "missing", "S02-EL", "2023-02") and has(r2, "submeter", "S04-EL", "2024-01")
    print("selftest OK ·", ", ".join(f"{c['code']} {c['n']}" for c in rep["checks"]))
    print("rows", rep["read"]["mesures"], "loaded", rep["loaded"], "rejected", rep["rejected"], "reimport", rep["reimport"])


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
