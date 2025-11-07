#!/usr/bin/env python3
"""
Prepare curated list of song titles and authors, analyze missing columns,
and optionally match a supplier sheet against the curated list.

Outputs:
- Processed/Curated_Titles_Authors.csv
- Processed/_logs/Curated_Analysis.json
- If SUPPLIER_FILE is provided: Processed/Supplier_Matches.csv
"""

from pathlib import Path
import os
import re
import json
import duckdb
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "primary_archive.duckdb"
OUT_DIR = BASE_DIR / "Processed"
LOG_DIR = OUT_DIR / "_logs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(DB_PATH))

def q(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'

def normalize_text(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().str.lower()
    # collapse whitespace
    s = s.str.replace(r"\s+", " ", regex=True)
    # remove accents via DuckDB can be heavy; do lightweight ASCII fold here
    try:
        import unicodedata
        s = s.apply(lambda x: ''.join(c for c in unicodedata.normalize('NFKD', x) if not unicodedata.combining(c)))
    except Exception:
        pass
    return s

def load_works_and_authors(sample_rows: int | None = None) -> pd.DataFrame:
    # Titles and authors from OBRAS raw table
    o = con.execute(f'SELECT {q("Unnamed: 4")} AS title_raw, {q("Unnamed: 6")} AS autor6, {q("Unnamed: 2")} AS autor2 FROM OBRAS').fetchdf()
    o['title'] = o['title_raw']
    o['title_norm'] = normalize_text(o['title'])
    invalid = {'', 'none', 'nan', 'null'}
    o.loc[o['title_norm'].isin(invalid), 'title_norm'] = ''
    # Remove headers/noise
    bad_tokens = ['titulo principal da obra','tipo obra','pagina','ass. respons','relatorio analitico']
    for tok in bad_tokens:
        o.loc[o['title_norm'].str.contains(tok, na=False), 'title_norm'] = ''
    o = o[(o['title_norm'].notna()) & (o['title_norm']!='')]

    # Pick authors: prefer autor6 if it looks like a name, else autor2
    def choose_author(row):
        for c in ['autor6','autor2']:
            v = str(row.get(c, '') or '').strip()
            if not v or v.lower() in {'nan','none','null'}:
                continue
            # contains letters and not only numbers/symbols
            if re.search(r'[a-zA-Z]', v) and not re.fullmatch(r'[0-9\-., ]+', v):
                return v
        return None

    o['author_raw'] = o.apply(choose_author, axis=1)

    # Split and explode authors
    def split_authors(s: str) -> list[str]:
        if not isinstance(s, str):
            return []
        s = s.strip()
        if not s or s.lower() in {'nan','none','null'}:
            return []
        parts = re.split(r"\s*[,/;&]|\s+e\s+", s)
        parts = [p.strip() for p in parts if p and p.strip()]
        return parts[:6]

    rows = []
    for _, r in o.iterrows():
        als = split_authors(r.get('author_raw'))
        if not als:
            rows.append({'title': str(r['title']).strip(), 'title_norm': r['title_norm'], 'author': None, 'author_norm': None, 'source': 'OBRAS'})
        else:
            for a in als:
                rows.append({'title': str(r['title']).strip(), 'title_norm': r['title_norm'], 'author': a, 'author_norm': normalize_text(pd.Series([a])).iloc[0], 'source': 'OBRAS'})

    df = pd.DataFrame(rows)
    # Remove invalids in plain title too
    df['title'] = df['title'].fillna('')
    df['title_clean'] = normalize_text(df['title'])
    df = df[~df['title_clean'].isin({'', 'none', 'nan', 'null'})]
    df = df.drop(columns=['title_clean'])
    df = df.drop_duplicates(subset=['title_norm','author_norm'])
    if sample_rows:
        df = df.head(sample_rows)
    return df

def analyze_missing(df: pd.DataFrame) -> dict:
    total = len(df)
    missing_author = int(df['author'].isna().sum())
    missing_ratio = round(100.0 * missing_author / total, 2) if total else 0.0
    sample_titles = df[df['author'].isna()].head(20)['title'].tolist()
    return {
        'total_rows': total,
        'missing_author_rows': missing_author,
        'missing_author_pct': missing_ratio,
        'missing_author_sample_titles': sample_titles,
    }

def save_curated(df: pd.DataFrame):
    out_csv = OUT_DIR / 'Curated_Titles_Authors.csv'
    df[['title','author']].to_csv(out_csv, index=False)
    return out_csv

def read_supplier_sheet(path: Path) -> pd.DataFrame:
    # Try to auto-detect title/artist columns from the first worksheet
    import unicodedata
    def fold(s: str) -> str:
        s = str(s)
        s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
        return s.lower()

    xl = pd.ExcelFile(path)
    df = xl.parse(xl.sheet_names[0])
    cols_norm = [fold(c) for c in df.columns]
    def find_col(options):
        for opt in options:
            for i, cn in enumerate(cols_norm):
                if opt in cn:
                    return df.columns[i]
        return None
    # Prefer explicit song title columns first
    c_title = find_col(['titulo da obra musical','titulo da obra','obra musical','musica'])
    if c_title is None:
        c_title = find_col(['titulo original','titulo','title'])
    c_artist = find_col(['intérprete','interprete','artista','autor','artist','author'])
    if c_title is None:
        # fall back to any non-empty first col
        c_title = df.columns[0]
    cols = [c for c in [c_title, c_artist] if c is not None]
    sdf = df[cols].copy()
    rename_map = {c_title: 'title'}
    if c_artist is not None:
        rename_map[c_artist] = 'artist'
    sdf = sdf.rename(columns=rename_map)
    if 'artist' not in sdf.columns:
        sdf['artist'] = None
    return sdf

def match_supplier(curated: pd.DataFrame, supplier_df: pd.DataFrame) -> pd.DataFrame:
    s = supplier_df.copy()
    s['title_norm'] = normalize_text(s['title'])
    if 'artist' in s.columns:
        s['author_norm'] = normalize_text(s['artist'])
    else:
        s['author_norm'] = None

    c = curated.copy()
    # Title+author first
    both = s.merge(c, on=['title_norm','author_norm'], how='inner', suffixes=('_supplier','_ref'))
    # Title-only for the unmatched by normalized keys
    matched_keys = both[['title_norm','author_norm']].drop_duplicates()
    unmatched = s.merge(matched_keys, on=['title_norm','author_norm'], how='left', indicator=True)
    still = unmatched[unmatched['_merge']=='left_only'].drop(columns=['_merge'])
    title_only = still.merge(c[['title_norm','title','author','author_norm']], on='title_norm', how='inner', suffixes=('_supplier','_ref'))
    return pd.concat([both, title_only], ignore_index=True)

def main():
    curated = load_works_and_authors()
    analysis = analyze_missing(curated)
    out_csv = save_curated(curated)
    with open(LOG_DIR / 'Curated_Analysis.json', 'w') as f:
        json.dump(analysis, f, indent=2)
    print(f"✅ Curated list saved: {out_csv}")
    print(f"   Total rows: {analysis['total_rows']} | Missing author: {analysis['missing_author_pct']}%")

    supplier_file = os.environ.get('SUPPLIER_FILE')
    if supplier_file and Path(supplier_file).exists():
        print(f"📄 Matching supplier sheet: {supplier_file}")
        df_sup = read_supplier_sheet(Path(supplier_file))
        matches = match_supplier(curated, df_sup)
        out_matches = OUT_DIR / 'Supplier_Matches.csv'
        matches.to_csv(out_matches, index=False)
        print(f"✅ Matches: {len(matches)} | Saved: {out_matches}")
    else:
        if supplier_file:
            print(f"⚠️ Supplier file not found: {supplier_file}")
        else:
            print("ℹ️ No supplier file provided. Set SUPPLIER_FILE env var to an .xlsx to run matching.")

if __name__ == '__main__':
    main()
