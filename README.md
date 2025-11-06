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
