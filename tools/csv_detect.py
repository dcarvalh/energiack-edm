"""Identify which openEDM dataset a CSV belongs to from its column headers alone.

detect(columns) -> (table_name | None, confidence 0-1, human_label | None)
"""

# Minimal set of columns that uniquely identify each table (lowercase, no BOM).
# Score = fraction of signature columns present in the file.
SIGNATURES = {
    "batiments":          frozenset({"id_batiment",    "id_site", "sre_m2"}),
    "installations":      frozenset({"id_installation","id_site", "vecteur"}),
    "compteurs":          frozenset({"id_compteur",    "id_site", "releve", "debut", "fin"}),
    "mesures":            frozenset({"mois",            "id_compteur", "valeur", "energie_kwh", "qualite"}),
    "ref-climat":         frozenset({"mois",            "ensoleillement_h", "degres_jours_20_12"}),
    "ref-climat-normale": frozenset({"mois_calendaire", "degres_jours_20_12"}),
    "ref-typologies":     frozenset({"code",            "typologie", "sites"}),
    "ref-co2":            frozenset({"vecteur",         "kg_co2_par_kwh"}),   # actual column name
    "ref-conversion":     frozenset({"vecteur",         "mois", "facteur"}),
    "ref-vecteurs":       frozenset({"fluide_mesures",  "vecteur_conversion"}),
}

LABELS = {
    "batiments":          "Bâtiments",
    "installations":      "Installations",
    "compteurs":          "Compteurs",
    "mesures":            "Mesures",
    "ref-climat":         "Réf. climat",
    "ref-climat-normale": "Réf. climat normales",
    "ref-typologies":     "Réf. typologies",
    "ref-co2":            "Réf. CO₂",
    "ref-conversion":     "Réf. conversions",
    "ref-vecteurs":       "Réf. vecteurs",
}

THRESHOLD = 0.7   # minimum fraction of signature columns required


def detect(columns: list[str]) -> tuple[str | None, float, str | None]:
    """Return (table_name, confidence, label). table_name is None if below threshold."""
    cols = {c.strip().lstrip("﻿").lower() for c in columns if c.strip()}
    best_name, best_score = None, 0.0
    for name, sig in SIGNATURES.items():
        score = len(sig & cols) / len(sig)
        if score > best_score:
            best_name, best_score = name, score
    if best_score < THRESHOLD:
        return None, round(best_score, 2), None
    return best_name, round(best_score, 2), LABELS.get(best_name)
