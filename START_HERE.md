# Start here

Five minutes to know what openEDM is, what works, how to run it and where to go next. Details live in the files
linked below; this page only points to them. Last refreshed: 15 Nov 2026.

## What it is

openEDM is an open-source Energy Data Management tool (EDM) that a commune owns: its energy readings in an open
format, readable code, a static site or its own server. Built at the Energ-IACK hackathon (Geneva, 13–14 Nov 2026,
challenge 2 « EDM citoyen et souverain »); next presentation **1 Dec 2026**.

Users: the commune's energy manager first (Manage, site pages, data quality, imports), plus a public page for
residents (Citizens) and a 3D map. Data: the organisers' **fictional** commune Rive-Claire, plus public Geneva
building data (SITG, swisstopo). Nothing confidential, ever (see "Rules" in `CLAUDE.md`).

- **Server version (main link):** https://openedm.davidcarvalho.work/ (logins, roles, several municipalities;
  "Log in" shows one-click demo accounts)
- **Static copy:** https://dcarvalh.github.io/energiack-edm/ (GitHub Pages, no login; uploading data and managing
  municipalities need the server version, and those pages say so)

## Done and not done

| | |
|---|---|
| **Done** | Manage (KPIs, monthly chart, CO₂ path to 2030, site table with alerts), site pages with every meter, Citizens, data quality report (17 checks), 3D maps (Rive-Claire, Geneva), FR/EN, logins and 4 roles, several municipalities, ZIP import through a staging area, Genève (démo): real Geneva buildings with simulated readings, linked to their building sheets on the map, pitch deck |
| **Not done** | council summary (#10), hand-over pack (#11), weather-corrected heat, traced manual corrections, public-data view for a municipality without readings, deploys on merge (the server is updated by hand), password reset |

The full state table is in `plan.md` › "State"; the ordered to-do list in `plan.md` › "To do".

## Run it in 5 minutes

```bash
python3 -m http.server 8000 -d prototype      # static app: open http://127.0.0.1:8000/
```

With the database and logins (Docker):

```bash
cp .env.example .env            # set POSTGRES_PASSWORD; DEMO_LOGIN=1 for one-click demo accounts
docker compose up -d --build    # open http://127.0.0.1:8088/
```

Checks: `README.md` › "Run it locally" and "Working together"; the server, hosting and backups: `docs/deploy.md`.

## Where the code lives

| Part | Where |
|---|---|
| The whole web app (one file; every string in `T.fr` / `T.en`) | `prototype/index.html` |
| 3D map | `prototype/map3d.js`; map data in `prototype/map-rc/` (Rive-Claire), `prototype/map/` (Geneva) |
| Data format and the import (single source of `data.json`) | `tools/import_rive_claire.py` › `build()` |
| API, database, roles | `server/` (`app.py`, `store.py`, `auth.py`, `schema.sql`) and `compose.yaml` |
| Map builders | `tools/make_rive_claire_map.py`, `tools/make_map.py` |
| Checks (also run on every pull request) | `tools/check_page.py`, `tools/check_roles.py`, `tools/check_stack.sh`, `tools/check_upgrade.sh` |
| The dataset and its defects | `rive-claire/`, `docs/rive-claire-data.md` |
| Licences of everything not ours | `THIRD_PARTY.md` |

A file-by-file list: `README.md` › "Files".

## How to contribute

One branch per change from an up-to-date `main`, a pull request with the template filled in, squash-merge when the
checks pass. Ideas and bugs: GitHub issues. Team rules (data, FR/EN, URLs, cache numbers): `CLAUDE.md`.

## Next steps

`plan.md` › "To do": "Now" in order, then "Before 1 Dec", then "Later / ideas". Decisions already taken are in
`plan.md` › "Decisions" and under "Public base layer".
