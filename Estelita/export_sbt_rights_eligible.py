#!/usr/bin/env python3
"""
Export SBT (or any supplier file) matches filtered to rights-eligible only,
and enrich with matched reference columns, plus basic amount summaries.

Eligibility (first pass):
- Title appears in OBRAS rows where any column contains 'ESTELITA' (accent-insensitive)
  using 'Unnamed: 4' as the song title column.
- OR supplier EDITORA column contains an Estelita alias (e.g., 'ESTELITA').

Uncertain match flag:
- True when the match was title-only (no author match) based on Supplier_Matches_All.csv.

Usage:
  SUPPLIER_FILE=/path/to/SBT.xls python3 Estelita/export_sbt_rights_eligible.py

Outputs:
- Processed/<basename>__eligible_with_refs.xlsx (filtered/enriched workbook)
- Processed/SBT_Rights_Eligible_Summary.csv (one-line summary for the file)
"""

import os
from pathlib import Path
import unicodedata
import re
import pandas as pd
import duckdb

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "Processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MATCHES_ALL = OUT_DIR / 'Supplier_Matches_All.csv'
ELIGIBLE_CATALOG = OUT_DIR / 'Eligible_Catalog.csv'
ELIGIBLE_ARTISTS = OUT_DIR / 'Eligible_Artists.txt'

def norm(s: str) -> str:
    x = str(s or '').strip().lower()
    x = ' '.join(x.split())
    x = ''.join(c for c in unicodedata.normalize('NFKD', x) if not unicodedata.combining(c))
    return x

def norm_series(s: pd.Series) -> pd.Series:
    return s.astype(str).map(norm)

def parse_brl(value: str) -> float:
    s = str(value or '').strip()
    if s == '' or s.lower() in {'nan','none','null'}:
        return 0.0
    s = s.replace('R$','').replace(' ','')
    # Replace thousands and decimal markers (pt-BR)
    s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0

def find_title_artist_columns(df: pd.DataFrame):
    cols = list(df.columns)
    cn = [norm(c) for c in cols]
    def find_col(options):
        for opt in options:
            for i, v in enumerate(cn):
                if opt in v:
                    return cols[i]
        return None
    c_title = find_col(['titulo da obra musical','titulo da obra','obra musical','musica'])
    if c_title is None:
        c_title = find_col(['titulo original','titulo','title'])
    c_artist = find_col(['intérprete','interprete','artista','autor','artist','author'])
    c_editora = find_col(['editora','publisher'])
    c_valor = find_col(['valor a pagar','valor','montante','amount'])
    c_percent = find_col(['percentual','percent','%'])
    return c_title, c_artist, c_editora, c_valor, c_percent

def eligible_title_norms_from_obras() -> set[str]:
    con = duckdb.connect(str(BASE_DIR / 'primary_archive.duckdb'))
    def qident(s: str) -> str:
        return '"' + s.replace('"','""') + '"'
    cols = [r[1] for r in con.execute('PRAGMA table_info(OBRAS)').fetchall()]
    title_col = 'Unnamed: 4' if 'Unnamed: 4' in cols else cols[0]
    like_clauses = ' OR '.join([f"LOWER(CAST({qident(c)} AS VARCHAR)) LIKE '%estelita%'" for c in cols])
    sql = f"SELECT {qident(title_col)} AS title FROM OBRAS WHERE {like_clauses}"
    try:
        df = con.execute(sql).fetchdf()
    except Exception as e:
        df = pd.DataFrame(columns=['title'])
    con.close()
    if 'title' not in df.columns:
        return set()
    titles = df['title'].astype(str)
    titles_norm = titles.map(lambda s: ''.join(c for c in unicodedata.normalize('NFKD', s.lower().strip()) if not unicodedata.combining(c)))
    titles_norm = titles_norm.str.replace(r"\s+"," ", regex=True)
    return set(titles_norm[titles_norm!=''].unique())

def eligible_iswc_from_obras() -> set[str]:
    con = duckdb.connect(str(BASE_DIR / 'primary_archive.duckdb'))
    def qident(s: str) -> str:
        return '"' + s.replace('"','""') + '"'
    cols = [r[1] for r in con.execute('PRAGMA table_info(OBRAS)').fetchall()]
    like_clauses = ' OR '.join([f"LOWER(CAST({qident(c)} AS VARCHAR)) LIKE '%estelita%'" for c in cols])
    sql = f"SELECT * FROM OBRAS WHERE {like_clauses}"
    try:
        df = con.execute(sql).fetchdf()
    except Exception:
        df = pd.DataFrame()
    con.close()
    iswcs = set()
    if not df.empty:
        for c in df.columns:
            if df[c].dtype == object:
                series = df[c].astype(str)
                for v in series.dropna().unique()[:]:
                    if isinstance(v, str) and v.startswith('T-'):
                        iswcs.add(v.strip())
    return iswcs

