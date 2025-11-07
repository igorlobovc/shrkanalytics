#!/usr/bin/env python3
"""
Batch-match all supplier sheets under a directory against the curated titles+authors.

Outputs in Estelita/Processed/:
- Supplier_Matches_All.csv (all matched rows)
- Suppliers_Coverage_Summary.csv (coverage per provider)
- Suppliers_Top_Unmatched.csv (top unmatched titles with counts)
"""

import os
from pathlib import Path
import re
import unicodedata
import duckdb
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "primary_archive.duckdb"
OUT_DIR = BASE_DIR / "Processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = OUT_DIR / "_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIER_DIR = Path(os.environ.get('SUPPLIER_DIR', "/Users/igorcunha/SHRKVSCODE/Estelita/Raw/Fornecedores"))

def normalize_text_py(text: str) -> str:
    s = str(text or "").strip().lower()
    s = " ".join(s.split())
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return s

def normalize_series(s: pd.Series) -> pd.Series:
    return s.astype(str).map(normalize_text_py)

def build_curated_if_missing() -> Path:
    curated_csv = OUT_DIR / 'Curated_Titles_Authors.csv'
    if curated_csv.exists():
        return curated_csv
    # Build curated from OBRAS (same logic as prepare_titles_and_match_suppliers)
    con = duckdb.connect(str(DB_PATH))
    q = lambda x: '"'+x.replace('"','""')+'"'
    o = con.execute(f'SELECT {q("Unnamed: 4")} AS title_raw, {q("Unnamed: 6")} AS autor6, {q("Unnamed: 2")} AS autor2 FROM OBRAS').fetchdf()
    con.close()
    o['title'] = o['title_raw']
    o['title_norm'] = normalize_series(o['title'])
    invalid = {'', 'none', 'nan', 'null'}
    o.loc[o['title_norm'].isin(invalid), 'title_norm'] = ''
    bad_tokens = ['titulo principal da obra','tipo obra','pagina','ass. respons','relatorio analitico']
    for tok in bad_tokens:
        o.loc[o['title_norm'].str.contains(tok, na=False), 'title_norm'] = ''
    o = o[(o['title_norm'].notna()) & (o['title_norm']!='')]
    def choose_author(row):
        for c in ['autor6','autor2']:
            v = str(row.get(c, '') or '').strip()
            if not v or v.lower() in {'nan','none','null'}:
                continue
            if re.search(r'[a-zA-Z]', v) and not re.fullmatch(r'[0-9\-., ]+', v):
                return v
        return None
    o['author_raw'] = o.apply(choose_author, axis=1)
    def split_authors(s: str) -> list[str]:
        if not isinstance(s, str):
            return []
        s = s.strip()
        if not s or s.lower() in {'nan','none','null'}:
            return []
        parts = re.split(r"\s*[,/;&]|\s+e\s+", s)
        return [p.strip() for p in parts if p and p.strip()][:6]
    rows = []
    for _, r in o.iterrows():
        als = split_authors(r.get('author_raw'))
        if not als:
            rows.append({'title': str(r['title']).strip(), 'title_norm': r['title_norm'], 'author': None, 'author_norm': None})
        else:
            for a in als:
                rows.append({'title': str(r['title']).strip(), 'title_norm': r['title_norm'], 'author': a, 'author_norm': normalize_text_py(a)})
    df = pd.DataFrame(rows).drop_duplicates(subset=['title_norm','author_norm'])
    df[['title','author']].to_csv(curated_csv, index=False)
    return curated_csv

def find_title_artist_columns(df: pd.DataFrame):
    # Accent folding for header detection
    def fold(s: str) -> str:
        return normalize_text_py(s)
    cols = list(df.columns)
    cn = [fold(c) for c in cols]
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
    if c_title is None:
        # fallback to first non-empty column
        c_title = cols[0]
    return c_title, c_artist

def read_supplier_any(path: Path) -> pd.DataFrame:
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return pd.DataFrame()
    for sheet in xl.sheet_names:
        try:
            df = xl.parse(sheet)
        except Exception:
            continue
        c_title, c_artist = find_title_artist_columns(df)
        if c_title is None:
            continue
        sdf = df[[c for c in [c_title, c_artist] if c is not None]].copy()
        rename_map = {c_title: 'title'}
        if c_artist is not None:
            rename_map[c_artist] = 'artist'
        sdf = sdf.rename(columns=rename_map)
        if 'title' in sdf.columns:
            sdf['title'] = sdf['title'].astype(str)
            # consider a sheet valid if at least 5 non-empty titles
            nonempty = (sdf['title'].astype(str).str.strip()!='').sum()
            if nonempty >= 5:
                return sdf
    return pd.DataFrame()

