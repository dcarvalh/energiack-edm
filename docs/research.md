# Défi 2: what Geneva has today (research, 2026-11-13 night)

Sources checked online. "Verified" = read in the source; "inferred" = my reading.

## Ville de Genève, Service de l'énergie (ENE)
- Mission: "100% renouvelable et 0 émission de CO2 en 2050". It "assure le monitoring des consommations",
  buys electricity on the free market, runs a field team, builds solar. Works with OCEN (canton) and SIG (utility). *Verified.*
- Size: about **800 buildings and apartment blocks** (rapport d'activités 2022, p. on dynamic regulation). *Verified.*
- 2030 targets for City-owned buildings: **-30 % energy, -60 % CO2** (Stratégie climat). *Verified.*
- 2023 figures: heat -4 % (4.9 GWh), electricity -4.8 % (1.8 GWh), renewable share of heat **9 %**,
  PV 0.9 GWh from 45 plants, 66 % self-consumption. 2022: electricity 37.8 GWh. *Verified.*
- Reporting today: an **annual PDF activity report** (46 pages, charts as images), figures "brutes, sans corrections
  liées à l'augmentation du patrimoine" (no normalisation per m² or climate). Budget tracked in SAP. *Verified.*
- Software used for monitoring: **not named anywhere public**. The challenge text says communes "dépendent souvent de
  logiciels propriétaires coûteux". *Inferred: Geneva is in that case, to confirm with the organisers on Friday.*
- Pilot: dynamic (weather-predictive) heating regulation in 27 buildings, 10-15 % potential, to extend to ~800. *Verified.*

## What other Swiss communes use
- **EnerCoach** (SuisseEnergie / OFEN): free energy-accounting web tool, 500+ communes, required output for the
  Cité de l'énergie label. Manual or semi-manual monthly/annual entry; no AI, no open data model. *Verified (2017-2020 sources).*
- Canton (OCBA + UNIGE) issued a 2026 tender for a SaaS building-data platform (~70 buildings) incl. energy steering. *Verified.*

## The gap the prototype addresses (inferred)
1. Data locked in vendor tools or spreadsheets; yearly PDF instead of a live view.
2. No common open data format between communes -> nothing to share.
3. Raw totals, no normalisation (kWh/m², climate), so trends are hard to read.
4. Citizens see a yearly PDF, not where their commune stands vs 2030/2050 targets.

## Sources
- https://www.geneve.ch/autorites-administration/administration-municipale/departement-amenagement-constructions-mobilite/services-municipaux/service-energie
- https://www.geneve.ch/themes/durabilite/climat/strategie-climat/10-mesures-phares-climat-avancement/energie-batiments
- https://www.geneve.ch/publication/rapportactivites-energie-2022-ville-geneve
- https://www.eipa.eu/epsa/enercoach-a-digital-energy-accounting-platform-for-municipalities-to-monitor-energy-consumption-of-public-infrastructure/
- https://ted.europa.eu/fr/notice/451453-2026/pdf
