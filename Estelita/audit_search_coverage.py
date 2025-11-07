#!/usr/bin/env python3
"""
Audit search coverage across supplier files (Raw/Fornecedores and Raw/Unified):
- For each file/sheet, report how many rows contain:
  - title match (exact normalized title)
  - author match (exact normalized author)
  - iswc (pattern T-...)
  - isrc (pattern)
  - publisher alias (substring match)
  - eligible artist (exact)

Outputs:
- Estelita/Processed/Supplier_Search_Coverage.csv
  columns: provider, file, sheet, total_rows, title_rows, author_rows,
           iswc_rows, isrc_rows, publisher_alias_rows, eligible_artist_rows
"""

from __future__ import annotations

import re
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
RAW_F = BASE / 'Raw' / 'Fornecedores'
RAW_U = BASE / 'Raw' / 'Unified'
PROC = BASE / 'Processed'
PROC.mkdir(parents=True, exist_ok=True)


def norm(s: str) -> str:
    s = str(s or '').strip().lower()
    try:
        import unicodedata
        s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    except Exception:
        pass
    s = ' '.join(s.split())
    return s


def load_searchable() -> dict[str, set[str]]:
    path = PROC / 'Searchable_Base.csv'
    df = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=['key_norm','key_type'])
    groups: dict[str, set[str]] = {}
    for k, grp in df.groupby('key_type'):
        groups[k] = set(str(x).strip() for x in grp['key_norm'].dropna().astype(str))
    return groups


def iter_supplier_files() -> list[Path]:
    out = []
    for root in [RAW_F, RAW_U]:
        if root.exists():
            out.extend([p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.xlsx','.xls'}])
    return sorted(out)


def provider_from_path(p: Path) -> str:
    try:
        # First directory level for Fornecedores
        rel = p.relative_to(RAW_F)
        return rel.parts[0]
    except Exception:
        pass
    # For Unified, use filename stem heuristic
    s = p.stem.lower()
    if 'sbt' in s: return 'SBT'
    if 'globo' in s: return 'Globo'
    if 'canal' in s: return 'Canal Brasil'
    if 'aparecida' in s: return 'Aparecida'
    if 'band ' in s or s.startswith('band '): return 'Band'
    if 'clipes' in s: return 'Clipes'
    return 'Desconhecido'


def coverage_for_sheet(df: pd.DataFrame, keys: dict[str,set[str]]) -> dict[str,int]:
    total = int(len(df))
    # flatten all text cells by column
    cols = list(df.columns)
    # normalized strings per cell row-wise
    norm_df = df.astype(str).map(norm)

    # For sheet-level counts, check any column match per row
    def count_rows_any_match(df_text: pd.DataFrame, keyset: set[str], substring=False) -> int:
        if not keyset:
            return 0
        if substring:
            row_mask = df_text.apply(lambda r: any(any(k in v for k in keyset) for v in r.values), axis=1)
        else:
            row_mask = df_text.apply(lambda r: any(v in keyset for v in r.values), axis=1)
        return int(row_mask.sum())

    title_rows = count_rows_any_match(norm_df, keys.get('title', set()))
    author_rows = count_rows_any_match(norm_df, keys.get('author', set()))
    eligible_artist_rows = count_rows_any_match(norm_df, keys.get('eligible_artist', set()))
    publisher_alias_rows = count_rows_any_match(norm_df, keys.get('publisher_alias', set()), substring=True)

    # ISWC / ISRC patterns (detect anywhere)
    joined = norm_df.astype(str).agg(' '.join, axis=1)
    iswc_rows = int(joined.str.contains(r'\bT-[0-9.]+-[0-9xX]\b', regex=True).sum())
    isrc_rows = int(joined.str.contains(r'\b[A-Z]{2}[A-Z0-9]{3}\d{7}\b', case=False, regex=True).sum())

    return {
        'total_rows': total,
        'title_rows': title_rows,
        'author_rows': author_rows,
        'eligible_artist_rows': eligible_artist_rows,
        'publisher_alias_rows': publisher_alias_rows,
        'iswc_rows': iswc_rows,
        'isrc_rows': isrc_rows,
    }


def main():
    keys = load_searchable()
    rows = []
    files = iter_supplier_files()
    for path in files:
        prov = provider_from_path(path)
        try:
            xl = pd.ExcelFile(path)
        except Exception:
            continue
        for sheet in xl.sheet_names:
            try:
                df = xl.parse(sheet)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            cov = coverage_for_sheet(df, keys)
            rows.append({
                'provider': prov,
                'file': path.name,
                'sheet': sheet,
                **cov,
            })

    out = PROC / 'Supplier_Search_Coverage.csv'
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote: {out} ({len(rows)} sheet rows)")


if __name__ == '__main__':
    main()
