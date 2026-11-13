# Energ-IACK 2026 · Défi 2 « EDM citoyen et souverain »

An Energy Data Management tool (EDM) that a commune **owns**: open data format, readable code, runs on any static host,
and the same format lets communes compare and share. Built at the Energ-IACK hackathon, Geneva, 13–14 Nov 2026.

**Live demo: https://dcarvalh.github.io/energiack-edm/** (FR/EN toggle top right, also `?lang=en`)

## What it shows

| View | For whom | What |
|---|---|---|
| **Accueil / Welcome** | everyone | the challenge in short, what is online, next steps |
| **Gestion / Manage** | the commune's energy service | KPIs (energy, estimated cost, CO₂ vs 2030 target, fossil-heated sites, solar), monthly chart by fluid, CO₂ trajectory to 2030, site table with alerts incl. data defects. A site page has its monthly history per fluid, every meter with raw readings and quality flags, buildings, installations, heating history and a CSV download |
| **Citoyen·ne·s / Citizens** | residents | the year in one sentence, progress to the 2030 targets, numbers per resident, what changed |
| **Carte 3D / 3D map** | everyone | **Rive-Claire** (default): the challenge's fictional commune as schematic 3D blocks coloured by measured 2025 readings; scenery (lake, roads, trees) is generated. **Geneva**: 10,574 real buildings in central Geneva (SITG footprints and heights) on swisstopo terrain and aerial photo, coloured by heat index, heating energy, solar potential (real) or electricity and water (simulated, flagged) |
| **Comment ça marche / How it works** | jury, other communes | why sovereign, the Geneva context with sources, the open data model |

Data: the organisers' fictional **Rive-Claire** dataset (CC BY 4.0): 48 sites, 50 buildings, 64 installations, 172 meters,
9,437 monthly readings 2021–2025. Rules applied from the dataset's dictionary: on-site electricity = EL + PV − EL-INJ;
heat = gas × 0.90 (gross → net) + district heat + oil + pellets; oil and pellets are deliveries; duplicate readings: first kept.
CO₂ = the dataset's factors (direct on-site emissions, so electricity and district heat count 0). Costs use **assumed**
prices, labelled "estimated". Licences and attributions: `THIRD_PARTY.md`.

## Run it locally

No build step, no framework, no external requests: `prototype/` is the whole app.

```bash
python3 -m http.server 8000 -d prototype     # then open http://127.0.0.1:8000/
```

Pushing to `main` deploys to GitHub Pages (`.github/workflows/pages.yml` publishes `prototype/`).

## Files

```
prototype/index.html    the whole app (one file); every visible string in the T.fr / T.en dictionaries
prototype/data.json     the dataset, in the open format described on the "How it works" page
prototype/map3d.js      the 3D map (three.js + three-mesh-bvh, vendored in prototype/vendor/, loaded only when the tab opens)
prototype/map-rc/       Rive-Claire map data      prototype/map/   Geneva map data (≈ 13 MB)
tools/import_rive_claire.py    builds data.json from the organisers' Rive-Claire guide
tools/make_rive_claire_map.py  builds prototype/map-rc/ from the same guide (--out/--scale/--year)
tools/make_map.py       builds prototype/map/ from SITG + swisstopo (--box/--out/--step/--px/--tiles)
tools/check_page.py     headless browser check: all views, FR/EN, desktop/phone, light/dark, JS errors, overflow
docs/research.md        what Geneva has today, with sources
rive-claire/            the Rive-Claire dataset as published by the organisers (guide, workbook, CSV tables)
docs/rive-claire-data.md  the Rive-Claire dataset: tables, rules, known defects
plan.md                 team plan, decisions, next steps
```

The two Rive-Claire tools read the organisers' guide from `rive-claire/` (the dataset, CC BY 4.0, with its CSV tables).
Set up the tools:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
.venv/bin/python tools/import_rive_claire.py
.venv/bin/python tools/check_page.py http://127.0.0.1:8000/
```

## Rule for contributors

Only public or fictional data goes in this repo and on the site. Data received under confidentiality at the event
(partner APIs, real municipal cases) stays on your own machine and never in git.
