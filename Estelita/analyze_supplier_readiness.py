#!/usr/bin/env python3
"""
Analyze supplier files under Fornecedores and score readiness per sheet/file.

Outputs:
- Processed/Suppliers_Readiness_Report.csv (per-file metrics + readiness_score)
- Processed/Suppliers_Readiness_Top.csv (sorted by readiness_score desc)
"""

import os
import re
from pathlib import Path
import unicodedata
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "Processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUPPLIER_DIR = Path(os.environ.get('SUPPLIER_DIR', "/Users/igorcunha/SHRKVSCODE/Estelita/Raw/Fornecedores"))
MATCHES_ALL = OUT_DIR / 'Supplier_Matches_All.csv'

def norm(s: str) -> str:
    x = str(s or '').strip().lower()
    x = ' '.join(x.split())
    x = ''.join(c for c in unicodedata.normalize('NFKD', x) if not unicodedata.combining(c))
    return x

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
    return c_title, c_artist

def is_currency_like(s: str) -> bool:
    s = str(s or '').strip()
    return bool(re.search(r"^(R\$\s*)?[0-9]+([\.,][0-9]{2,})$", s))

def readiness_for_sheet(df: pd.DataFrame, matches_per_file_titles: set[str]):
    # Identify columns
    c_title, c_artist = find_title_artist_columns(df)
    if c_title is None or c_title not in df.columns:
        return {
            'has_title': False,
            'total_rows': 0,
            'musical_rows': 0,
            'artist_ratio': 0.0,
            'has_amounts': False,
            'amount_rows': 0,
            'has_percent': False,
            'percent_rows': 0,
            'has_dates': False,
            'match_rate': 0.0,
            'noise_ratio': 1.0,
            'readiness_score': 0.0,
        }
    work = df.copy()
    titles = work[c_title].astype(str)
    title_norm = titles.map(norm)
    total_rows = int((titles.astype(str).str.strip()!='').sum())
    musical_mask = title_norm != ''
    musical_rows = int(musical_mask.sum())
    # Artist
    artist_ratio = 0.0
    if c_artist and c_artist in work.columns:
        artist_ratio = float((work[c_artist].astype(str).str.strip()!='').mean())
    # Amounts
    has_amounts, amount_rows = False, 0
    amount_cols = [c for c in work.columns if any(k in norm(c) for k in ['valor','pagar','montante','amount','vr '])]
    if amount_cols:
        for c in amount_cols:
            series = work[c].astype(str)
            amount_rows += int(series.apply(is_currency_like).sum())
        has_amounts = amount_rows > 0
    # Percent
    has_percent, percent_rows = False, 0
    percent_cols = [c for c in work.columns if any(k in norm(c) for k in ['percent','percentual','%'])]
    if percent_cols:
        for c in percent_cols:
            series = work[c].astype(str)
            percent_rows += int(series.str.contains('%', regex=False).sum())
        has_percent = percent_rows > 0
    # Dates
    has_dates = any(any(k in norm(c) for k in ['data','exib','date']) for c in work.columns)
    # Match rate by titles (distinct) using precomputed per-file match titles
    unique_titles = set(title_norm[title_norm!=''].unique())
    intersect = unique_titles & matches_per_file_titles
    match_rate = (len(intersect)/len(unique_titles))*100.0 if unique_titles else 0.0
    # Noise ratio (channels/publishers/month markers)
    noise_tokens = {'tv fechada','tv aberta','multishow','bis','off','gnt','diversas','globoplay','canal brasil','nov/','dez/','jan/','fev/','mar/','abr/','mai/','jun/','jul/','ago/','set/','out/'}
    noise_ratio = float(sum(any(tok in t for tok in noise_tokens) for t in title_norm))/float(len(title_norm) or 1)
    # Readiness score (max ~100)
    score = 0.0
    if has_amounts:
        score += 40.0
        if amount_rows >= 10:
            score += 10.0
    if has_percent:
        score += 15.0
    if has_dates:
        score += 10.0
    if artist_ratio >= 0.5:
        score += 10.0
    elif artist_ratio > 0:
        score += 5.0
    # reward match_rate
    if match_rate >= 2.0:
        score += 10.0
    elif match_rate > 0.2:
        score += 5.0
    # penalize noise
    if noise_ratio >= 0.5:
        score -= 15.0
    elif noise_ratio >= 0.2:
        score -= 5.0
    return {
        'has_title': True,
        'total_rows': total_rows,
        'musical_rows': musical_rows,
        'artist_ratio': round(artist_ratio*100, 2),
        'has_amounts': has_amounts,
        'amount_rows': amount_rows,
        'has_percent': has_percent,
        'percent_rows': percent_rows,
        'has_dates': has_dates,
        'match_rate': round(match_rate, 2),
        'noise_ratio': round(noise_ratio*100, 2),
        'readiness_score': round(score, 2),
    }

def main():
    # Load matches per file → set of matched title_norm for that file
    matches_per_file: dict[str, set[str]] = {}
    if MATCHES_ALL.exists():
        m = pd.read_csv(MATCHES_ALL)
        if not m.empty and 'file' in m.columns and 'title_norm' in m.columns:
            m['title_norm'] = m['title_norm'].astype(str).map(norm)
            for fn, grp in m.groupby('file'):
                matches_per_file[fn] = set(grp['title_norm'].dropna().unique())

    rows = []
    files = [p for p in SUPPLIER_DIR.rglob('*') if p.is_file() and p.suffix.lower() in {'.xlsx','.xls'}]
    for path in files:
        try:
            xl = pd.ExcelFile(path)
        except Exception:
            continue
        for sheet in xl.sheet_names:
            try:
                df = xl.parse(sheet)
            except Exception:
                continue
            if df.empty:
                continue
            metrics = readiness_for_sheet(df, matches_per_file.get(path.name, set()))
            # Provider as first directory level under supplier dir
            try:
                rel = path.relative_to(SUPPLIER_DIR)
                provider = rel.parts[0] if len(rel.parts) > 1 else rel.stem
            except Exception:
                provider = path.parent.name
            rows.append({
                'provider': provider,
                'file': path.name,
                'sheet': sheet,
                **metrics,
            })

    report = pd.DataFrame(rows)
    out_all = OUT_DIR / 'Suppliers_Readiness_Report.csv'
    out_top = OUT_DIR / 'Suppliers_Readiness_Top.csv'
    if not report.empty:
        report.sort_values(['readiness_score','provider','file','sheet'], ascending=[False, True, True, True]).to_csv(out_all, index=False)
        # Rank by readiness, keep best sheet per file
        best_per_file = (report.sort_values('readiness_score', ascending=False)
                         .groupby(['provider','file'], as_index=False).first()
                         .sort_values('readiness_score', ascending=False))
        best_per_file.to_csv(out_top, index=False)
        print(f"Saved readiness report: {out_all}")
        print(f"Saved readiness ranking: {out_top}")
    else:
        print("No readable supplier sheets found.")

if __name__ == '__main__':
    main()

