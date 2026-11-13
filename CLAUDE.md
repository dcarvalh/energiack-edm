# energiack-edm: **openEDM**, Energ-IACK hackathon, Défi 2 « EDM citoyen et souverain »

Public repo. Live at https://dcarvalh.github.io/energiack-edm/ (GitHub Pages, deployed from `prototype/` on every push to `main`).
What it does and how to run it: `README.md`. Team plan, decisions and next steps: `plan.md`. Dataset notes: `docs/rive-claire-data.md`.

## Rules
- **Public repo: only public or fictional data.** Data received under confidentiality at the event (partner APIs, real
  municipal cases) never goes into git, the site, or an AI service without the owner's OK.
- **FR and EN are a must.** Every visible string goes through the `T.fr` / `T.en` dictionaries in `prototype/index.html`
  (`map3d.js` uses the same `t()`). `tools/check_page.py` fails if the two key sets differ.
- Simple, minimalist, modern. Don't add features nobody asked for; list ideas in `plan.md` instead.
- Users: the commune's energy manager first, plus a public citizen page.
- Costs are assumed prices, labelled "estimated". CO₂ = the dataset's factors (direct on-site). Simulated values are flagged on screen.
- New third-party code or data: add it to `THIRD_PARTY.md` with its licence.

## How to work
- Plan first, then small steps; validate each one.
- Before pushing: serve `prototype/` locally and run `tools/check_page.py http://127.0.0.1:PORT/` (screenshots in `shots/`).
  Check FR/EN and phone width. Say what was not verified.
- The site is served under `/energiack-edm/`: keep every URL in the app relative (no leading `/`).
- After changing data or JS, bump the cache constants: `const V` in `prototype/index.html` and `const V` in `prototype/map3d.js`.

## Map (3D tab)
- Two maps: Rive-Claire (`prototype/map-rc/`, `tools/make_rive_claire_map.py`, default) and Geneva (`prototype/map/`,
  `tools/make_map.py`). Same schema; `map3d.js` branches on `cfg.key === "rc"`. `initMap` returns `destroy()` for the switch.
- Never build straight into `prototype/`: `--out` a scratch folder, test it, then copy.
- three.js 0.160.0 and three-mesh-bvh 0.7.6 vendored in `prototype/vendor/`. BVH keeps hover picking fast on 10k buildings.
  `OrbitControls.js` only exports `OrbitControls`. Headless 3D needs `--use-angle=swiftshader --enable-unsafe-swiftshader`.
- SITG values are French only: English labels live in the `EN` table in `map3d.js`.
- SITG `CAD_BATIMENT_HORSOL.hauteur` = height above ground (m). IDC `indice` is MJ/m²·yr (÷3.6 = kWh/m²); keep the latest
  year per building. Boiler fuel "HEL" = heating oil. Classify heat pump/wood before district heating ("PAC - Comptage de
  chaleur" contains "chaleur"). 450 MJ/m²·yr is Geneva's IDC threshold in the energy regulation (REn, amended 13 Apr 2022; > 800 = significant
  exceedance; from a search of ge.ch documents, consolidated text not checked). Our heat index only approximates the official IDC (different method): say "approximate" next to it.
- swisstopo: STAC `data.geo.admin.ch/api/stac/v0.9` (swissALTI3D), WMS `wms.geo.admin.ch` (SWISSIMAGE). All LV95 / EPSG:2056.
