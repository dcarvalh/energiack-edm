# Team plan · openEDM (Défi 2 « EDM citoyen et souverain »)

Updated 15 Nov 2026. What exists and how to run it: `README.md`. What is left: see "To do" below.

## Deadlines
- Hackathon pitch: done, Sat 14 Nov (deliverables in by 14:00: prototype, code with `THIRD_PARTY.md`, slides, project sheet).
- **The project goes on. Next presentation: Tue 1 Dec 2026.** Aim: a stable, presentable demo and a repo others
  can pick up (see "To do").
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
| Several municipalities on one server (#43): municipality selector, Municipalities page, ZIP upload into a staging area, row review/edit, commit; 3D map per municipality | merged 14 Nov; checked by CI (`tools/check_stack.sh`, #45). Live: the server answers `/api/localities` with `map_config` (checked 15 Nov) |
| Pitch deck (`prototype/pitch/`, French only, runs offline) with app clips and two QR codes | done 14 Nov (#33–#46) |

**Main link: the server version** https://openedm.davidcarvalho.work/ (database, logins, roles, one-click demo
accounts; David, 15 Nov). GitHub Pages stays as an open static copy (no login). The old redirect domain is retired.
Server access and its cost are with David.

**Hosted version, decided (14 Nov):** one small server running `compose.yaml` (see `docs/deploy.md`); built-in
accounts, an OpenID Connect server (Keycloak, Authentik, Zitadel) only when a commune wants its own single sign-on.
Roles per #15. Several communes on one install: done (#43). Still open: deploys on merge (the server is updated by
hand), resetting passwords from the app.

## To do (priorities set by David, 15 Nov; one branch + PR each, one session per item)

**Goal until 1 Dec** (David, 15 Nov): a stable demo he can link from his portfolio and talk about; a repo teammates can
join and understand quickly (what is done, what is not, what is next); a state anyone, David included, can pick up
again after weeks away. Not a "polish" pass: no redesign. Effort: S = under an hour, M = about one session, L = several.
Items 15–19 keep their numbers: their details are under "Public base layer" below.

**Now, in this order**
- ~~**Step 1.**~~ Done 15 Nov: licences and attribution (S): checked the `THIRD_PARTY.md` lines written from memory (three-mesh-bvh,
   OrbitControls, server stack) and the SITG/swisstopo credit wording against the real sources.
- ~~**Step 2.**~~ Done 15 Nov (`START_HERE.md`): "Start here" doc (S, new): what openEDM is, what is done and not done, run it in 5 minutes, where each part of the
   code lives, next steps (points here). Today that is spread across `README.md`, `plan.md`, `CLAUDE.md` and `docs/`.
   Refresh it at step 9.
- ~~**Step 3.**~~ Done 15 Nov: Geneva as a built-in municipality (S–M, item 15): seeded with the `map/` map, listed to
  visitors before it has readings (pages without data say so and point to the map), the admin picks a map when creating
  a municipality.
- ~~**Step 4.**~~ Done 15 Nov: one map per municipality (S, David 15 Nov): once Geneva is its own municipality, drop the Rive-Claire /
  Geneva switch on the 3D tab (`MAPS`, `switchMap` in `prototype/index.html`, the switch in `map3d.js`); the map is
  the municipality's `map_config`. Clear the old `energiack-map` choice saved in `localStorage`.
- ~~**Step 5.**~~ Done 15 Nov: a clearer municipality switch, a labelled button in the sidebar and the page header (phones use the header one) (S, David 15 Nov): today it is a small uppercase label over a borderless
  dropdown at the top of the sidebar (`#loc-select` in `prototype/index.html`), easy to miss; with one municipality
  it is only a name. Make it visible and explicit: e.g. a labelled button "Municipality: Rive-Claire ▾" (FR/EN) that
  opens the list, also reachable on phone width; show the current municipality in the page header.