def main():
    supplier_file = os.environ.get('SUPPLIER_FILE')
    if not supplier_file:
        raise SystemExit('Please set SUPPLIER_FILE to an .xls/.xlsx path (SBT sheet).')
    xl_path = Path(supplier_file)
    if not xl_path.exists():
        raise SystemExit(f'File not found: {xl_path}')

    # Load matches for this file
    if not MATCHES_ALL.exists():
        raise SystemExit(f'Matches file not found: {MATCHES_ALL}. Run batch_match_suppliers first.')
    m = pd.read_csv(MATCHES_ALL)
    m = m[m['file'] == xl_path.name].copy()
    if m.empty:
        print('No matches found for this file in Supplier_Matches_All.csv')
    # Normalize keys and prep fields
    for c in ['title_norm','author_norm','author_norm_supplier','author_norm_ref']:
        if c in m.columns:
            m[c] = m[c].fillna('').astype(str)
    # Add uncertainty flag: no author_norm pair match
    m['uncertain_match'] = (m['author_norm'] == '') | (m['author_norm_supplier'] == '')

    # Eligible titles/ISWCs from OBRAS and Eligible_Catalog
    eligible_titles = eligible_title_norms_from_obras()
    eligible_iswcs = eligible_iswc_from_obras()
    if ELIGIBLE_CATALOG.exists():
        ec = pd.read_csv(ELIGIBLE_CATALOG)
        if 'title' in ec.columns:
            eligible_titles |= set(ec['title'].astype(str).map(norm).dropna().unique())
        if 'iswc' in ec.columns:
            eligible_iswcs |= set(str(x).strip() for x in ec['iswc'].dropna().astype(str).unique() if str(x).strip())
    eligible_artists = set()
    if ELIGIBLE_ARTISTS.exists():
        try:
            eligible_artists = set(x.strip().lower() for x in ELIGIBLE_ARTISTS.read_text(encoding='utf-8').splitlines() if x.strip())
        except Exception:
            pass
    estelita_aliases = {'estelita', 'eduardo melo pereira', 'eduardo melo pereira ltda'}

    # Read the supplier workbook and filter/enrich per sheet
    xl = pd.ExcelFile(xl_path)
    rows_all = []
    total_amount = 0.0
    for sheet in xl.sheet_names:
        df = xl.parse(sheet)
        if df.empty:
            continue
        c_title, c_artist, c_editora, c_valor, c_percent = find_title_artist_columns(df)
        if c_title is None or c_title not in df.columns:
            continue
        work = df.copy()
        work['__title_norm'] = norm_series(work[c_title])
        if c_artist and c_artist in work.columns:
            work['__author_norm'] = norm_series(work[c_artist])
        else:
            work['__author_norm'] = ''
        # Join to matches to get matched refs and uncertainty
        m_sub = m[['title_norm','author_norm','title_ref','author','uncertain_match']].drop_duplicates()
        work = work.merge(m_sub, how='left', left_on=['__title_norm','__author_norm'], right_on=['title_norm','author_norm'])
        # Title-only enrichment for rows not matched by both
        miss = work['title_ref'].isna()
        if miss.any():
            m_title = m[['title_norm','title_ref','author','uncertain_match']].drop_duplicates()
            work = work.merge(m_title, how='left', left_on='__title_norm', right_on='title_norm', suffixes=('','_titleonly'))
            # Consolidate fields
            work['Matched Title'] = work['title_ref'].fillna(work['title_ref_titleonly'])
            work['Matched Identifier/ISWC'] = work['author'].fillna(work['author_titleonly'])
            work['Uncertain Match'] = work['uncertain_match'].fillna(work['uncertain_match_titleonly']).fillna(True)
        else:
            work['Matched Title'] = work['title_ref']
            work['Matched Identifier/ISWC'] = work['author']
            work['Uncertain Match'] = work['uncertain_match'].fillna(True)
        # Eligibility: title in eligible set OR EDITORA has Estelita alias OR matched ISWC in eligible_iswcs
        eligible_mask = work['__title_norm'].isin(eligible_titles)
        if 'Matched Identifier/ISWC' in work.columns:
            eligible_mask = eligible_mask | work['Matched Identifier/ISWC'].astype(str).isin(eligible_iswcs)
        # Artist-only eligibility
        if c_artist and c_artist in work.columns and eligible_artists:
            artist_norm = norm_series(work[c_artist])
            eligible_mask = eligible_mask | artist_norm.isin(eligible_artists)
        if c_editora and c_editora in work.columns:
            editora_norm = norm_series(work[c_editora])
            has_alias = editora_norm.apply(lambda x: any(a in x for a in estelita_aliases))
            eligible_mask = eligible_mask | has_alias
        # Compose eligibility basis
        basis = []
        basis.append(('title_in_catalog', work['__title_norm'].isin(eligible_titles)))
        if 'Matched Identifier/ISWC' in work.columns:
            basis.append(('iswc_in_catalog', work['Matched Identifier/ISWC'].astype(str).isin(eligible_iswcs)))
        artist_norm = norm_series(work[c_artist]) if c_artist and c_artist in work.columns else pd.Series(['']*len(work))
        basis.append(('artist_alias', artist_norm.isin(eligible_artists) if len(artist_norm) else pd.Series([False]*len(work))))
        if c_editora and c_editora in work.columns:
            editora_norm = norm_series(work[c_editora])
            basis.append(('editora_alias', editora_norm.apply(lambda x: any(a in x for a in estelita_aliases))))
        # Build basis string per row
        basis_df = pd.DataFrame({name: mask for name, mask in basis})
        work['Eligibility Basis'] = basis_df.apply(lambda r: '+'.join([k for k,v in r.items() if v]), axis=1)
        # Eligible if any basis present
        eligible_df = work[(basis_df.any(axis=1))].copy()
        if eligible_df.empty:
            continue
        # Sum monetary amounts if present (define local parser here to avoid scope issues)
        if c_valor and c_valor in eligible_df.columns:
            def _parse_brl(v):
                s = str(v or '').strip().replace('R$','').replace(' ','')
                s = s.replace('.', '').replace(',', '.')
                try:
                    return float(s)
                except Exception:
                    return 0.0
            eligible_df['__valor_float'] = eligible_df[c_valor].apply(_parse_brl)
            total_amount += float(eligible_df['__valor_float'].sum())
            eligible_df = eligible_df.drop(columns=['__valor_float'])
        eligible_df['__source_sheet'] = sheet
        rows_all.append(eligible_df)

    if not rows_all:
        print('No eligible matches found to export.')
        return
    full = pd.concat(rows_all, ignore_index=True)
    # Split into two tabs
    explicit_mask = (full['Matched Title'].astype(str).str.strip()!='') | (full['Matched Identifier/ISWC'].astype(str).str.strip()!='')
    explicit = full[explicit_mask].copy()
    alias_only = full[~explicit_mask].copy()

    # Keep useful columns and drop helpers
    def cleanup(df):
        drop_cols = [c for c in df.columns if c.startswith('title_norm') or c in ('author_norm','title_ref','author','title_norm_titleonly','title_ref_titleonly','author_titleonly','uncertain_match_titleonly','__title_norm','__author_norm','title_norm_titleonly')]
        return df.drop(columns=drop_cols, errors='ignore')
    explicit = cleanup(explicit)
    alias_only = cleanup(alias_only)

    out_xlsx = OUT_DIR / (xl_path.stem + '__eligible_with_refs.xlsx')
    with pd.ExcelWriter(out_xlsx) as wr:
        explicit.to_excel(wr, sheet_name='Explicit_Refs_Only', index=False)
        alias_only.to_excel(wr, sheet_name='Artist_Alias_Eligible', index=False)
    print(f'Saved eligible workbook: {out_xlsx}')

    # Summary CSV
    summary = pd.DataFrame([
        {'file': xl_path.name,
         'eligible_rows_total': len(full),
         'explicit_rows': len(explicit),
         'alias_only_rows': len(alias_only),
         'sum_valor_editora_brl': round(total_amount, 2)}
    ])
    out_sum = OUT_DIR / 'SBT_Rights_Eligible_Summary.csv'
    summary.to_csv(out_sum, index=False)
    print(f'Summary saved: {out_sum}')

    # Print counts and top-20 explicit by amount
    def parse_brl(value: str) -> float:
        s = str(value or '').strip().replace('R$','').replace(' ','')
        s = s.replace('.', '').replace(',', '.')
        try:
            return float(s)
        except Exception:
            return 0.0
    amt_col = next((c for c in explicit.columns if 'VALOR' in c.upper() and 'EDITORA' in c.upper()), None)
    if amt_col:
        explicit['__amount'] = explicit[amt_col].apply(parse_brl)
        explicit_sorted = explicit.sort_values('__amount', ascending=False)
        cols_show = [c for c in ['DATA DE EXIBIÇÃO','PROGRAMA','EDITORA','NOME DA MÚSICA','INTERPRETE','PERCENTUAL A PAGAR - EDITORA',amt_col,'Matched Title','Matched Identifier/ISWC','Eligibility Basis'] if c in explicit_sorted.columns]
        print('EXPLICIT_COUNTS', len(explicit_sorted))
        print('EXPLICIT_TOP20_START')
        for _, r in explicit_sorted.head(20).iterrows():
            parts = [f"{c}: {r.get(c,'')}" for c in cols_show]
            print(' - ' + ' | '.join(parts))
        print('EXPLICIT_TOP20_END')

if __name__ == '__main__':
    main()
