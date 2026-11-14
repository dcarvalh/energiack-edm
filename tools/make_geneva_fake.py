#!/usr/bin/env python3
"""Generate a fictional Geneva municipal energy dataset.

Same CSV schema and conventions as the Rive-Claire dataset (see rive-claire/csv/).
All output CSVs use ';' as delimiter, UTF-8 with BOM, empty cells = empty strings.

Writes 5 files to geneve/csv/:
  geneve-batiments.csv, geneve-compteurs.csv, geneve-installations.csv,
  geneve-mesures.csv, geneve-ref-typologies.csv

The ref tables geneve-ref-climat.csv, geneve-ref-climat-normale.csv, geneve-ref-co2.csv,
geneve-ref-conversion.csv, geneve-ref-vecteurs.csv already exist (copied from Rive-Claire,
identical physics/climate) and are NOT touched.

Deterministic: random.seed(42). Standard library only.

Run:  python3 tools/make_geneva_fake.py
"""
import csv
import math
import random
from pathlib import Path

random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "geneve" / "csv"

START_YEAR, N_MONTHS = 2021, 60   # 2021-01 .. 2025-12


def months():
    out = []
    for i in range(N_MONTHS):
        y = START_YEAR + i // 12
        m = i % 12 + 1
        out.append(f"{y}-{m:02d}")
    return out


MONTHS = months()


def fnum(x):
    """Format a number the way the Rive-Claire CSVs do: ints without decimals."""
    if x is None or x == "":
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


