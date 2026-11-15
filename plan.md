# Team plan · openEDM (Défi 2 « EDM citoyen et souverain »)

Updated 15 Nov 2026. What exists and how to run it: `README.md`. What is left: see "To do for 1 Dec" below.

## Deadlines
- Hackathon pitch: done, Sat 14 Nov (deliverables in by 14:00: prototype, code with `THIRD_PARTY.md`, slides, project sheet).
- **The project goes on. Next presentation: Tue 1 Dec 2026.** Aim: more polished and easier to use (what that means
  exactly is still to decide, see "To do for 1 Dec" › Decide first).
- Pitch format so far: about 5 minutes, **tell a story**, don't list features.

## The pitch in one line
An EDM a commune owns: one open-source codebase for every commune, open data format, runs on its own server or shared
hosting, and it **complements** existing tools as an aggregator instead of replacing them.

## Decisions (team meeting, 13 Nov)
- The public demo uses only the fictional Rive-Claire data. Real partner data stays off the public site and out of this repo.
- First user story: **load the Rive-Claire data with a quality and consistency report** (duplicates, wrong IDs, formats, gaps).
- Targets can only be changed by an identified, authorised person.
- Repo public under MIT (code) with a data notice; hosted on GitHub Pages.
- Name: **openEDM** (13 Nov). The repo name and Pages URL stay as they are.
- The import must be repeatable (re-running it never duplicates records) and list every rejected row with its reason.
  Reference data (buildings, meters, installations) is kept apart from monthly readings.
- Equipment comes from the installations table, never inferred from consumption.
- Indicator choices (David, 13 Nov):
  1. Heat-pump heat at the 5 sites without a heat meter: pump electricity × COP measured at S09/S12, labelled "estimated".
  2. District heat is not counted as renewable: shown as "no fossil fuel burned on site", with the CO₂ caveat.
  3. 450 MJ/m²·yr is Geneva's regulatory IDC threshold (REn, amended 13 Apr 2022; > 800 = significant exceedance;
     ge.ch). Consolidated current text not checked. Our heat index is an approximation: never call it the legal IDC.
  4. Per-building target = average of the same typology in the dataset, said on screen.
  5. Policy targets on the site only from public Ville / canton documents, cited.

## Framing
- Goal: a multi-fluid EDM replicable across all communes, to avoid costly per-commune licences.
- Users: supervisors, HVAC engineers, elected officials, building managers, property managers, citizens.
  No tool on the market covers them all.
- Citizens see buildings compared against targets, not raw values (privacy).
- Architecture (target, not in the demo): online platform with login and visibility per profile; one common codebase;
  shared encrypted hosting per commune or a standalone install; optional features each commune switches on.
  GitHub Pages is static: login and per-profile views can only be shown as mock-ups in the demo.

## Energy model and indicators
- A building = inputs (solar, fossil, district heating, grid) → transformation → end uses. Surpluses tracked too
  (summer solar surplus, waste heat, e.g. from an ice rink).
- Four headline indicators for portfolio and grid managers, including **dynamic COP**, CO₂ and energy per m².
  A heat pump gives 2–8 kWh of heat per kWh of electricity; gas or oil about 1 for 1.
- Problem: heat pump performance data stays in the building, with no automatic feedback.
- District-heated buildings count 0 local CO₂, which can skew comparisons: say so wherever CO₂ is shown.
- Master plan targets: −60 % CO₂ for the building stock by 2030, zero oil boilers, gas declining, 350 MWp of PV,
  sufficiency −15 % heat, falling average heat index (IDC), fossil phase-out by 2050.

## Indicators per audience (planned, checked against Rive-Claire)
| Audience | Indicator | Rive-Claire | Note |
|---|---|---|---|
| Officials, portfolio | Heat index IDC (corrected heat / SRE) | yes | SRE + degree-days in the data. 450 MJ/m² is a display class until a legal source is checked. Heat-pump heat measured at S09, S12 only |
| | Electricity per m² (IEE) | yes | say whether solar used on site is included |
| | CO₂ | yes | dataset factors: gas 0.188, oil 0.265 kg/kWh; electricity, district heat, wood = 0 direct |
| | Renewable share of heat | partly | heat-pump heat estimated elsewhere (flag it); counting district heat as renewable is an assumption |
| Citizens | A–G label vs same typology | yes | our own scale, not CECB |
| | Solar self-consumption, self-sufficiency | yes | 12 PV sites with production and injection |
| Energy manager | Heat-pump COP (monthly, vs outdoor temperature) | 2 sites | S09, S12 |
| | Sub-meter ≤ parent, unit checks | yes | part of the quality report |
| | Night base load | no | needs hourly data, not in the public demo |

## Data
- Rive-Claire (fictional): 48 sites, 172 meters, monthly values 2021–2025, **deliberate anomalies** (see `docs/rive-claire-data.md`).
  Known ones: duplicate S03-EL 2024-06; S25-GZ missing 2021-05/06; S44-EL missing 2023-11; S40-EL "estimé" 2023-05..08.
