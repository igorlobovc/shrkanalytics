# 🎵 Estelita Consolidator

**Goal**: To consolidate all musical works and recordings held by Estelita into a **single canonical, deduplicated, and audit-ready table**. This reference will be used to validate third-party data (e.g., supplier match, catalog licensing).

## 🔧 Input Sources

Located in `/Estelita/Raw`:
- `ESTELITA OBRAS_v2.xlsx` → musical works
- `ESTELITA Fonogramas_v2.xlsx` → recordings
- `ESTELITA - OBRAS 09-10-25 (2).pdf` → PDF export of work data
- `ESTELITA - FONOGRAMAS -09-10-25.pdf` → PDF export of recording data

Additional data may come from:
- `primary_archive.duckdb` (tables: `obras_clean`, `fonogramas_clean`)

## 🧩 What Makes This Special?

- **Hybrid Merge**: ISWC, ISRC, or normalized `title + artist` will be used to unify records.
- **Text Normalization**: All names, titles, and associations undergo unidecode + unicode normalization + case handling.
- **Canonical Logic**: We select the best variant of title/artist per rules:
  - Prefer presence of code (ISWC or ISRC)
  - Prefer longest, complete title
  - Prefer `FONOGRAMAS` performer > `OBRAS` composer
- **Segmentation** is guided by the PDFs but we DO NOT parse them live — we use patterns derived from them (like block starts: ISRC, ISWC, capitalized titles, etc.)

## 📄 Output Files (in `/Estelita/Processed/`)

- `Consolidated_Reference.parquet`
- `Consolidated_Reference.csv`
- `_logs/Consolidated_Reference.report.json`
- `_logs/Consolidated_Reference.duplicates.csv`
- `_logs/Consolidated_Reference.ambiguous.csv`
- `_logs/Consolidated_Reference.sample_head.csv`

## ✅ Validation Criteria

- Max 2% missing in `title`
- Report must include count of:
  - Unique ISRCs and ISWCs
  - Deduplicated titles
  - Ambiguous matches
- Each row must represent a unique song with:  
  `work_id`, `recording_id`, `title`, `artist`, `association`, provenance.

---

## 📌 SBT Priority: What’s Included

This repo now includes a focused pipeline to match supplier sheets and prioritize SBT for revenue collection:

- Curated catalog (from OBRAS/Fonogramas):
  - `Estelita/Processed/Curated_Titles_Authors.csv`
- Batch matching and reporting tools:
  - `Estelita/prepare_titles_and_match_suppliers.py` — build curated list and match a given supplier sheet
  - `Estelita/batch_match_suppliers.py` — scan all fornecedores, compute coverage and top unmatched
  - `Estelita/analyze_supplier_readiness.py` — score each sheet’s readiness (amounts, percent, dates, matchability)
  - `Estelita/export_matches_from_supplier_file.py` — export a supplier workbook filtered to matched rows only, enriched with Matched Title and ISWC
- In‑DB matcher (DuckDB):
  - `Estelita/build_relations_duckdb.py` — detect columns by overlap, join WORKS ↔ RECORDINGS and profile inputs

### SBT Deliverables (checked into Git)

- `Estelita/Processed/Unificado SBT nov dez 23 e jan fev mar 24__matches_only_with_refs.xlsx`
  - SBT “matches‑only” workbook with reference columns:
    - `Matched Title`, `Matched Identifier/ISWC`
- `Estelita/Processed/Unificado SBT nov dez 23 e jan fev mar 24__eligible_with_refs.xlsx`
  - SBT “rights‑eligible” workbook (two tabs):
    - `Explicit_Refs_Only`: rows that intersect Estelita catalog by title and/or ISWC
    - `Low Probability Matches SBT`: rows eligible by represented artist or editora alias
  - All rows include:
    - `Matched Title`, `Matched Identifier/ISWC`, `Eligibility Basis`, `Uncertain Match`

### How to Reproduce Locally

1) Build curated catalog (titles+authors) from OBRAS:

```
python3 Estelita/prepare_titles_and_match_suppliers.py
```

2) Batch match all fornecedores and produce coverage + unmatched:

```
python3 Estelita/batch_match_suppliers.py
```

3) Produce per‑file readiness scores (ranks sheets with revenue fields highest):

```
python3 Estelita/analyze_supplier_readiness.py
```

4) Export a supplier workbook filtered to matched rows, with reference columns:

```
SUPPLIER_FILE="/Users/…/Fornecedores/SBT/Unificado SBT nov dez 23 e jan fev mar 24.xls" \
  python3 Estelita/export_matches_from_supplier_file.py
```

Outputs are written to `Estelita/Processed/`.

### Notes

- The `.gitignore` allows committing the SBT deliverable workbook mentioned above so it’s accessible on GitHub.
- Other large files (e.g., full `Processed/` outputs) are generated locally and typically not tracked, to keep the repo light.
5) Build eligibility catalog and export SBT “rights‑eligible” workbook (two tabs):

```
python3 Estelita/build_eligible_catalog.py
SUPPLIER_FILE="/Users/…/Fornecedores/SBT/Unificado SBT nov dez 23 e jan fev mar 24.xls" \
  python3 Estelita/export_sbt_rights_eligible.py
```

Outputs:
- `Estelita/Processed/Eligible_Catalog.csv`, `Eligible_Artists.txt`
- `Estelita/Processed/Unificado SBT nov dez 23 e jan fev mar 24__eligible_with_refs.xlsx`
- `Estelita/Processed/SBT_Rights_Eligible_Summary.csv`
## 📊 Consolidated Summaries

- General (all files): `Estelita/Processed/Fornecedores_Summary.csv`
  - Columns: provider, file_stem, matches_rows, eligible_explicit_rows, eligible_alias_rows, sum_valor_brl_explicit
- By provider: `Estelita/Processed/Fornecedores_ByProvider_Summary.csv`
- Explicit only (all providers): `Estelita/Processed/Eligible_Explicit_All_Providers.csv`
  - Combined export of the `Explicit_Refs_Only` sheets for quick finance review.
