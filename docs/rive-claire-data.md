# Rive-Claire dataset (organisers, v2, 6 Nov 2026)

Fictional commune of 25,000 inhabitants, 5 neighbourhoods (Centre, Les Crêts, Bois-Joli, Prés-Verts, La Gravière).
Sites and readings are simulated; the climate is real (Genève-Cointrin). Licence **CC BY 4.0**: may be published, cite
« Energ-IA Transition, Energ-IACK 2026 ». Source: `ENERG-IACK26-kDrive-OpenData/02-Defis-Données/1-Donnees-Rive-Claire/`
(git-ignored). The 11 CSV are a base64 zip inside `EIAK-RC-Guide-Donnees-vf.html`; the Excel workbook has the same tables.
CSV: UTF-8 with BOM, `;` separator, decimal point, months as text `YYYY-MM`.

## Scale
48 sites (50 building rows), 111,540 m² heated area (SRE), 64 installations, 172 meters, 9,437 monthly rows,
60 months (Jan 2021 → Dec 2025). PV grows from 425 to 955 kWp. Electricity and gas, water and district heat come from the
fictional utility SIR; oil and pellets from private suppliers.

## The four main tables
| Table | Rows | Key columns |
|---|---|---|
| `batiments` | 50 | `id_batiment`, `id_site`, `nom_site`, `quartier`, `typologie`, `annee_construction`, `annee_renovation`, `sre_m2`, `niveaux`, `label` (Minergie…), `logements`, `ouverture`, `x_km`/`y_km` (fictional plan position) |
| `installations` | 64 | `id_site`, `type`, `vecteur`, `puissance_kw` (kWp for PV), `mise_en_service`, `retrait` |
| `compteurs` | 172 | `id_compteur` (= site + code), `fluide`, `unite`, `niveau`, `mesure`, `parent`, `releve`, `debut`/`fin` |
| `mesures` | 9,437 | `mois`, `id_compteur`, `id_site`, `fluide`, `mesure`, `valeur`, `unite`, `energie_kwh` (empty for water), `qualite` |

Site types: 8 primary schools + 1 school with pool, 6 nurseries, 10 municipal housing blocks, 3 admin, 3 community houses,
2 halls, library, theatre, 4 sports sites, indoor pool, ice rink, works depot, fire station, 2 civil-defence shelters,
cemetery, underground car park (SRE 0), street lighting (SRE 0).

## Meter codes
| Code | Measures | Unit | Count |
|---|---|---|---|
| EL | electricity drawn from grid (main meter) | kWh | 48 |
| EL-INJ | electricity fed back to grid (same meter, 2nd register) | kWh | 12 |
| PV | solar production | kWh | 12 |
| GZ | natural gas | m³ | 21 |
| CAD | district heat | kWh | 10 |
| MZ | heating oil, **deliveries only** | litre | 7 |
| GR | wood pellets, deliveries only | kg | 1 |
| PAC | electricity used by a heat pump (sub-meter of EL) | kWh | 7 |
| CH-PAC | heat produced by a heat pump | kWh | 2 |
| EL-VENT / EL-FROID / EL-BORNES / EL-EAUBASSIN | electric sub-meters (ventilation, ice-rink cooling, EV chargers, pool water) | kWh | 6 |
| EAU | water | m³ | 46 |

Readings: 164 series automatic monthly, 8 from delivery notes.

## Reference tables
- `ref-climat` (60 months: temperature, heating degree-days 20/12, radiation, sunshine) and `ref-climat-normale` (1991–2020 by month).
- `ref-conversion`: gas factor per month (≈ 10.9–11.3 kWh/m³, gross/PCS); oil 10 kWh/l; pellets 4.9 kWh/kg (net/PCI).
- `ref-co2`: gas 2.086 kg/m³, oil 2.65 kg/l, pellets 0 (biogenic); electricity and district heat 0 *on-site scope only*.
- `ref-typologies` (18 types with SRE), `ref-vecteurs` (fuel → conversion/CO₂ mapping), `dictionnaire` (meaning of every column).

## Calculation rules (from the dictionary)
- On-site electricity use = EL + PV − EL-INJ. Sub-meters are already inside EL (a sub-meter may exceed EL).
- Gas is in gross kWh (PCS), oil and pellets in net (PCI): gas × 0.90 ≈ PCI for comparison.
- Oil/pellets: consumed = delivered + start stock − end stock; stocks unknown, so a month without delivery = unknown use.
- Ratios per m²: sum SRE of buildings open at that date; SRE 0 → "not applicable". Housing electricity = common parts only.
- `id_compteur` + `mois` should be unique for monthly series: check duplicates before summing.

## Changes over the period (installations)
S01 Mairie gas → district heat (Jul 2024) · S04 École du Centre oil → ground heat pump + PV (Sep 2022; Aug 2022 heat source unknown)
· S07 PV (Jun 2023) · S18 new nursery with heat pump + PV (opens Aug 2023) · S26 PV (May 2021) · S28 oil → air heat pump (Jun 2024)
· S32 PV + EV chargers (Apr 2022) · S39 oil → gas (Aug 2023) · S47 EV chargers (Mar 2023).

## Deliberate defects found so far
- Duplicate: S03-EL 2024-06 (two identical rows, 2011 kWh).
- Missing: S25-GZ 2021-05 and 2021-06; S44-EL 2023-11.
- Estimated (by the utility): S40-EL 2023-05 → 2023-08, flat 1623 kWh.
- Likely more (drifts, leaks, unit or level traps, e.g. gas and water both in m³): not analysed yet.

## In the app
Imported on 13 Nov by `tools/import_rive_claire.py` into `prototype/data.json` (replaced our earlier simulation).
All four defects above are flagged on the site page; S04's August 2022 (no heating system) too.
