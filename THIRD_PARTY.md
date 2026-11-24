# Third-party code and data

The project's own code is under the MIT licence (`LICENSE`). Everything below keeps its own licence.

## Data

| What | Where in the repo | Source | Licence / attribution |
|---|---|---|---|
| Rive-Claire dataset (fictional commune: sites, buildings, installations, meters, monthly readings 2021–2025) | `rive-claire/` (original guide, workbook and CSV, unmodified); `prototype/data.json`, `prototype/map-rc/` (derived by `tools/import_rive_claire.py`, `tools/make_rive_claire_map.py`) | Energ-IACK 2026 organisers | **CC BY 4.0**, « Energ-IA Transition, Energ-IACK 2026 » |
| Geneva buildings, official addresses, heat index (IDC), boilers, solar potential (SITG layers `CAD_BATIMENT_HORSOL`, `CAD_ADRESSE`, `SCANE_INDICE_MOYENNES_3_ANS`, `SCANE_CHAUDIERE`, `OCEN_SOLAIRE_PV_BATIMENT`; extracted Nov 2026) | `prototype/map/buildings.json` (derived by `tools/make_map.py`: filtered, joined by EGID, latest heat index per building) | SITG, Système d'information du territoire à Genève (sitg.ge.ch) | Level « A - Accès libre » (open data, commercial use allowed; checked on each layer's catalogue page, 15 Nov 2026). The [terms](https://sitg.ge.ch/ressources/conditions-utilisation-donnees) require the source, the extraction date and the processing done: on screen « Données SITG (extraction nov. 2026), traitées par openEDM » |
| Terrain (swissALTI3D) and aerial photo (SWISSIMAGE) | `prototype/map/` | swisstopo, Federal Office of Topography | Free geodata (OGD). The [terms](https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices) require a source line; « © swisstopo » is one of the accepted forms (checked 15 Nov 2026) |
| Imported 3D maps: buildings + EGID (GWR), terrain (swissALTI3D), aerial (SWISSIMAGE) | fetched at import by `tools/fetch_swiss_map.py`, stored per locality | swisstopo / BFS, geo.admin.ch | Free geodata (OGD), « © swisstopo / BFS » |
| Imported 3D maps: building footprints (optional, when enabled) | same | OpenStreetMap contributors | **ODbL**, « © OpenStreetMap contributors » — must be shown wherever the map is displayed |
| Imported 3D maps (France): buildings + RNB id (BD TOPO), aerial (BD ORTHO), terrain (RGE ALTI) | fetched at import by `tools/fetch_france_map.py`, stored per locality | IGN Géoplateforme (data.geopf.fr) | Open licence (Etalab / Licence Ouverte), « © IGN / Géoplateforme » |
| French place search in the 3D-map import dialog (place name → zone) | queried live by `tools/fetch_swiss_map.py` (`geocode`), nothing stored | Base Adresse Nationale (api-adresse.data.gouv.fr) | Licence Ouverte / Etalab 2.0 |

Electricity and water per building on the Geneva map are **simulated** (flagged `sim` in the data and on screen).
Costs in CHF are **assumed prices**, not in the dataset, and labelled "estimated" in the app.

## Code (vendored in `prototype/vendor/`, unmodified)

| Library | Version | Licence |
|---|---|---|
| three.js (`three.module.min.js`) | 0.160.0 | MIT, © 2010–2023 three.js authors |
| three.js `OrbitControls.js` (from `examples/jsm/controls`) | 0.160.0, wheel-zoom fix patched in | MIT, © 2010–2023 three.js authors (the repo's licence covers the examples) |
| three-mesh-bvh (`three-mesh-bvh.module.js`) | 0.7.6 | MIT, © 2018 Garrett Johnson |
| Inter variable font, latin subset (`fonts/inter-latin-wght-normal.woff2`, also copied with its licence text to `prototype/pitch/fonts/` so the deck folder works on its own; from the `@fontsource-variable/inter` npm package) | 5.3.0 | SIL Open Font License 1.1, © 2016 The Inter Project Authors (licence text in `fonts/Inter-OFL.txt`) |

## Icons (inlined in `prototype/index.html`)

| What | Version | Licence |
|---|---|---|
| Lucide icons (path data of 22 icons, `ICONS` in `index.html`, from the `lucide-static` npm package) | 1.72.0 | ISC, © Lucide Icons and Contributors |

## Server stack (`compose.yaml`, `server/`; not part of the static site)

Installed or pulled at build time, nothing vendored in the repo.

| What | Version | Licence |
|---|---|---|
| PostgreSQL (`postgres:18-alpine` image) | 18 | PostgreSQL Licence |
| Caddy (`caddy:2-alpine` image) | 2 | Apache-2.0 |
| Python (`python:3.13-alpine` image) | 3.13 | PSF Licence |
| FastAPI | 0.162.7 | MIT |
| Uvicorn | 0.54.0 | BSD-3-Clause |
| psycopg (with `psycopg-binary`) | 3.3.9 | LGPL-3.0 (used as an unmodified library) |
| python-multipart (file uploads) | 0.0.20 | Apache-2.0 |

Licences above checked on 15 Nov 2026 against the npm and PyPI registries and the upstream `LICENSE` files (the vendored
three-mesh-bvh and OrbitControls files carry no header).

Python tools use only the standard library plus `requirements.txt` (Playwright, Apache-2.0, for the headless check;
numpy, BSD-3-Clause, Pillow, MIT-CMU, rasterio, BSD-3-Clause, for the Geneva map build; segno, BSD-3-Clause, made
the QR code SVGs; imageio-ffmpeg, BSD-2-Clause, for the pitch video: its package ships an FFmpeg binary
built with GPL parts (x264), used as a separate program and not redistributed here).
