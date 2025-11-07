#!/usr/bin/env python3
"""
Build a simple 3-column CSV of explicit matches' terms across all suppliers.

Reads all processed eligible workbooks' Explicit_Refs_Only sheets and extracts:
- source_sheet: original fornecedor sheet name (from '__source_sheet' if present),
                else '<provider>/<file>:Explicit_Refs_Only'
- term: title (music), author, and ISRC when available
- term_type: 'music', 'author', or 'fonogram'

Output:
- Estelita/Processed/Summaries/Explicit_Terms_Index.csv
"""

from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'
OUT = PROC / 'Summaries'
OUT.mkdir(parents=True, exist_ok=True)


def norm(s: str) -> str:
    return str(s or '').strip()


def find_col(df: pd.DataFrame, options: list[str]) -> str | None:
    cols = list(df.columns)
    cn = [str(c).strip().lower() for c in cols]
    for opt in options:
        o = str(opt).strip().lower()
        for i, x in enumerate(cn):
            if o == x:
                return cols[i]
        for i, x in enumerate(cn):
            if o in x:
                return cols[i]
    return None


def main():
    rows = []
    for xlsx in sorted(PROC.glob('*__eligible_with_refs.xlsx')):
        stem = xlsx.stem.replace('__eligible_with_refs', '')
        provider = stem.split()[0] if stem else ''
        try:
            xl = pd.ExcelFile(xlsx)
        except Exception:
            continue
        sheet = 'Explicit_Refs_Only' if 'Explicit_Refs_Only' in xl.sheet_names else None
        if not sheet:
            continue
        try:
            df = xl.parse(sheet)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        c_title = find_col(df, ['NOME DA MÚSICA','TÍTULO DA OBRA MUSICAL','Música','TÍTULO'])
        c_author = find_col(df, ['AUTOR'])
        c_isrc = find_col(df, ['ISRC'])
        c_src = '__source_sheet' if '__source_sheet' in df.columns else None
        for _, r in df.iterrows():
            source = norm(r.get(c_src)) if c_src else f"{provider}/{stem}:Explicit_Refs_Only"
            if c_title and pd.notna(r.get(c_title)) and str(r.get(c_title)).strip():
                rows.append({'source_sheet': source, 'term': str(r.get(c_title)).strip(), 'term_type': 'music'})
            if c_author and pd.notna(r.get(c_author)) and str(r.get(c_author)).strip():
                rows.append({'source_sheet': source, 'term': str(r.get(c_author)).strip(), 'term_type': 'author'})
            if c_isrc and pd.notna(r.get(c_isrc)) and str(r.get(c_isrc)).strip():
                rows.append({'source_sheet': source, 'term': str(r.get(c_isrc)).strip(), 'term_type': 'fonogram'})
    out = OUT / 'Explicit_Terms_Index.csv'
    pd.DataFrame(rows).drop_duplicates().to_csv(out, index=False)
    print(f"Wrote: {out} ({len(rows)} terms)")


if __name__ == '__main__':
    main()

