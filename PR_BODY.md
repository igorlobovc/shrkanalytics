### Sheet‑based rollups, unified inputs, explicit/alias summaries, normalizer, and performance metrics

## Overview

This PR strengthens the data pipeline and reporting around fornecedores and unified workbooks:

- Adds an end‑to‑end pipeline runner and robust sheet‑based classification for explicit vs low‑probability (alias) matches.
- Normalizes currency to integer cents; recognizes Band's `Total` column as the explicit amount.
- Introduces a standardizer (normalizer) for fornecedores sheets to a common schema.
- Adds definitive explicit inventories and per‑sheet explicit counts.
- Documents performance metrics in the README.

## Key Additions

- Pipeline runner: `Estelita/run_full_pipeline.py`
- Normalizer + summary: `Estelita/normalize_fornecedores.py`, `Estelita/Processed/Normalized/_summary.csv`
- Rollups (sheet‑based, integer amounts):
  - With value: `Eligible_Value_Explicit_All_Providers.csv`, `Eligible_Value_Alias_All_Providers.csv`
  - Without value: `Explicit_Without_Value_All_Providers.csv`, `Alias_Without_Value_All_Providers.csv`
- Summaries:
  - Provider totals: `Providers_Explicit_Alias_Summary.csv`
  - Per‑file totals: `Files_Explicit_Alias_Summary.csv`
  - Unified per‑file: `Unified_Explicit_Summary.csv`
  - Explicit per source_sheet: `Explicit_Counts_By_SourceSheet.csv`
- Definitive explicit inventories:
  - All: `Explicit_Matches_All.csv`
  - Exact subset (uncertain=false OR ISWC present OR catalog basis): `Explicit_Matches_Exact.csv`
- Explicit terms index (3 col): `Explicit_Terms_Index.csv`
- Data catalog: `Data_Catalog.csv`
- Makefile targets: `make pipeline`, `make summaries`, `make audit`, `make normalize`, …
- CI sanity check: `.github/workflows/pipeline-check.yml`

## Highlight Findings (current run)

- Searches
  - Sheets scanned: 56
  - Rows scanned: 130,788
- Matches found (sheet‑based)
  - Explicit total rows: 60
  - Low probability (alias) total rows: 1,135
- Fornecedor coverage
  - Files scanned: 49
  - Files with ≥1 match: 18 (36.73%)

## Band and SBT Notes

- Band unified explicit values from `Total` now counted:
  - `band UNIFICADO out dez 2023 jan fev 2024`: explicit_rows=8, explicit_value=int BRL 419
- SBT unified explicit:
  - `Unificado SBT nov dez 23 e jan fev mar 24`: explicit_rows=4, explicit_value=int BRL 6,693

## README Updates

- Added sections for pipeline usage, normalizer, definitive explicit outputs, and a Highlight Findings block.

## Organization & Hygiene

- Ignore bulky per‑sheet normalized CSVs going forward (keep `_summary.csv`).
- Optional normalization of `file_stem`→`provider` via `Estelita/config/stem_aliases.csv`.
- Data catalog for quick inventory of summary outputs.

## Next Steps (optional)

- Add a small CI sample test that asserts non‑zero counts on key metrics.
- Tag a dated release with the summary CSVs; attach bulky normalized sheets as release assets.