- ~~**Step 6.**~~ Done 15 Nov: Geneva addresses from SITG `CAD_ADRESSE` (`tools/geneva_addresses.py`, normal-case names): most buildings sharing one address 10 → 2. Without an address 487 → 1933: annexes, garages and building parts with their own EGID that the register gives no address (their old one was the energy record of a group); they show "EGID …". Idea: a "part of <address>" link for them. (M, item 19.) Before step 8, because Genève (démo) shows real addresses.
- ~~**Step 7.**~~ Done 15 Nov: EGID link (item 16): optional `egid` column in `batiments` (`ALTER TABLE building ADD COLUMN IF NOT EXISTS egid`). On the Geneva map linked buildings get a blue site label, a "Municipality sites" legend filter and an "All data for this site" button; the site page gets a "Public building data" table read from the map. Tested with two fictional Geneva sites linked by hand (no committed data has EGIDs yet: step 8).
- ~~**Step 8.**~~ Done 15 Nov: Genève (démo) (item 18), built-in municipality `geneve-demo`: 39 real buildings of the Geneva map chosen by SITG use and linked by EGID, plus public lighting; yearly heat = public heat index × floor area (2025 lands at 85-95 % of it: −2 %/yr trend, mild year), electricity and water = the map's simulated values. Permanent banner and a "simulated" tag on every reading-based figure (not on the public building data). Seeded by the server from `geneve/csv/`, static copy `prototype/data-geneve-demo.json` for Pages; `check_stack.sh` asserts both are equal. Fixed on the way: the generator's monthly split gave heat and solar 0.48× their yearly target and electricity and water 2.4×. The climate tables were already Geneva's real ones (checked against MeteoSwiss Genève-Cointrin), nothing to replace.
- ~~**Step 8a.**~~ Done 15 Nov (David: "one neighbourhood, clustered and highlighted"): the 39 Genève (démo) buildings
  now sit in one neighbourhood (Plainpalais / Jonction around Boulevard Carl-Vogt, all within 520 m), 32 with the
  matching SITG use, 7 in a plausible host (`FALLBACK` in `tools/make_geneva_fake.py`). The map opens framed on them
  with only them lit (legend "Municipality sites", click to show all); site names appear when zoomed in, on hover or
  when selected. Fixed: that legend key ghosted every building. The server replaces a simulated built-in dataset at
  each start (`store.load(..., replace=True)`), so old demo sites do not linger. Address check against OpenStreetMap:
  of 11,869 OSM addresses inside a map footprint, 72.8 % match exactly, 2.9 % same street other number, 10.2 % another
  street (mostly second entrances of corner and Old Town buildings that SITG does not attach to that EGID; only 0.6 %
  point to a building 40 m+ away); the 35 demo sites with an OSM address in their footprint all agree.
- ~~**Step 8b.**~~ Done 15 Nov: building sheets in Genève (démo). On the Geneva map a linked building's panel has
  "Building sheet" (`#fiche/<id>`) and a "Simulated readings, <year>" block (heat index, energy/m², heat, electricity,
  solar, water of the site, each tagged "simulated"; `siteYear()` in `prototype/index.html`, same numbers as the
  sheet) under the public SITG data (not tagged). In the sheet the reading cards carry the "simulated" tag, heating
  and "other indicators" do not. Fixed on the way: the sheet's month chart called `LOC()` (now the municipality
  object), so no sheet opened, Rive-Claire's included; after a municipality switch the old map's click listener and
  a queued frame still ran (`trim` / `addr` errors); the `ecole_primaire` type had no label.
- **Step 9.** Last: stability pass on the server version (S, new): every page and role on https://openedm.davidcarvalho.work/,
   FR and EN, phone width; fix what is broken or confusing (empty states, errors). Then a project entry on the
   portfolio site (`portfolio/`, separate repo) linking the server version.

**Before 1 Dec, after "Now"**
- #10 council summary (S–M): choose the year, printable page, quality and limits in it; same numbers as Manage.
- #11 hand-over (M): CSV of the filtered Manage view; a guide and a formula dictionary; one config file per commune
  (assumed prices are still in `tools/import_rive_claire.py`).
- Weather-corrected heat (S–M): degree-days are in `meta.climate`, unused; the +12 % alert on the corrected figure.
  Show the monthly heat-pump COP (`meta.hp_cop`, used but not displayed).