def match_supplier_df(curated: pd.DataFrame, supplier_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if supplier_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    s = supplier_df.copy()
    s = s.rename(columns=lambda x: x.lower())
    if 'artist' not in s.columns:
        s['artist'] = None
    s['title_norm'] = normalize_series(s['title'])
    s['author_norm'] = normalize_series(s['artist'])
    s = s[s['title_norm']!='']

    c = curated.copy()
    c['title_norm'] = normalize_series(c['title'])
    c['author_norm'] = normalize_series(c['author'])

    # Tier 1: title+author
    both = s.merge(c, on=['title_norm','author_norm'], how='inner', suffixes=('_supplier','_ref'))
    # Compute unmatched keys and Title-only
    matched_keys = both[['title_norm','author_norm']].drop_duplicates()
    unmatched = s.merge(matched_keys, on=['title_norm','author_norm'], how='left', indicator=True)
    still = unmatched[unmatched['_merge']=='left_only'].drop(columns=['_merge'])
    title_only = still.merge(c[['title_norm','title','author','author_norm']], on='title_norm', how='inner', suffixes=('_supplier','_ref'))
    matched = pd.concat([both, title_only], ignore_index=True)

    # Build unmatched rows (after both tiers)
    matched_titles = matched[['title_norm']].drop_duplicates()
    unmatched_final = s.merge(matched_titles, on='title_norm', how='left', indicator=True)
    unmatched_final = unmatched_final[unmatched_final['_merge']=='left_only'].drop(columns=['_merge'])

    return matched, unmatched_final

def main():
    curated_csv = build_curated_if_missing()
    curated = pd.read_csv(curated_csv)

    files = [p for p in SUPPLIER_DIR.rglob('*') if p.is_file() and p.suffix.lower() in {'.xlsx','.xls'}]
    if not files:
        print(f"No supplier files found under {SUPPLIER_DIR}")
        return

    provider_stats = {}
    all_matches = []
    all_unmatched = []

    for path in files:
        # Provider is first-level folder under SUPPLIER_DIR
        try:
            rel = path.relative_to(SUPPLIER_DIR)
            provider = rel.parts[0] if len(rel.parts) > 1 else rel.stem
        except Exception:
            provider = path.parent.name

        sdf = read_supplier_any(path)
        if sdf.empty:
            continue
        matches, unmatched = match_supplier_df(curated, sdf)

        # annotate
        for df, kind in [(matches,'match'),(unmatched,'unmatched')]:
            if df is not None and not df.empty:
                df['provider'] = provider
                df['file'] = path.name

        total = int((sdf['title'].astype(str).str.strip()!='').sum())
        matched_count = int(matches['title_norm'].nunique()) if not matches.empty else 0
        provider_stats.setdefault(provider, {'total':0,'matched':0})
        provider_stats[provider]['total'] += total
        provider_stats[provider]['matched'] += matched_count

        if not matches.empty:
            all_matches.append(matches)
        if not unmatched.empty:
            all_unmatched.append(unmatched[['title','artist','title_norm','author_norm','provider','file']])

    # Save matches
    if all_matches:
        matches_all = pd.concat(all_matches, ignore_index=True)
        matches_all.to_csv(OUT_DIR / 'Supplier_Matches_All.csv', index=False)
        print(f"Saved matches: {len(matches_all)}")
    else:
        print("No matches found.")

    # Coverage summary
    rows = []
    for prov, st in sorted(provider_stats.items()):
        total = st['total']
        matched = st['matched']
        pct = round(100.0*matched/total, 2) if total else 0.0
        rows.append({'provider': prov, 'total_rows': total, 'matched_titles': matched, 'coverage_pct': pct})
    cov_df = pd.DataFrame(rows)
    cov_df.to_csv(OUT_DIR / 'Suppliers_Coverage_Summary.csv', index=False)
    print(f"Coverage summary saved: {OUT_DIR / 'Suppliers_Coverage_Summary.csv'}")

    # Top unmatched titles (global)
    if all_unmatched:
        un = pd.concat(all_unmatched, ignore_index=True)
        top = (un.groupby('title_norm')
                 .agg(title_example=('title','first'), providers=('provider','nunique'), count=('title_norm','count'))
                 .reset_index()
                 .sort_values('count', ascending=False)
                 .head(50))
        top.to_csv(OUT_DIR / 'Suppliers_Top_Unmatched.csv', index=False)
        print(f"Top unmatched saved: {OUT_DIR / 'Suppliers_Top_Unmatched.csv'}")
    else:
        print("No unmatched rows captured.")

if __name__ == '__main__':
    main()