- No costs in CHF in the data: simulated, labelled "estimated".
- Tables: buildings (reference), consumption by fluid, month and site, costs (simulated), emission factors.
  Heating system per building (oil, gas, heat pump, district heat) enables filters and searches.

## State (all live)
| Part | Status |
|---|---|
| Manage, Citizens, How it works (FR/EN) | done, on the real Rive-Claire import |
| Site page with every meter, quality flags, CSV | done |
| 3D map · Rive-Claire (default) and Geneva (real SITG/swisstopo) | done; checked headless, not on a real phone GPU |
| Data quality report on import (17 checks, re-import test, CSV) | done (13 Nov); negative values and spikes replaced by an estimate |
| Building sheet (`#fiche/<building id>`, from the 3D map panel, every role) | first simple version (14 Nov): heat index, heating, electricity per m², CO₂, monthly bars, solar. Not computed yet: renewable share of heat, COP, night base load, A–G label |
| Heat index per site in MJ/m²·yr (#7): Manage table, site page, Rive-Claire map layer with the Geneva IDC classes | done 14 Nov. Approximate, **not weather-corrected**, never called the IDC. Heat-pump heat: heat meter at S09/S12, elsewhere pump electricity × the COP measured that month at S09/S12, marked estimated. No index where heating is direct electric (not metered apart) |
| Server stack: PostgreSQL + API + Caddy (`compose.yaml`, `server/`, `docs/deploy.md`) | merged 13 Nov night (#23); live since 13 Nov night on one small cloud server (EU), with its own domain and HTTPS since 14 Nov. `data.json` comes from the database, identical to the static build |
| Logins and roles (#15): admin, technique, élu·e, public; menus filtered, data filtered by the server, Users page, one-click demo accounts | done 14 Nov (#25), live on the server version with demo accounts on; GitHub Pages stays open without login |
| Several municipalities on one server (#43): municipality selector, Municipalities page, ZIP upload into a staging area, row review/edit, commit; 3D map per municipality | merged 14 Nov; checked by CI (`tools/check_stack.sh`, #45). Whether the live server runs it: not checked on 15 Nov |
| Pitch deck (`prototype/pitch/`, French only, runs offline) with app clips and two QR codes | done 14 Nov (#33–#46) |

**Main link: the server version** https://openedm.davidcarvalho.work/ (database, logins, roles, one-click demo
accounts; David, 15 Nov). GitHub Pages stays as an open static copy (no login). The old redirect domain is retired.
Server access and its cost are with David.

**Hosted version, decided (14 Nov):** one small server running `compose.yaml` (see `docs/deploy.md`); built-in
accounts, an OpenID Connect server (Keycloak, Authentik, Zitadel) only when a commune wants its own single sign-on.
Roles per #15. Several communes on one install: done (#43). Still open: deploys on merge (the server is updated by
hand), resetting passwords from the app.

## To do for 1 Dec (15 Nov; one branch + PR each, one session per item)

**Decide first** (team): what "more polished and easier to use" means. Suggested starting points: a guided first
visit (what to look at, in what order), fewer controls per screen, plain-language labels, one obvious story path for the
demo (energy manager → council → citizen). The demo link is the server version (decided 15 Nov).

**Pitch and docs**
1. Done 15 Nov: English deck `prototype/pitch/en.html`. David chose to reuse the French clips (French app text).
2. Done 15 Nov: `README.md` updated (project goes on, 1 Dec, server = main link, Pages = open copy, current
   features). QR codes checked: the deck's points to the server version, `docs/qr` to Pages.
3. Pitch clips: the two clips stacked on slides 2 and 3 are small on a projector.

**P0 user stories, still open** (status comment on each issue, 15 Nov; #5 closed as done)
4. #6 quality: coverage, estimated and excluded readings shown in Manage for the chosen year; a visible note on an
   incomplete total; a person decides between two different values for the same meter and month.
5. #8 explore: choose the fluid, a perimeter (quarter, building type) and months at portfolio level.
6. #9 compare: a month vs the same month a year before; show the absolute difference next to the %; coverage of the
   compared periods; alert wording asks a question, never claims a fault.
7. #10 council summary: choose the year, printable page, quality and limits in the summary; same numbers as Manage.
8. #11 hand-over: CSV of the filtered Manage view; a guide and a formula dictionary; one config file per commune
   (assumed prices are still in `tools/import_rive_claire.py`).

**Indicators** (from the Buyer review below)
9. Weather-corrected heat (degree-days are in `meta.climate`, unused); dynamic COP shown for heat-pump sites
   (`meta.hp_cop`, used but not displayed).
10. Traffic light per site: heat kWh/m² vs its typology average, labelled "approximate".
11. Corrections by an authorised person with a trace (who, when, why); median replacements today are automatic.

**Server version**
12. Check the live server runs the current `main` (#43 municipalities); deploys on merge (the Stack workflow's deploy job
    needs SSH secrets); a budget alert on the cloud account; David's admin account; reset passwords in the app.

**Housekeeping**
13. Close issue #4 ("test") if nobody uses it; go through P1/P2 issues (#12–#20) and the audience views (#26–#29),
    close what is covered.
14. Check the licence lines in `THIRD_PARTY.md` (three-mesh-bvh, OrbitControls, server stack: written from memory) and
    the SITG/swisstopo attribution wording; test the 3D map on a real phone.

**Geneva as a shared public base layer** (David, 15 Nov). Idea: public building data (Geneva first) is the starting
point every municipality reuses without copying it; what a municipality imports stays its own, linked to the public
buildings by **EGID** (the federal building ID, already in `prototype/map/buildings.json`). Maps are already shared:
`map_config` points to a folder, so several municipalities can use `map/` today.
Decided: a portfolio is a list of EGIDs in the import, not an area drawn on the map (a commune's buildings are
scattered, and the 3D map is slow without a GPU); the map's extent comes from the commune boundary. The public demo
links only a few public-owned buildings to fictional readings, under a permanent "fictional readings" banner, so
invented figures are never taken for real ones at a real address. Keep it generic (a regional data pack, Geneva first),
not hard-wired to Geneva.
15. Geneva as a built-in municipality: seeded in `server/schema.sql` like Rive-Claire, `map_config` → `map/`; the admin
    chooses the map when creating a municipality (`POST /api/localities` takes slug, name and country only today).
16. EGID link: optional `egid` column in the `building` import (upgrade step in `schema.sql`, `check_upgrade.sh` must
    pass; `build()` stays the single format). Linked buildings are highlighted on the map and open their site; the
    site page shows the public attributes (height, use, heating, heat index, solar). Buildings without EGID work as now.
17. A public-data view for a municipality with no readings yet (map, heat-index classes, heating mix, solar), since
    Manage and Citizens need readings. The public municipality list hides a municipality with no import today.

Later, after 1 Dec: one map extent per Geneva commune, generated once into a shared `map/ge/<commune>/` (the
whole canton is too heavy for the browser); add or remove buildings by clicking the map; sharing between
municipalities (e.g. commune → canton; accounts already get a role per municipality). Not checked: whether the federal
building register (RegBL/GWR) gives heating type and energy source for all of Switzerland, which would make the same
link work outside Geneva.

**Ideas, not planned:** consumption breaks after renovations, synergies between buildings, price scenarios, indirect CO₂,
DE/IT, place Rive-Claire in a recognisable Geneva neighbourhood on the map.

## Buyer review (13 Nov evening; since then: login, roles and a ZIP upload are done)
A review of the app as a buyer would see it: the commune's energy manager, plus the council, IT and procurement who sign.
Checked in the code: the degree-day data (`meta.climate`, `meta.climate_normal`) is in `data.json` but no calculation uses it.
Comparisons with commercial tools are from memory, not researched.

**Deal-breakers before a pilot**
1. Import of the commune's own data: today only `tools/import_rive_claire.py`, run offline; no upload, no CSV template.
2. Weather correction: year-on-year heat and the +12 % alert mostly reflect mild or cold winters.
3. Per-building benchmark: only portfolio targets; no kWh/m² heat per site against a reference.
4. Login, roles and a record of corrections: median replacements are automatic and unsigned.
5. Real costs: flat assumed prices, no check against utility invoices.

**Would strongly want:** printable annual report (council, Cité de l'énergie label); alerts with a threshold per site;
whole-portfolio export; indirect CO₂ (electricity and district heat count 0 today); hourly smart-meter data and the
official IDC/CECB figures; a register of renovations with savings before/after.

**Trust and procurement:** hosting in Switzerland or by the commune (GitHub Pages is US-hosted, which weakens
"souverain"); a data-protection (nLPD) statement; who maintains it and how often it is released; pricing shape, support
and service level; a guaranteed full export (no lock-in); German and Italian; accessibility not checked.

**Already good:** the data quality report (the differentiator); honest labels (estimated, simulated, CO₂ scope);
open and portable (no build step, no external requests).

**Proposed changes** (not done on 14 Nov; now in "To do for 1 Dec"):
| # | Change | Size |
|---|---|---|
| 1 | Weather-corrected annual heat (to the 1991–2020 normal), second figure on Manage and the site page; the +12 % alert on it if it compares heat year on year | S–M |
| 2 | Traffic light per site: heat kWh/m² vs the average of its typology, labelled "approximate" | M |
| 3 | Whole-portfolio CSV, plus a log of every corrected reading (rule, old, new) | S |
| 4 | Printable council page (print layout + button) | S |
| 5 | "Run it in your commune" block on How it works: hosting options, nLPD stance, estimated cost shape, CSV template and import command, full-export promise | S |

Not now: invoice checks, indirect CO₂, e-mail alerts, DE/IT, hourly data.
