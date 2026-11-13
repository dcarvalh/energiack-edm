# Rive-Claire dataset (v2)

The fictional commune used by the Energ-IACK 2026 hackathon: 25,000 inhabitants, 48 municipal sites, 172 meters,
monthly readings from January 2021 to December 2025. Sites and readings are simulated; the climate is real
(Genève-Cointrin). The data contains **deliberate anomalies** (duplicates, gaps, estimated readings).

**Licence: CC BY 4.0.** Source: « Energ-IA Transition, Energ-IACK 2026 ». Copied here unmodified from the organisers'
team space, with the CSV tables extracted from the guide.

| File | What |
|---|---|
| `EIAK-RC-Guide-Donnees-vf.html` | the organisers' guide (French): schema, tables, rules. The CSV zip is embedded in it |
| `EIAK-RC-Donnees-Rive-Claire-v2.xlsx` | the same tables as an Excel workbook, with notes |
| `csv/` | the 11 tables as CSV: UTF-8 with BOM, `;` separator, decimal point, months as text `YYYY-MM` |
| `LISEZ-MOI.txt` | the organisers' notes on the CSV archive (French) |

`tools/import_rive_claire.py` and `tools/make_rive_claire_map.py` read the guide from this folder. Tables, rules and
known defects in English: `docs/rive-claire-data.md`.

Not copied (also CC BY 4.0, kept out to keep the repo small): the illustrated story « Une journée côté énergie » (PDF),
the teaser video and 16 illustrations.