# --------------------------------------------------------------------------
# Reference data read from the existing (copied) ref files
# --------------------------------------------------------------------------
def load_ref(name):
    with open(CSV_DIR / f"geneve-{name}.csv", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


GAS_FACTOR = {}        # "YYYY-MM" -> kWh/m3 for gaz
MAZOUT_FACTOR = 10.0
GRAN_FACTOR = 4.9
for r in load_ref("ref-conversion"):
    if r["vecteur"] == "gaz":
        GAS_FACTOR[r["mois"]] = float(r["facteur"])
    elif r["vecteur"] == "mazout" and r["mois"] == "toujours":
        MAZOUT_FACTOR = float(r["facteur"])
    elif r["vecteur"] == "granulés de bois" and r["mois"] == "toujours":
        GRAN_FACTOR = float(r["facteur"])

# degree-days (heating shape) and radiation (solar shape), per month
DJ = {}        # "YYYY-MM" -> degres_jours
RAD = {}       # "YYYY-MM" -> rayonnement kWh/m2
for r in load_ref("ref-climat"):
    DJ[r["mois"]] = float(r["degres_jours_20_12"])
    RAD[r["mois"]] = float(r["rayonnement_kwh_m2"])

DJ_TOTAL = sum(DJ.values())            # total degree-days over 60 months
RAD_TOTAL = sum(RAD.values())


# --------------------------------------------------------------------------
# Typologies (reuse the exact Rive-Claire labels) and their slug codes
# --------------------------------------------------------------------------
TYPO_CODE = {
    "Administration": "administration",
    "École primaire": "ecole_primaire",
    "École avec piscine": "ecole_piscine",
    "Crèche (EVE)": "creche",
    "Maison de quartier": "maison_quartier",
    "Salle communale": "salle_communale",
    "Bibliothèque": "bibliotheque",
    "Salle de spectacle": "salle_spectacle",
    "Installation sportive": "installation_sportive",
    "Piscine couverte": "piscine",
    "Patinoire": "patinoire",
    "Voirie et ateliers": "voirie",
    "Caserne de pompiers": "caserne",
    "Logements communaux": "logements",
    "Abri PC": "abri_pc",
    "Cimetière": "cimetiere",
    "Parking souterrain": "parking",
    "Éclairage public": "eclairage_public",
}

# Quartiers of Geneva with a cluster centre (x_km, y_km) in the 0.5..5.0 range.
QUARTIERS = {
    "Pâquis":      (2.6, 4.3),
    "Eaux-Vives":  (3.9, 3.5),
    "Plainpalais": (2.2, 2.2),
    "Jonction":    (1.0, 1.8),
    "Servette":    (2.4, 4.0),
    "Grottes":     (2.1, 3.6),
    "Champel":     (3.2, 1.4),
    "Saint-Jean":  (1.1, 3.1),
    "Charmilles":  (1.4, 4.1),
    "Acacias":     (2.8, 0.9),
}


# --------------------------------------------------------------------------
# Site plan: 40 sites. Each dict describes one site.
#   typo      typology label
#   quartier  neighbourhood
#   heat      heat source: "GZ" | "CAD" | "MZ" | "PAC" | "GR" | "EL" | None
#   pv        kWp of a PV plant or None
#   sre       energy reference area m2 (0 or None = unheated)
#   niveaux   number of levels
#   nom       human name of the site
#   subs      list of sub-meter suffixes (EL-VENT, EL-FROID, ...)
#   extra     list of extra building rows for the site (nom_batiment, sre, niveaux)
#   logements number of dwellings (for housing)
#   history   optional heat transition: (old_heat, old_end "YYYY-MM", new_heat, new_start "YYYY-MM")
# --------------------------------------------------------------------------
def build_sites():
    S = []

    def add(typo, quartier, nom, heat, sre, niveaux, pv=None, subs=None,
            logements=None, history=None, extra=None, label="", annee=2000,
            renov="", remarque=""):
        S.append(dict(typo=typo, quartier=quartier, nom=nom, heat=heat, sre=sre,
                      niveaux=niveaux, pv=pv, subs=subs or [], logements=logements,
                      history=history, extra=extra or [], label=label, annee=annee,
                      renov=renov, remarque=remarque))

    # --- Administration (3) ---
    add("Administration", "Plainpalais", "Hôtel municipal", "CAD", 2800, 4,
        pv=90, annee=1905, renov=2009, label="Patrimoine recensé",
        extra=[("Annexe administrative", 1100, 3)])
    add("Administration", "Eaux-Vives", "Centre administratif des Eaux-Vives", "GZ", 2200, 4, annee=1991)
    add("Administration", "Servette", "Service technique de la Servette", "CAD", 1400, 3, annee=2004)

    # --- Écoles primaires (6) ---
    add("École primaire", "Pâquis", "École des Pâquis", "CAD", 4200, 3,
        pv=80, annee=1910, renov=2015, label="Patrimoine recensé",
        extra=[("Pavillon", 900, 1)])
    add("École primaire", "Jonction", "École de la Jonction", "GZ", 4400, 3, annee=1968)
    add("École primaire", "Champel", "École de Champel", "CAD", 3800, 3, pv=60, annee=1981)
    add("École primaire", "Charmilles", "École des Charmilles", "PAC", 3600, 3,
        pv=100, annee=2011, label="Minergie")
    add("École primaire", "Acacias", "École des Acacias", "CAD", 4500, 3, annee=1959, renov=2019,
        label="Minergie (rénovation)")
    add("École primaire", "Servette", "École de la Servette", "PAC", 4200, 3, pv=120,
        annee=2018, label="Minergie-P")

    # --- École avec piscine (1) ---
    add("École avec piscine", "Eaux-Vives", "École et bassin des Eaux-Vives", "GZ", 6400, 3,
        subs=["EL-EAUBASSIN"], annee=1972, renov=2008)

    # --- Crèches / EVE (5) ---
    add("Crèche (EVE)", "Plainpalais", "EVE de Plainpalais", "GZ", 650, 2, annee=1932, renov=2006)
    add("Crèche (EVE)", "Pâquis", "EVE des Pâquis", "CAD", 820, 2, annee=1986)
    add("Crèche (EVE)", "Champel", "EVE de Champel", "GZ", 900, 2, annee=2008)
    add("Crèche (EVE)", "Servette", "EVE de la Servette", "PAC", 1050, 2, annee=2014, label="Minergie")
    add("Crèche (EVE)", "Charmilles", "EVE des Charmilles", "PAC", 1100, 2, pv=40,
        annee=2023, label="Minergie-P")

    # --- Maisons de quartier (2) ---
    add("Maison de quartier", "Pâquis", "Maison de quartier des Pâquis", "GZ", 520, 2, annee=1960, renov=1998)
    add("Maison de quartier", "Jonction", "Maison de quartier de la Jonction", "CAD", 780, 2, annee=1979)

    # --- Salles communales (2) ---
    add("Salle communale", "Plainpalais", "Salle communale de Plainpalais", "GZ", 2300, 2, annee=1967, renov=2003)
    add("Salle communale", "Champel", "Salle des fêtes de Champel", "GZ", 1400, 2, annee=1986)

    # --- Bibliothèque (1) ---
    add("Bibliothèque", "Plainpalais", "Bibliothèque municipale", "CAD", 1500, 3, annee=2006)

    # --- Salle de spectacle (1) ---
    add("Salle de spectacle", "Eaux-Vives", "Théâtre des Eaux-Vives", "GZ", 3600, 3,
        subs=["EL-VENT"], annee=1990)

    # --- Installations sportives (3) ---
    add("Installation sportive", "Charmilles", "Centre sportif des Charmilles", "GZ", 2900, 2, annee=1983)
    add("Installation sportive", "Acacias", "Vestiaires du stade des Acacias", "MZ", 650, 1, annee=1975, renov=2013)
    add("Installation sportive", "Champel", "Club-house du tennis de Champel", "EL", 260, 1, annee=1988)

    # --- Piscine couverte (1) ---
    add("Piscine couverte", "Servette", "Piscine couverte de la Servette", "GZ", 4600, 2,
        subs=["EL-EAUBASSIN", "EL-VENT"], annee=1976, renov=2010)

    # --- Patinoire (1) ---
    add("Patinoire", "Acacias", "Patinoire des Acacias", "GZ", 3800, 1,
        subs=["EL-FROID"], annee=1994,
        remarque="Exploitation saisonnière : septembre à mars.")

    # --- Voirie et ateliers (1) ---
    add("Voirie et ateliers", "Acacias", "Voirie et ateliers municipaux", "GZ", 3100, 2,
        pv=200, subs=["EL-BORNES"], annee=1979)

    # --- Caserne de pompiers (1) ---
    add("Caserne de pompiers", "Jonction", "Caserne des pompiers", "GZ", 1250, 2, annee=2001)

    # --- Logements communaux (7) ---
    add("Logements communaux", "Pâquis", "Immeuble Rue de Berne 12", "CAD", 2600, 5, logements=32, annee=1958, renov=2012)
    add("Logements communaux", "Servette", "Immeuble Avenue Wendt 24", "MZ", 3400, 7, logements=44, annee=1963)
    add("Logements communaux", "Charmilles", "Immeuble Rue de Lyon 68", "CAD", 4200, 8, logements=56, annee=1969)
    add("Logements communaux", "Eaux-Vives", "Immeuble Rue des Eaux-Vives 11", "GZ", 2900, 6, logements=38,
        annee=1974, history=("MZ", "2023-07", "GZ", "2023-08"))
    add("Logements communaux", "Plainpalais", "Immeuble Boulevard du Pont-d'Arve 30", "GZ", 2100, 5, logements=26, annee=1985)
    add("Logements communaux", "Acacias", "Immeuble Route des Acacias 40", "GZ", 1900, 4, logements=24, annee=1992)
    add("Logements communaux", "Champel", "Immeuble Avenue de Champel 50", "PAC", 3000, 6, logements=40,
        pv=60, annee=2016, label="Minergie")

    # --- Abri PC (2, unheated) ---
    add("Abri PC", "Plainpalais", "Abri PC de Plainpalais", None, 0, 1, annee=1982)
    add("Abri PC", "Champel", "Abri PC de Champel", None, 0, 1, annee=1974)

    # --- Cimetière (1, unheated) ---
    add("Cimetière", "Saint-Jean", "Cimetière de Saint-Georges", None, 0, 1, annee=1968)

    # --- Parking souterrain (1, unheated) ---
    add("Parking souterrain", "Plainpalais", "Parking souterrain de Plainpalais", None, 0, 2,
        annee=1996, remarque="Non chauffé : pas de surface de référence énergétique.")

    # --- Éclairage public (1, city-wide) ---
    add("Éclairage public", "Tous", "Éclairage public", None, 0, None, annee="",
        remarque="Réseau, pas un bâtiment. Points lumineux LED.")

    return S


SITES = build_sites()
assert len(SITES) == 40, f"expected 40 sites, got {len(SITES)}"


def site_id(n):
    return f"G{n + 1:02d}"


def jitter(center, spread=0.35):
    return round(center + random.uniform(-spread, spread), 2)


# Assign ids and coordinates
for n, s in enumerate(SITES):
    s["id"] = site_id(n)
    cx, cy = QUARTIERS[s["quartier"]] if s["quartier"] in QUARTIERS else (2.1, 1.96)
    s["x"] = jitter(cx)
    s["y"] = jitter(cy)
# fixed coordinate for city-wide éclairage public
for s in SITES:
    if s["typo"] == "Éclairage public":
        s["x"], s["y"] = 2.11, 1.96


# --------------------------------------------------------------------------
# BATIMENTS
# --------------------------------------------------------------------------
BAT_HEADER = ["id_batiment", "id_site", "nom_site", "quartier", "typologie", "nom_batiment",
              "annee_construction", "annee_renovation", "sre_m2", "niveaux", "label",
              "logements", "ouverture", "x_km", "y_km", "remarque"]


def gen_batiments():
    rows = []
    for s in SITES:
        buildings = [(s["nom"], s["sre"], s["niveaux"])]
        # distribute sre across extra buildings: main building gets sre minus the extras
        if s["extra"]:
            extra_sre = sum(e[1] for e in s["extra"])
            buildings = [(s["nom"], max(0, s["sre"] - extra_sre), s["niveaux"])] + list(s["extra"])
        for bi, (nom_bat, sre, niv) in enumerate(buildings, 1):
            # for unheated sites sre stays 0 (empty)
            sre_out = "" if (s["sre"] in (0, None)) else fnum(sre)
            niv_out = "" if niv is None else fnum(niv)
            rows.append({
                "id_batiment": f"{s['id']}-B{bi}",
                "id_site": s["id"],
                "nom_site": s["nom"],
                "quartier": s["quartier"],
                "typologie": s["typo"],
                "nom_batiment": nom_bat if bi == 1 and not s["extra"] else nom_bat,
                "annee_construction": fnum(s["annee"]) if s["annee"] != "" else "",
                "annee_renovation": fnum(s["renov"]) if s["renov"] else "",
                "sre_m2": sre_out,
                "niveaux": niv_out,
                "label": s["label"],
                "logements": fnum(s["logements"]) if s["logements"] else "",
                "ouverture": "",
                "x_km": fnum(s["x"]),
                "y_km": fnum(s["y"]),
                "remarque": s["remarque"] if bi == 1 else "",
            })
    return rows


# --------------------------------------------------------------------------
# COMPTEURS + INSTALLATIONS
# --------------------------------------------------------------------------
CPT_HEADER = ["id_compteur", "id_site", "libelle", "fluide", "unite", "niveau", "mesure",
              "parent", "fournisseur_donnee", "releve", "debut", "fin"]
INST_HEADER = ["id_installation", "id_site", "type", "libelle", "vecteur", "puissance_kw",
               "mise_en_service", "retrait", "remarque"]

# heat meter templates: suffix -> (libelle, fluide, unite, niveau, mesure, fournisseur, releve)
HEAT_METER = {
    "GZ":  ("Gaz naturel", "gaz", "m3", "général", "consommation", "SIR", "automatique, mensuel"),
    "CAD": ("Chaleur à distance", "chaleur à distance", "kWh", "général", "consommation", "SIR", "automatique, mensuel"),
    "MZ":  ("Mazout (livraisons)", "mazout", "litre", "livraison", "livraison", "fournisseur de mazout", "bon de livraison"),
    "GR":  ("Granulés de bois (livraisons)", "bois (granulés)", "kg", "livraison", "livraison", "fournisseur de granulés", "bon de livraison"),
    "PAC": ("Électricité de la pompe à chaleur", "électricité", "kWh", "sous-compteur", "consommation", "commune", "automatique, mensuel"),
}

INST_BY_HEAT = {
    "GZ":  ("chaudiere_gaz", "Chaudière à gaz", "gaz"),
    "CAD": ("sous_station_cad", "Sous-station de chauffage à distance", "chaleur à distance"),
    "MZ":  ("chaudiere_mazout", "Chaudière à mazout", "mazout"),
    "GR":  ("chaudiere_granules", "Chaudière à granulés de bois", "bois"),
    "PAC_SOL": ("pac_sol_eau", "Pompe à chaleur sol-eau (sondes géothermiques)", "électricité"),
    "PAC_AIR": ("pac_air_eau", "Pompe à chaleur air-eau", "électricité"),
    "EL":  ("electrique_direct", "Chauffage électrique direct", "électricité"),
}

SUB_METER = {
    "EL-VENT":      "Électricité : Ventilation",
    "EL-FROID":     "Électricité : Groupe froid (glace)",
    "EL-BORNES":    "Électricité : Bornes de recharge",
    "EL-EAUBASSIN": "Électricité : Traitement de l'eau du bassin",
}


def boiler_power(s):
    base = {"GZ": 1, "CAD": 1, "MZ": 1, "GR": 1, "PAC": 1}
    kw = max(20, round((s["sre"] or 500) * random.uniform(0.07, 0.11) / 10) * 10)
    return min(900, kw)


def heat_commissioning(s):
    """Realistic heat-install commissioning date "YYYY-MM" in 2000-2025.

    Prefer the renovation year when it is a plausible install date, otherwise
    pick from the site's construction year clamped into [2000, 2024]. The
    build() function requires a valid YYYY-MM date, so this must never return
    a pre-2000 or out-of-range year.
    """
    candidates = []
    renov = s.get("renov")
    if isinstance(renov, int) and 2000 <= renov <= 2025:
        candidates.append(renov)
    annee = s.get("annee")
    if isinstance(annee, int):
        candidates.append(annee)
    year = candidates[0] if candidates else 2005
    # clamp pre-2000 construction years into a realistic retrofit window
    year = max(2000, min(2024, year))
    return f"{year}-{random.randint(1, 12):02d}"


def gen_compteurs_installations():
    cpt, inst = [], []
    for s in SITES:
        sid = s["id"]
        el_label = "Électricité des parties communes" if s["typo"] == "Logements communaux" else "Électricité, compteur général"
        inst_n = 0

        def add_inst(type_code, libelle, vecteur, power, mes, retrait="", remarque=""):
            nonlocal inst_n
            inst_n += 1
            inst.append({
                "id_installation": f"{sid}-I{inst_n}", "id_site": sid, "type": type_code,
                "libelle": libelle, "vecteur": vecteur, "puissance_kw": fnum(power) if power else "",
                "mise_en_service": mes, "retrait": retrait, "remarque": remarque,
            })

        # --- general electricity meter (always) ---
        cpt.append({"id_compteur": f"{sid}-EL", "id_site": sid, "libelle": el_label,
                    "fluide": "électricité", "unite": "kWh", "niveau": "général", "mesure": "soutirage",
                    "parent": "", "fournisseur_donnee": "SIR", "releve": "automatique, mensuel",
                    "debut": "", "fin": ""})

        # --- PV plant (+ injection meter) ---
        if s["pv"]:
            pv_start = f"{random.choice([2018, 2019, 2020, 2021, 2022, 2023])}-{random.randint(3, 9):02d}"
            s["pv_start"] = pv_start
            cpt.append({"id_compteur": f"{sid}-EL-INJ", "id_site": sid,
                        "libelle": "Électricité réinjectée au réseau", "fluide": "électricité",
                        "unite": "kWh", "niveau": "général", "mesure": "injection", "parent": "",
                        "fournisseur_donnee": "SIR", "releve": "automatique, mensuel",
                        "debut": pv_start, "fin": ""})
            cpt.append({"id_compteur": f"{sid}-PV", "id_site": sid,
                        "libelle": "Production photovoltaïque", "fluide": "électricité solaire",
                        "unite": "kWh", "niveau": "production", "mesure": "production", "parent": "",
                        "fournisseur_donnee": "commune (onduleur)", "releve": "automatique, mensuel",
                        "debut": pv_start, "fin": ""})
            add_inst("pv", "Installation photovoltaïque", "soleil", s["pv"], pv_start,
                     remarque="Puissance en kWc")

        # --- heat source ---
        heat = s["heat"]
        history = s.get("history")
        mes = heat_commissioning(s)
        if history:
            power = boiler_power(s)
            old_heat, old_end, new_heat, new_start = history
            # old source: meter (if metered) + retired installation
            if old_heat in HEAT_METER:
                _add_heat_meter(cpt, inst, s, old_heat, debut=mes, fin=old_end)
            old_type, old_lib, old_vec = INST_BY_HEAT[old_heat if old_heat != "PAC" else "PAC_AIR"]
            add_inst(old_type, old_lib, old_vec, boiler_power(s), mes, retrait=old_end)
            # new source: meter + installation
            if new_heat in HEAT_METER:
                _add_heat_meter(cpt, inst, s, new_heat, debut=new_start, fin="")
            new_type, new_lib, new_vec = INST_BY_HEAT[new_heat if new_heat != "PAC" else "PAC_AIR"]
            add_inst(new_type, new_lib, new_vec, power, new_start)
        elif heat == "EL":
            power = boiler_power(s)
            # electric direct heating: no separate meter, drawn on the main EL meter
            t, lib, vec = INST_BY_HEAT["EL"]
            add_inst(t, lib, vec, power, mes)
        elif heat == "PAC":
            power = boiler_power(s)
            _add_heat_meter(cpt, inst, s, heat, debut=mes, fin="")
            pac_variant = "PAC_SOL" if (s["sre"] or 0) >= 3000 else "PAC_AIR"
            t, lib, vec = INST_BY_HEAT[pac_variant]
            cop = random.choice(["3,8", "4,2", "4,5", "4", "3"])
            add_inst(t, lib, vec, power, mes, remarque=f"COP annuel visé {cop}")
            if s.get("want_chpac"):
                cpt.append({"id_compteur": f"{sid}-CH-PAC", "id_site": sid,
                            "libelle": "Chaleur produite par la pompe à chaleur", "fluide": "chaleur",
                            "unite": "kWh", "niveau": "mesure de chaleur", "mesure": "production",
                            "parent": "", "fournisseur_donnee": "commune",
                            "releve": "automatique, mensuel", "debut": mes, "fin": ""})
        elif heat:
            power = boiler_power(s)
            _add_heat_meter(cpt, inst, s, heat, debut=mes, fin="")
            t, lib, vec = INST_BY_HEAT[heat]
            add_inst(t, lib, vec, power, mes)

        # --- sub-meters ---
        for sub in s["subs"]:
            cpt.append({"id_compteur": f"{sid}-{sub}", "id_site": sid,
                        "libelle": SUB_METER[sub], "fluide": "électricité", "unite": "kWh",
                        "niveau": "sous-compteur", "mesure": "consommation", "parent": f"{sid}-EL",
                        "fournisseur_donnee": "commune", "releve": "automatique, mensuel",
                        "debut": "", "fin": ""})

        # --- water meter (most sites; unheated utility sites keep it too, except éclairage public) ---
        if s["typo"] != "Éclairage public":
            cpt.append({"id_compteur": f"{sid}-EAU", "id_site": sid,
                        "libelle": "Eau potable, compteur général", "fluide": "eau", "unite": "m3",
                        "niveau": "général", "mesure": "consommation", "parent": "",
                        "fournisseur_donnee": "SIR", "releve": "automatique, mensuel",
                        "debut": "", "fin": ""})

    return cpt, inst


def _add_heat_meter(cpt, inst, s, heat, debut, fin):
    sid = s["id"]
    lib, fluide, unite, niveau, mesure, fourn, releve = HEAT_METER[heat]
    parent = f"{sid}-EL" if heat == "PAC" else ""
    cpt.append({"id_compteur": f"{sid}-{heat}", "id_site": sid, "libelle": lib,
                "fluide": fluide, "unite": unite, "niveau": niveau, "mesure": mesure,
                "parent": parent, "fournisseur_donnee": fourn, "releve": releve,
                "debut": debut if debut and not debut.endswith("-00") else "", "fin": fin})


# mark two PAC sites to also carry a CH-PAC heat-output meter
_pac_sites = [s for s in SITES if s["heat"] == "PAC"]
for s in _pac_sites[:2]:
    s["want_chpac"] = True


# --------------------------------------------------------------------------
# MESURES
# --------------------------------------------------------------------------
MES_HEADER = ["mois", "id_compteur", "id_site", "fluide", "mesure", "valeur", "unite",
              "energie_kwh", "qualite"]


def heat_shape(mo):
    """Fraction of annual heating that falls in this month (from degree-days)."""
    return DJ[mo] / DJ_TOTAL * N_MONTHS / 5   # normalised so a flat year sums to ~12/yr weight


def solar_shape(mo):
    return RAD[mo] / RAD_TOTAL * N_MONTHS / 5


def energy_for_heat(s):
    """Target annual heat energy in kWh from SRE (specific demand kWh/m2/yr)."""
    typo = s["typo"]
    base = {
        "École primaire": 85, "École avec piscine": 110, "Administration": 90,
        "Crèche (EVE)": 95, "Maison de quartier": 100, "Salle communale": 95,
        "Bibliothèque": 80, "Salle de spectacle": 100, "Installation sportive": 110,
        "Piscine couverte": 320, "Patinoire": 180, "Voirie et ateliers": 90,
        "Caserne de pompiers": 95, "Logements communaux": 90,
    }.get(typo, 90)
    if s.get("label", "").startswith("Minergie"):
        base *= 0.6
    return (s["sre"] or 0) * base


def energy_for_elec(s):
    """Target annual electricity in kWh."""
    typo = s["typo"]
    base = {
        "École primaire": 22, "École avec piscine": 35, "Administration": 45,
        "Crèche (EVE)": 40, "Maison de quartier": 30, "Salle communale": 28,
        "Bibliothèque": 50, "Salle de spectacle": 55, "Installation sportive": 40,
        "Piscine couverte": 180, "Patinoire": 260, "Voirie et ateliers": 35,
        "Caserne de pompiers": 35, "Logements communaux": 18, "Parking souterrain": 60,
        "Abri PC": 8, "Cimetière": 12, "Éclairage public": 0,
    }.get(typo, 25)
    if typo == "Éclairage public":
        return 420000.0  # city-wide network, fixed
    if typo in ("Parking souterrain", "Abri PC", "Cimetière"):
        return base * 1000  # these have no SRE; use a flat figure
    return (s["sre"] or 300) * base


def water_for(s):
    """Target annual water in m3."""
    typo = s["typo"]
    base = {
        "École primaire": 0.18, "École avec piscine": 0.9, "Administration": 0.15,
        "Crèche (EVE)": 0.35, "Logements communaux": 0.55, "Piscine couverte": 2.5,
        "Patinoire": 0.6, "Installation sportive": 0.5,
    }.get(typo, 0.2)
    return max(60, (s["sre"] or 300) * base)


def yearly_trend(mo, rate):
    """Multiplier for a slight year-on-year efficiency trend."""
    y = int(mo[:4]) - START_YEAR
    return (1 + rate) ** y


def noise(pct=0.05):
    return 1 + random.uniform(-pct, pct)


def in_window(mo, debut, fin):
    if debut and mo < debut:
        return False
    if fin and mo > fin:
        return False
    return True


def gen_mesures(cpt):
    rows = []
    by_id = {c["id_compteur"]: c for c in cpt}
    site_by_id = {s["id"]: s for s in SITES}

    # anomaly bookkeeping
    anomalies = []

    for c in cpt:
        mid = c["id_compteur"]
        sid = c["id_site"]
        s = site_by_id[sid]
        fluide, mesure, unite = c["fluide"], c["mesure"], c["unite"]
        suffix = mid[len(sid) + 1:]
        releve = c["releve"]
        debut, fin = c["debut"], c["fin"]

        # ---- Delivery meters (mazout, granulés): 1-4 deliveries per year, autumn/winter ----
        if releve == "bon de livraison":
            annual = energy_for_heat(s)  # kWh/yr of heat covered by this fuel
            factor = MAZOUT_FACTOR if fluide == "mazout" else GRAN_FACTOR
            for y in range(START_YEAR, START_YEAR + 5):
                n_del = random.randint(2, 4)
                del_months = random.sample([1, 2, 3, 10, 11, 12, 9], n_del)
                total_units = annual * yearly_trend(f"{y}-01", -0.02) / factor
                shares = [random.uniform(0.7, 1.3) for _ in del_months]
                ssum = sum(shares)
                for mnum, sh in zip(sorted(del_months), shares):
                    mo = f"{y}-{mnum:02d}"
                    if not in_window(mo, debut, fin):
                        continue
                    units = round(total_units * sh / ssum)
                    kwh = round(units * factor)
                    rows.append([mo, mid, sid, fluide, mesure, fnum(units), unite, fnum(kwh), "mesuré"])
            continue

        # ---- Monthly meters ----
        if suffix == "EL" or suffix.startswith("EL-") and suffix != "EL-INJ" or suffix == "EL":
            kind = "elec"
        if suffix == "EL":
            kind = "elec_main"
        elif suffix == "EL-INJ":
            kind = "inj"
        elif suffix == "PV":
            kind = "pv"
        elif suffix == "EAU":
            kind = "water"
        elif suffix in ("GZ", "CAD", "PAC", "CH-PAC"):
            kind = "heat"
        elif suffix in SUB_METER:
            kind = "sub"
        else:
            kind = "elec"

        # annual target
        if kind in ("heat",):
            annual = energy_for_heat(s)
            if suffix == "PAC":
                annual = annual / 3.8     # electricity drawn = heat / COP
            elif suffix == "CH-PAC":
                annual = energy_for_heat(s)  # heat output
        elif kind == "elec_main":
            annual = energy_for_elec(s)
            # if there is a PAC, part of the electricity is on the sub-meter; keep EL as general
        elif kind == "pv":
            annual = (s["pv"] or 0) * 950  # ~950 kWh/kWp/yr
        elif kind == "inj":
            annual = (s["pv"] or 0) * 950 * 0.45  # ~45% injected
        elif kind == "water":
            annual = water_for(s)
        elif kind == "sub":
            frac = {"EL-VENT": 0.18, "EL-FROID": 0.45, "EL-BORNES": 0.12, "EL-EAUBASSIN": 0.25}.get(suffix, 0.15)
            annual = energy_for_elec(s) * frac
        else:
            annual = energy_for_elec(s)

        for i, mo in enumerate(MONTHS):
            if not in_window(mo, debut, fin):
                continue

            if kind == "heat":
                shape = heat_shape(mo)
                trend = yearly_trend(mo, -0.02)
            elif kind == "pv" or kind == "inj":
                shape = solar_shape(mo)
                trend = yearly_trend(mo, 0.0)
            elif kind == "water":
                # roughly flat, slight summer bump
                summer = 1.0 + 0.15 * math.cos((int(mo[5:7]) - 7) / 12 * 2 * math.pi) * -1
                shape = (1.0 / 12) * summer * N_MONTHS / 5
                trend = yearly_trend(mo, 0.0)
            else:
                # electricity: mild seasonal (slightly higher winter), flat-ish
                m = int(mo[5:7])
                seas = 1.0 + 0.12 * math.cos((m - 1) / 12 * 2 * math.pi)
                shape = (1.0 / 12) * seas * N_MONTHS / 5
                trend = yearly_trend(mo, -0.01)

            val_kwh = annual / 5 * shape * trend * noise()

            # convert kWh to the meter's raw unit + energy column
            if unite == "kWh":
                valeur = round(val_kwh)
                energie = valeur
            elif fluide == "gaz":
                f = GAS_FACTOR.get(mo, 11.1)
                valeur = round(val_kwh / f)
                energie = round(valeur * f)
            elif fluide == "eau":
                valeur = round(val_kwh)   # val_kwh here is really m3 target
                energie = ""
            else:
                valeur = round(val_kwh)
                energie = valeur

            if kind == "water":
                # water target 'annual' is in m3 already, not kWh
                valeur = max(1, round(annual / 5 * shape * trend * noise()))
                energie = ""

            rows.append([mo, mid, sid, fluide, mesure, fnum(valeur), unite, fnum(energie), "mesuré"])

    # ------------------------------------------------------------------
    # Inject deliberate anomalies
    # ------------------------------------------------------------------
    idx = {}
    for n, r in enumerate(rows):
        idx[(r[1], r[0])] = n

    def getrow(mid, mo):
        return rows[idx[(mid, mo)]] if (mid, mo) in idx else None

    # 1) DUPLICATE: G03-EL 2024-06 appears twice (same value)
    r = getrow("G03-EL", "2024-06")
    if r:
        rows.append(list(r))
        anomalies.append("duplicate: G03-EL 2024-06 (exact copy)")

    # 2) MISSING: G25-GZ has no row for 2021-05 and 2021-06
    removed = 0
    for mo in ("2021-05", "2021-06"):
        if ("G25-GZ", mo) in idx:
            rows[idx[("G25-GZ", mo)]] = None
            removed += 1
    if removed:
        anomalies.append("missing: G25-GZ 2021-05, 2021-06 (no row)")

    # 3) ESTIMATED: G40-EL 2023-05..2023-08 qualite=estimé
    est = []
    for mo in ("2023-05", "2023-06", "2023-07", "2023-08"):
        rr = getrow("G40-EL", mo)
        if rr:
            rr[8] = "estimé"
            est.append(mo)
    if est:
        anomalies.append(f"estimated: G40-EL {', '.join(est)} (qualite=estimé)")

    # 4) NEGATIVE: G13-GZ 2022-03 negative value
    rr = getrow("G13-GZ", "2022-03")
    if rr:
        f = GAS_FACTOR.get("2022-03", 11.1)
        rr[5] = "-1800"
        rr[7] = fnum(round(-1800 * f))
        anomalies.append("negative: G13-GZ 2022-03 (valeur=-1800)")

    # 5) SPIKE: G22-GZ 2022-11 ~8x normal
    rr = getrow("G22-GZ", "2022-11")
    if rr:
        f = GAS_FACTOR.get("2022-11", 11.1)
        base_v = float(rr[5]) if rr[5] else 2000
        spike_v = round(base_v * 8)
        rr[5] = fnum(spike_v)
        rr[7] = fnum(round(spike_v * f))
        anomalies.append("spike: G22-GZ 2022-11 (~8x normal)")

    # 6) ZERO-RUN: G35-PV 2023-06, 2023-07 = 0 (other years have real values)
    zr = []
    for mo in ("2023-06", "2023-07"):
        rr = getrow("G35-PV", mo)
        if rr:
            rr[5] = "0"
            rr[7] = "0"
            zr.append(mo)
    if zr:
        anomalies.append(f"zero_run: G35-PV {', '.join(zr)} (0 kWh)")

    rows = [r for r in rows if r is not None]
    return rows, anomalies


# --------------------------------------------------------------------------
# REF-TYPOLOGIES (recomputed from the generated buildings)
# --------------------------------------------------------------------------
REFT_HEADER = ["code", "typologie", "sites", "sre_m2"]


def gen_ref_typologies(bat_rows):
    # per typology: count distinct sites, sum sre over buildings
    sites_by_typo = {}
    sre_by_typo = {}
    order = []
    for r in bat_rows:
        typo = r["typologie"]
        if typo not in sites_by_typo:
            sites_by_typo[typo] = set()
            sre_by_typo[typo] = 0
            order.append(typo)
        sites_by_typo[typo].add(r["id_site"])
        sre = int(r["sre_m2"]) if r["sre_m2"] else 0
        sre_by_typo[typo] += sre
    rows = []
    for typo in order:
        rows.append({
            "code": TYPO_CODE[typo],
            "typologie": typo,
            "sites": fnum(len(sites_by_typo[typo])),
            "sre_m2": fnum(sre_by_typo[typo]),
        })
    return rows


# --------------------------------------------------------------------------
# Write helpers
# --------------------------------------------------------------------------
def write_csv(name, header, rows):
    path = CSV_DIR / f"geneve-{name}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        for r in rows:
            if isinstance(r, dict):
                w.writerow([r.get(h, "") for h in header])
            else:
                w.writerow(r)
    return path


def main():
    bat = gen_batiments()
    cpt, inst = gen_compteurs_installations()
    mes, anomalies = gen_mesures(cpt)
    reft = gen_ref_typologies(bat)

    write_csv("batiments", BAT_HEADER, bat)
    write_csv("compteurs", CPT_HEADER, cpt)
    write_csv("installations", INST_HEADER, inst)
    write_csv("mesures", MES_HEADER, mes)
    write_csv("ref-typologies", REFT_HEADER, reft)

    print("Geneva fake dataset written to", CSV_DIR)
    print(f"  sites        : {len(SITES)}")
    print(f"  buildings    : {len(bat)}")
    print(f"  meters       : {len(cpt)}")
    print(f"  installations: {len(inst)}")
    print(f"  measurements : {len(mes)}")
    print(f"  typologies   : {len(reft)}")
    print("  anomalies injected:")
    for a in anomalies:
        print("    -", a)


if __name__ == "__main__":
    main()
