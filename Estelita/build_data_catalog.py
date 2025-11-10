#!/usr/bin/env python3
"""
Build a lightweight data catalog documenting generated summary CSVs.

Scans Estelita/Processed/Summaries/*.csv and emits:
- Estelita/Processed/Summaries/Data_Catalog.csv
  Columns: file, rows, columns, purpose
"""

from __future__ import annotations

from pathlib import Path
import csv

BASE = Path(__file__).resolve().parent
SUM = BASE / 'Processed' / 'Summaries'

PURPOSE = {
    'Providers_Explicit_Alias_Summary.csv': 'Provider totals of explicit/alias rows and integer BRL',
    'Files_Explicit_Alias_Summary.csv': 'Per-file explicit/alias counts and integer BRL',
    'Unified_Explicit_Summary.csv': 'Per unified workbook: explicit counts and last-column amount rows',
    'Explicit_Terms_Index.csv': '3-col index of terms (music/author/ISRC) from explicit rows',
    'Explicit_Counts_By_SourceSheet.csv': 'Explicit row counts grouped by original source sheet',
    'Explicit_Matches_All.csv': 'All explicit rows from Explicit_Refs_Only across suppliers',
    'Explicit_Matches_Exact.csv': 'Strict subset of explicit rows: exact (uncertain=false or ISWC/basis)',
    'files_by_recency.csv': 'All tracked files with last commit metadata (newest->oldest)',
    'files_usefulness_rank.csv': 'Files ranked by usefulness category and score',
}


def main():
    out_rows = []
    for p in sorted(SUM.glob('*.csv')):
        try:
            with p.open('r', encoding='utf-8') as f:
                r = csv.reader(f)
                headers = next(r, [])
                count = sum(1 for _ in r)
        except Exception:
            headers, count = [], 0
        purpose = PURPOSE.get(p.name, 'Generated summary')
        out_rows.append({'file': p.name, 'rows': count, 'columns': ';'.join(headers), 'purpose': purpose})
    out_path = SUM / 'Data_Catalog.csv'
    with out_path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['file','rows','columns','purpose'])
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"Wrote: {out_path}")


if __name__ == '__main__':
    main()

