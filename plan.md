# Team plan · openEDM (Défi 2 « EDM citoyen et souverain »)

Updated 13 Nov 2026, evening. What exists and how to run it: `README.md`.

## Deadlines
- All deliverables before **14:00 on Sat 14 Nov**.
  Deliverables: prototype, code with declared third-party parts and licences (`THIRD_PARTY.md`), slides, one-page project sheet.
- Pitch: about 5 minutes, 2 of them video. **Tell a story**, don't list features.

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

## Next steps (keep the UI minimal; FR and EN for every string)
1. Corrections: negative values and spikes are replaced by the median of the same month in other years (David, 13 Nov).
   Later: let an authorised person correct a value with a trace (who, when, why).
2. Indicators: energy per m², CO₂, dynamic COP for heat-pump sites (check the dataset has what COP needs).
3. Targets per site with a traffic light (kWh/m² vs target).
4. Videos and QR code for the pitch.
5. Ideas, not started: consumption breaks after renovations, synergies between buildings, price scenarios; place the
   fictional commune in a recognisable Geneva neighbourhood on the map.

## Buyer review (13 Nov evening, not started)
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

**Proposed before 14:00 Sat** (one branch + PR each; if short on time, only 1 and 2):
| # | Change | Size |
|---|---|---|
| 1 | Weather-corrected annual heat (to the 1991–2020 normal), second figure on Manage and the site page; the +12 % alert on it if it compares heat year on year | S–M |
| 2 | Traffic light per site: heat kWh/m² vs the average of its typology, labelled "approximate" | M |
| 3 | Whole-portfolio CSV, plus a log of every corrected reading (rule, old, new) | S |
| 4 | Printable council page (print layout + button) | S |
| 5 | "Run it in your commune" block on How it works: hosting options, nLPD stance, estimated cost shape, CSV template and import command, full-export promise | S |

Not now: upload in the browser, real login, invoice checks, indirect CO₂, e-mail alerts, DE/IT, hourly data.
