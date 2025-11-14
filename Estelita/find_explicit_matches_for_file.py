#!/usr/bin/env python3
"""
Find explicit matches for a single fornecedor workbook by matching each sheet
against the curated Estelita catalog.

Environment:
  SUPPLIER_FILE=/path/to/workbook.xlsx (required)

Output:
  Estelita/Processed/Summaries/<stem>__matches_with_sheet.csv
    Columns: provider, supplier_file, sheet, supplier_title, supplier_artist,
             matched_term, matched_identifier, match_type
"""

from __future__ import annotations

import os
from pathlib import Path
import unicodedata
import pandas as pd

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'
SUM = PROC / 'Summaries'
SUM.mkdir(parents=True, exist_ok=True)


def norm_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().str.lower()
    s = s.str.replace(r"\s+", " ", regex=True)
    try:
        s = s.apply(lambda x: ''.join(c for c in unicodedata.normalize('NFKD', x) if not unicodedata.combining(c)))
    except Exception:
        pass
    return s


def load_curated() -> pd.DataFrame:
    path = PROC / 'Curated_Titles_Authors.csv'
    if not path.exists():
        raise SystemExit('Curated_Titles_Authors.csv not found. Run prepare_titles_and_match_suppliers.py first.')
    df = pd.read_csv(path)
    df = df.fillna('')
    df['title_norm'] = norm_series(df['title'])
    df['author_norm'] = norm_series(df['author'])
    return df[['title','author','title_norm','author_norm']]


def detect_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    cols = list(df.columns)
    cn = [norm_series(pd.Series([c])).iloc[0] for c in cols]

    def find_col(options: list[str]):
        for opt in options:
            optn = norm_series(pd.Series([opt])).iloc[0]
            for i, c in enumerate(cn):
                if optn in c:
                    return cols[i]
        return None

    c_title = find_col(['titulo da obra musical','titulo da obra','obra musical','musica','titulo','title'])
    c_artist = find_col(['intérprete','interprete','artista','autor','artist','author'])
    if c_title is None and cols:
        c_title = cols[0]
    return c_title, c_artist


def match_sheet(curated: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    c_title, c_artist = detect_columns(df)
    cols = [c_title] + ([c_artist] if c_artist else [])
    sdf = df[cols].copy()
    sdf = sdf.rename(columns={c_title: 'title', c_artist: 'artist'} if c_artist else {c_title: 'title'})
    if 'artist' not in sdf.columns:
        sdf['artist'] = None
    sdf['title_norm'] = norm_series(sdf['title'])
    sdf['author_norm'] = norm_series(sdf['artist'])

    curated = curated.copy()
    # Title + author match
    both = sdf.merge(curated, on=['title_norm','author_norm'], how='inner', suffixes=('_supplier','_ref'))
    both['match_type'] = 'title_author'

    matched_keys = both[['title_norm','author_norm']].drop_duplicates()
    still = sdf.merge(matched_keys, on=['title_norm','author_norm'], how='left', indicator=True)
    still = still[still['_merge']=='left_only'].drop(columns=['_merge'])
    title_only = still.merge(curated[['title_norm','title','author','author_norm']], on='title_norm', how='inner', suffixes=('_supplier','_ref'))
    title_only['match_type'] = 'title_only'

    out = pd.concat([both, title_only], ignore_index=True)
    out = out.rename(columns={'title_supplier':'supplier_title','title':'supplier_title',
                              'artist_supplier':'supplier_artist','artist':'supplier_artist',
                              'title_ref':'matched_term','author':'matched_identifier'})
    if 'matched_term' not in out.columns and 'title' in out.columns:
        out['matched_term'] = out['title']
    if 'matched_identifier' not in out.columns:
        out['matched_identifier'] = ''
    return out[['supplier_title','supplier_artist','matched_term','matched_identifier','match_type']]


def main():
    supplier_file = os.environ.get('SUPPLIER_FILE')
    if not supplier_file:
        raise SystemExit('Set SUPPLIER_FILE to the workbook to analyze.')
    path = Path(supplier_file)
    if not path.exists():
        raise SystemExit(f'Supplier file not found: {path}')

    curated = load_curated()
    xl = pd.ExcelFile(path)
    all_rows = []
    provider = path.parent.name or 'Supplier'
    for sheet in xl.sheet_names:
        try:
            df = xl.parse(sheet)
        except Exception:
            continue
        matches = match_sheet(curated, df)
        if matches.empty:
            continue
        matches.insert(0, 'sheet', sheet)
        matches.insert(0, 'supplier_file', path.name)
        matches.insert(0, 'provider', provider)
        all_rows.append(matches)

    if not all_rows:
        print('No matches found in workbook.')
        return

    result = pd.concat(all_rows, ignore_index=True)
    out = SUM / f"{path.stem}__matches_with_sheet.csv"
    result.to_csv(out, index=False)
    print(f"Wrote matches: {out} ({len(result)} rows)")


if __name__ == '__main__':
    main()
