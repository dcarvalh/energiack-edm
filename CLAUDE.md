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
- Never push to `main` (protected; merging deploys the live site). One branch per change (`feat/<name>` or `fix/<name>`,
  from an up-to-date `main`), then a PR into `main` that fills in the PR template; squash-merge once the check passes.
  Link the issue (`Closes #N`) when there is one. Ideas and bugs from the team arrive as GitHub issues.
- Before the PR: serve `prototype/` locally and run `tools/check_page.py http://127.0.0.1:PORT/` (screenshots in `shots/`).
  Check FR/EN and phone width. Say what was not verified.
- Pitch video: `.venv/bin/python tools/record_video.py --lang fr` (storyboard = `SHOTS` in that file; output in the
  git-ignored `video-out/`). The recorder captures the browser's frames over CDP because Playwright's own
  recorder is limited to the CSS viewport size.
- **Pitch deck** = `prototype/pitch/index.html`, live at `/pitch/` (README › Pitch deck). Decided 14 Nov: French only,
  silent, light, clicked through live; a title slide (not numbered) + 6 slides, one `<section class="slide">` each;
  short text (summarise, cut minor bullets); app clips only where the storyboard asks for one; slide 1's animations
  play once, clips loop. The folder must stay self-contained (own `fonts/`, `clips/`, no `../` URL) so it opens from
  disk offline: test with the network off. Clips (16:9 when two are stacked, 4:3 alone) are the only media committed;
  record `access` on the server version with `--url` and the demo logins. The Geneva map renders at about 3 fps on a machine
  without a GPU, so its raw recording stops and starts: the clip was repaired with ffmpeg, not re-recorded (drop
  repeated frames, `minterpolate` to a high rate from a numbered image sequence, pick frames at even distance,
  forward then backward for the loop). Headless Chromium cannot play H.264: a
  screenshot shows the poster frame, so say clips were not seen playing. "Energo" and the team's first names are
  allowed on the deck (David, 14 Nov).
- The site is served under `/energiack-edm/`: keep every URL in the app relative (no leading `/`).
- After changing data or JS, bump the cache constants: `const V` in `prototype/index.html` and `const V` in `prototype/map3d.js`.

## Server stack (`compose.yaml`, `server/`)
- PostgreSQL + FastAPI + Caddy. The API rebuilds `data.json` with `build()` from `tools/import_rive_claire.py`: keep
  that function the single source of the format, so the static site and the server never drift.
- `tools/check_stack.sh` (also run by the Stack workflow on every PR) must pass: `data.json` from the database equals the
  static build, a re-import adds 0 rows, every role gets what it should. Hosting and deploys: `docs/deploy.md`. Never commit `.env`.
- Roles (issue #15: admin, technique, elu, public): `server/auth.py` decides, the API enforces it on the data (no raw
  readings or quality report below `technique`); `ACCESS` in `prototype/index.html` only hides menus and must mirror it.
  Change both together. On a static host `prototype/api/config.json` (`{"server": false}`) keeps every page open, no login.
- UI checks on a running stack: `tools/check_roles.py <url>` and `CHECK_ROLE=technique tools/check_page.py <url>`;
  in static mode `tools/check_page.py` as before.

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
