# Third-party code and data

The project's own code is under the MIT licence (`LICENSE`). Everything below keeps its own licence.

## Data

| What | Where in the repo | Source | Licence / attribution |
|---|---|---|---|
| Rive-Claire dataset (fictional commune: sites, buildings, installations, meters, monthly readings 2021–2025) | `prototype/data.json`, `prototype/map-rc/` (derived by `tools/import_rive_claire.py`, `tools/make_rive_claire_map.py`) | Energ-IACK 2026 organisers | **CC BY 4.0**, « Energ-IA Transition, Energ-IACK 2026 » |
| Geneva buildings, heat index (IDC), boilers, solar potential | `prototype/map/buildings.json` (derived by `tools/make_map.py`) | SITG, Système d'information du territoire à Genève (ge.ch/sitg) | SITG open data, « © SITG » |
| Terrain (swissALTI3D) and aerial photo (SWISSIMAGE) | `prototype/map/` | swisstopo, Federal Office of Topography | Free geodata (OGD), « © swisstopo » |

Electricity and water per building on the Geneva map are **simulated** (flagged `sim` in the data and on screen).
Costs in CHF are **assumed prices**, not in the dataset, and labelled "estimated" in the app.

## Code (vendored in `prototype/vendor/`, unmodified)

| Library | Version | Licence |
|---|---|---|
| three.js (`three.module.min.js`) | 0.160.0 | MIT, © 2010–2023 three.js authors |
| three.js `OrbitControls.js` (from `examples/jsm/controls`) | 0.160.0 | MIT, © three.js authors |
| three-mesh-bvh (`three-mesh-bvh.module.js`) | 0.7.6 | MIT, © Garrett Johnson |

Python tools use only the standard library plus `requirements.txt` (Playwright for the headless check; numpy, Pillow,
rasterio for the Geneva map build).
