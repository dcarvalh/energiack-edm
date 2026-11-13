# Team plan · Défi 2 « EDM citoyen et souverain »

Updated 13 Nov 2026, evening. What exists and how to run it: `README.md`.

## Deadlines
- All deliverables before **14:00 on Sat 14 Nov** (team meeting; the organisers' sheet said 14:30, pitch 15:00: confirm).
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
| Data quality report on import | **next** (first user story) |

## Next steps (keep the UI minimal; FR and EN for every string)
1. Quality report page: run every check on import (duplicates, unknown IDs, formats, gaps, estimated readings), list the findings.
2. Indicators: energy per m², CO₂, dynamic COP for heat-pump sites (check the dataset has what COP needs).
3. Targets per site with a traffic light (kWh/m² vs target).
4. Videos and QR code for the pitch.
5. Ideas, not started: consumption breaks after renovations, synergies between buildings, price scenarios; place the
   fictional commune in a recognisable Geneva neighbourhood on the map.
