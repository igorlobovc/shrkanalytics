#!/usr/bin/env python3
"""
Export a filtered copy of a supplier Excel file containing only rows that match
the curated titles/authors list.

Usage:
  SUPPLIER_FILE=/path/to/file.xls[x] python3 Estelita/export_matches_from_supplier_file.py

Outputs:
  - Estelita/Processed/<basename>__matches_only.xlsx
"""

import os
from pathlib import Path
import unicodedata
import re
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "Processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def normalize_text_py(text: str) -> str:
    s = str(text or "").strip().lower()
    s = " ".join(s.split())
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s

def normalize_series(s: pd.Series) -> pd.Series:
    return s.astype(str).map(normalize_text_py)

def find_title_artist_columns(df: pd.DataFrame):
    cols = list(df.columns)
    cn = [normalize_text_py(c) for c in cols]
    def find_col(options):
        for opt in options:
            for i, x in enumerate(cn):
                if opt in x:
                    return cols[i]
        return None
    # Prefer explicit music title columns first
    c_title = find_col(['titulo da obra musical','titulo da obra','obra musical','musica'])
    if c_title is None:
        c_title = find_col(['titulo original','titulo','title'])
    c_artist = find_col(['intérprete','interprete','artista','autor','artist','author'])
    if c_title is None and cols:
        c_title = cols[0]
    return c_title, c_artist

def load_curated() -> pd.DataFrame:
    curated_csv = OUT_DIR / 'Curated_Titles_Authors.csv'
    if not curated_csv.exists():
        raise SystemExit(f"Curated list not found: {curated_csv}")
    c = pd.read_csv(curated_csv)
    # Ensure columns present
    if 'author' not in c.columns:
        c['author'] = None
    c['title_norm'] = normalize_series(c['title'])
    c['author_norm'] = normalize_series(c['author'])
    return c[['title','author','title_norm','author_norm']]

def filter_matching_rows(xl_path: Path, curated: pd.DataFrame) -> dict:
    # Returns dict of {sheet_name: filtered_df}
    keep = {}
    c_titles = set(curated['title_norm'].dropna().unique())
    c_pairs = set(curated[['title_norm','author_norm']].dropna().itertuples(index=False, name=None))
    try:
        xl = pd.ExcelFile(xl_path)
    except Exception as e:
        raise SystemExit(f"Failed to open {xl_path}: {e}")
    for sheet in xl.sheet_names:
        try:
            df = xl.parse(sheet)
        except Exception:
            continue
        if df.empty:
            continue
        c_title, c_artist = find_title_artist_columns(df)
        if c_title is None or c_title not in df.columns:
            continue
        work = df.copy()
        work['__title_norm'] = normalize_series(work[c_title])
        if c_artist and c_artist in work.columns:
            work['__author_norm'] = normalize_series(work[c_artist])
        else:
            work['__author_norm'] = None
        work['__is_match'] = work['__title_norm'].isin(c_titles)
        # If author present, prioritize exact pair matches as well
        if work['__author_norm'].notna().any():
            pair_mask = work.apply(lambda r: (r['__title_norm'], r['__author_norm']) in c_pairs, axis=1)
            work['__is_match'] = work['__is_match'] | pair_mask
        filtered = work[work['__is_match']].copy()
        if not filtered.empty:
            keep[sheet] = filtered
    return keep

def main():
    supplier_file = os.environ.get('SUPPLIER_FILE')
    if not supplier_file:
        raise SystemExit("Please set SUPPLIER_FILE to an .xlsx/.xls path.")
    xl_path = Path(supplier_file)
    if not xl_path.exists():
        raise SystemExit(f"File not found: {xl_path}")

    curated = load_curated()
    sheets = filter_matching_rows(xl_path, curated)
    # Optional enrichment using aggregated matches file
    matches_all_path = OUT_DIR / 'Supplier_Matches_All.csv'
    matches_df = None
    if matches_all_path.exists():
        try:
            m = pd.read_csv(matches_all_path)
            # Filter to this source file name
            m = m[m['file'] == xl_path.name]
            # Keep distinct mapping keys
            m = m[['title_norm','author_norm','title_ref','author']].drop_duplicates()
            # Normalize key types
            m['title_norm'] = m['title_norm'].fillna('').astype(str)
            m['author_norm'] = m['author_norm'].fillna('').astype(str)
            # Rename to avoid collisions with supplier columns
            m = m.rename(columns={'title_ref': '__matched_title', 'author': '__matched_identifier'})
            # Prepare helper for title-only fallback
            m_title_only = (m.groupby('title_norm')
                              .agg(__matched_title=('__matched_title','first'), __matched_identifier=('__matched_identifier','first'))
                              .reset_index())
            matches_df = (m, m_title_only)
        except Exception:
            matches_df = None
    if not sheets:
        print("No matching rows found in any sheet.")
        return
    # Write enriched workbook
    suffix = "__matches_only_with_refs.xlsx" if matches_df else "__matches_only.xlsx"
    out_path = OUT_DIR / (xl_path.stem + suffix)
    with pd.ExcelWriter(out_path) as wr:
        for name, fdf in sheets.items():
            dfw = fdf.copy()
            if matches_df:
                # Recompute normalized keys for the filtered slice
                c_title, c_artist = find_title_artist_columns(dfw)
                dfw['__title_norm'] = normalize_series(dfw[c_title]) if c_title in dfw.columns else ''
                if c_artist and c_artist in dfw.columns:
                    dfw['__author_norm'] = normalize_series(dfw[c_artist])
                else:
                    dfw['__author_norm'] = ''
                # Ensure string key types
                dfw['__title_norm'] = dfw['__title_norm'].fillna('').astype(str)
                dfw['__author_norm'] = dfw['__author_norm'].fillna('').astype(str)
                m, m_title_only = matches_df
                # Build key maps for robust enrichment
                dict_both = {(row['title_norm'], row['author_norm']): (row['__matched_title'], row['__matched_identifier']) for _, row in m.iterrows()}
                dict_title = {row['title_norm']: (row['__matched_title'], row['__matched_identifier']) for _, row in m_title_only.iterrows()}
                keys = list(zip(dfw['__title_norm'], dfw['__author_norm']))
                # Map both keys
                matched = [dict_both.get(k) for k in keys]
                mt = [t[0] if t else None for t in matched]
                mi = [t[1] if t else None for t in matched]
                # Fallback map by title only where missing
                miss_idx = [i for i,v in enumerate(mt) if v is None]
                if miss_idx:
                    for i in miss_idx:
                        tup = dict_title.get(dfw.iloc[i]['__title_norm'])
                        if tup:
                            mt[i], mi[i] = tup
                dfw['Matched Title'] = mt
                dfw['Matched Identifier/ISWC'] = mi
                # Cleanup helper columns
                dfw = dfw.drop(columns=[c for c in dfw.columns if c.startswith('__') or c in ('title_norm','author_norm')], errors='ignore')
            else:
                # No enrichment, drop helper columns if any
                for col in ['__title_norm','__author_norm','__is_match']:
                    if col in dfw.columns:
                        del dfw[col]
            dfw.to_excel(wr, sheet_name=name[:31] or 'Sheet1', index=False)
    print(f"Saved filtered workbook: {out_path}")

if __name__ == '__main__':
    main()