- Corrections by an authorised person with a trace (L): who, when, why; median replacements today are automatic.
- Public-data view for a municipality with no readings (M, item 17).
- Server: deploys on merge (S–M; the Stack workflow's deploy job needs SSH secrets, David adds them); David's admin
  account (S). Budget alert (S): likely before 1 Dec, but David may move the server off the cloud account to his own
  machine (to decide, maybe after 1 Dec).

**Later / ideas**
- #6 quality in Manage (M, L with the part where a person decides between two values for the same meter and month):
  coverage, estimated and excluded readings for the chosen year; a visible note on an incomplete total.
- #8 explore (M): choose the fluid, a perimeter (quarter, building type) and months at portfolio level.
- #9 compare (M): a month vs the same month a year before; absolute difference next to the %; coverage of both periods;
  alert wording asks a question, never claims a fault.
- Traffic light per site (M): heat kWh/m² vs its typology average, labelled "approximate".
- Reset passwords in the app (M): only useful once real users exist.
- Issue triage (S–M): P0 issues got a status comment on 15 Nov; P1/P2 (#12–#20) and the audience views (#26–#29) not
  gone through.

**Done or dropped on 15 Nov:** English deck `prototype/pitch/en.html` (reuses the French clips); `README.md` updated
(project goes on, server = main link); QR codes checked. Dropped: the small stacked pitch clips (the hackathon pitch
is over; David may make a new deck for 1 Dec) and the real-phone test (David checked it: fine).

**Public base layer, Switzerland-wide, Geneva first** (David, 15 Nov). Idea: public building data is the starting point
every municipality reuses without copying it; what a municipality imports stays its own, linked to the public
buildings by **EGID** (the federal building ID, already in `prototype/map/buildings.json`). Maps are already shared:
`map_config` points to a folder, so several municipalities can use `map/` today.
Decided: a portfolio is a list of EGIDs in the import, not an area drawn on the map (a commune's buildings are
scattered, and the 3D map is slow without a GPU); the map's extent comes from the commune boundary. Real and
simulated data never mix in one municipality (David, 15 Nov): the default **Genève** shows only public, true values;
a separate **Genève (démo)** has a set of real buildings where every reading is simulated, to show the features
Rive-Claire has (site sheet, meters, history, alerts).
Goal: adaptable anywhere in Switzerland (David, 15 Nov). Geneva is the first **data pack**, not a special case: a
municipality points to a pack, the app reads the same map schema whatever the source, and Geneva-only fields are
optional (the page hides what a pack lacks). EGID is national, so the link in 16 works everywhere. Build each pack in
two layers: national sources that exist for every commune, plus cantonal extras where a canton publishes them.

| Data | National (every commune) | Geneva extra (SITG, used today) |
|---|---|---|
| terrain, aerial photo | swissALTI3D, SWISSIMAGE (used today) | – |
| footprints, heights | swissBUILDINGS3D (to check: EGID on each building) | CAD_BATIMENT_HORSOL |
| use, year, heating type, energy source | federal register RegBL/GWR (to check: heating fields, open access) | SCANE_CHAUDIERE (boilers) |
| solar potential | the federal roof solar layer (sonnendach.ch; to check: per-building values) | OCEN_SOLAIRE_PV_BATIMENT |
| heat index | none known: only from the commune's own readings | SCANE_INDICE_MOYENNES_3_ANS (IDC) |
| building addresses | swisstopo official building address directory (by EGID; to check) | CAD_ADRESSE (item 19) |
| commune boundary | swissBOUNDARIES3D (to check) | – |
| climate, degree-days | MeteoSwiss open data (to check: station data, licence) | – |

For 1 Dec only Geneva; the code must not assume it (no Geneva names or SITG fields hard-coded outside the pack
builder `tools/make_map.py`, the IDC threshold applies only where the pack says so).
15. Geneva as a built-in municipality: seeded in `server/schema.sql` like Rive-Claire, `map_config` → `map/`; the admin
    chooses the map when creating a municipality (`POST /api/localities` takes slug, name and country only today).
16. EGID link: optional `egid` column in the `building` import (upgrade step in `schema.sql`, `check_upgrade.sh` must
    pass; `build()` stays the single format). Linked buildings are highlighted on the map and open their site; the
    site page shows the public attributes (height, use, heating, heat index, solar). Buildings without EGID work as now.
17. A public-data view for a municipality with no readings yet (map, heat-index classes, heating mix, solar), since
    Manage and Citizens need readings. The public municipality list hides a municipality with no import today.
    This is what the default Genève shows.
18. Genève (démo): about 40 real buildings on the same `map/` (chosen by use: schools, offices, sports, culture),
    each with its EGID and fully simulated meters and readings, rebuilt by `tools/make_geneva_fake.py` (today it
    makes 40 sites that are not linked to the map). Make the simulated values plausible from public attributes: floor
    area from footprint × levels, yearly heat from the public heat index, monthly split by degree-days (the tables in `geneve/csv/` turned
    out to be Geneva's real climate already, checked against MeteoSwiss), electricity from assumed kWh/m² per use (labelled "assumed"). On screen: a permanent "simulated
    data" banner and a "simulated" tag on every figure, never only a footnote, because the addresses are real.
    Needs 16.
19. Correct Geneva addresses. Today `tools/make_map.py` takes `addr` from the first energy record with the same EGID
    (heat index, then boilers, then solar): that is the installation's address, not the building's. In
    `prototype/map/buildings.json` 10 buildings share "30 Quai du Mont-Blanc", formats are mixed ("40 Rue AGASSE",
    "Rue SCHAUB 21") and 487 of 10,574 have none. Fix: read SITG `CAD_ADRESSE` (official address register, open;
    checked 15 Nov that it answers by EGID with street type, name, number, postcode, locality, official flag, point),
    with the existing `sitg()` helper on the map's extent, official addresses only. Group by EGID: several entrances
    give "Rue de Bâle 28-30" (all numbers in the search index). No address on the EGID: an address point inside the
    footprint, else "EGID …" as now. One format: street, number, then "1201 Genève" where there is room. Keep the
    old energy-layer address only to print a before/after count and 20 random pairs, checked by hand on
    map.geo.admin.ch. Build into a scratch folder, then copy; bump both `V`; add `CAD_ADRESSE` to `THIRD_PARTY.md`.
    To decide: write names in normal case ("Samuel-Constant", recommended) or as the register does ("Samuel-CONSTANT").

Later, after 1 Dec: a pack builder per commune from its federal statistical number (BFS number): national sources
first, cantonal extras when present, generated once into a shared `map/<canton>/<commune>/` (a whole canton is too
heavy for the browser); DE/IT UI (Swiss-wide means German and Italian communes); CO₂ factors and prices per pack
or commune (see #11 hand-over); add or remove buildings by clicking the map; sharing between
municipalities (e.g. commune → canton; accounts already get a role per municipality). Every "to check" in the table above is from memory, not
verified: check it before building a non-Geneva pack.

**Ideas, not planned:** consumption breaks after renovations, synergies between buildings, price scenarios, indirect CO₂,
DE/IT, place Rive-Claire in a recognisable Geneva neighbourhood on the map.

## Buyer review (13 Nov evening; since then: login, roles and a ZIP upload are done, so deal-breakers 1 and 4 are partly met)
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

**Proposed changes** (not done on 14 Nov; now in "To do"):
| # | Change | Size |
|---|---|---|
| 1 | Weather-corrected annual heat (to the 1991–2020 normal), second figure on Manage and the site page; the +12 % alert on it if it compares heat year on year | S–M |
| 2 | Traffic light per site: heat kWh/m² vs the average of its typology, labelled "approximate" | M |
| 3 | Whole-portfolio CSV, plus a log of every corrected reading (rule, old, new) | S |
| 4 | Printable council page (print layout + button) | S |
| 5 | "Run it in your commune" block on How it works: hosting options, nLPD stance, estimated cost shape, CSV template and import command, full-export promise | S |

Not now: invoice checks, indirect CO₂, e-mail alerts, DE/IT, hourly data.
