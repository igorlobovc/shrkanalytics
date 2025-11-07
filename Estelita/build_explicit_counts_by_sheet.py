#!/usr/bin/env python3
"""
Compute explicit match counts per original fornecedor sheet (source_sheet).

For each processed eligible workbook (*__eligible_with_refs.xlsx), reads
the Explicit_Refs_Only tab and groups by '__source_sheet' (if available)
to count explicit rows per source sheet. Falls back to the file stem when
no source_sheet is present.

Output:
- Estelita/Processed/Summaries/Explicit_Counts_By_SourceSheet.csv
  Columns: provider, file_stem, source_sheet, explicit_rows
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'
OUT = PROC / 'Summaries'
OUT.mkdir(parents=True, exist_ok=True)


def main():
    rows = []
    for xlsx in sorted(PROC.glob('*__eligible_with_refs.xlsx')):
        stem = xlsx.stem.replace('__eligible_with_refs', '')
        provider = stem.split()[0] if stem else ''
        try:
            xl = pd.ExcelFile(xlsx)
        except Exception:
            continue
        if 'Explicit_Refs_Only' not in xl.sheet_names:
            continue
        try:
            df = xl.parse('Explicit_Refs_Only')
        except Exception:
            continue
        if df is None or df.empty:
            continue
        if '__source_sheet' in df.columns:
            grp = (df.groupby('__source_sheet').size().reset_index(name='explicit_rows'))
            for _, r in grp.iterrows():
                rows.append({
                    'provider': provider,
                    'file_stem': stem,
                    'source_sheet': str(r['__source_sheet']),
                    'explicit_rows': int(r['explicit_rows'])
                })
        else:
            rows.append({
                'provider': provider,
                'file_stem': stem,
                'source_sheet': 'Explicit_Refs_Only',
                'explicit_rows': int(len(df))
            })

    out = OUT / 'Explicit_Counts_By_SourceSheet.csv'
    pd.DataFrame(rows).sort_values(['provider','file_stem','source_sheet']).to_csv(out, index=False)
    print(f"Wrote: {out}")


if __name__ == '__main__':
    main()

