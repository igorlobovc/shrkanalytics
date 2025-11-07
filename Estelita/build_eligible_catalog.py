#!/usr/bin/env python3
"""
Build an eligibility catalog from raw OBRAS and FONOGRAMAS files using practical heuristics
described by the user:

- Fonogramas (ESTELITA Fonogramas_v2.xlsx): rows with status 'LIBERADO' indicate eligible fonogramas.
  Use the track title column nearby (same row) and capture ISRC-like codes if present.
  Optionally collect adjacent author names between LIBERADO rows.

- Obras (ESTELITA OBRAS_v2.xlsx): rows where association contains 'UBC' indicate song title rows.
  Use the song title column and capture ISWC if present.
  Also build an eligible artist list from 'NOME DO TITULAR' and 'PSEUDÔNIMO'.

Outputs:
- Processed/Eligible_Catalog.csv (title, artist, iswc, isrc, source, basis)
- Processed/_logs/Eligible_Catalog.summary.json (counts per basis)
"""

from pathlib import Path
import re
import json
import unicodedata
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / 'Raw'
OUT_DIR = BASE_DIR / 'Processed'
LOG_DIR = OUT_DIR / '_logs'
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

OBRAS_XLSX = RAW_DIR / 'ESTELITA OBRAS_v2.xlsx'
FONOS_XLSX = RAW_DIR / 'ESTELITA Fonogramas_v2.xlsx'

def norm(s: str) -> str:
    x = str(s or '').strip().lower()
    x = ' '.join(x.split())
    x = ''.join(c for c in unicodedata.normalize('NFKD', x) if not unicodedata.combining(c))
    return x

def detect_fonos_columns(df: pd.DataFrame):
    # Status column: choose col with the most 'LIBERADO'
    status_col, max_lib = None, -1
    for c in df.columns:
        vals = df[c].astype(str).str.upper().str.strip()
        cnt = int((vals == 'LIBERADO').sum())
        if cnt > max_lib:
            status_col, max_lib = c, cnt
    # Title column: among object cols, pick the one with most non-empty strings on LIBERADO rows
    title_col, best_score = None, -1
    if status_col is not None:
        mask = df[status_col].astype(str).str.upper().str.strip() == 'LIBERADO'
        for c in df.columns:
            s = df.loc[mask, c].astype(str)
            nonempty = (s.str.strip()!='') & (~s.str.lower().isin(['nan','none','null']))
            # Discourage columns with many 'NAO'/'NÃO'/'X'
            bad = s.str.upper().isin(['NAO','NÃO','X'])
            score = nonempty.sum() - bad.sum()
            if score > best_score:
                title_col, best_score = c, score
    # A fallback: choose the first texty column if needed
    if title_col is None and len(df.columns) >= 2:
        title_col = df.columns[1]
    return status_col, title_col

def extract_isrc_like(values) -> str | None:
    # ISRC patterns such as BR-XXX-YY-XXXXX or BC-A7I-24-00014
    pat = re.compile(r'^[A-Z]{2}[- ][A-Z0-9]{2,4}[- ][0-9]{2}[- ][0-9]{3,6}$')
    for v in values:
        s = str(v or '').strip().upper()
        if pat.match(s):
            return s
    return None

def build_from_fonogramas() -> list[dict]:
    rows = []
    if not FONOS_XLSX.exists():
        return rows
    xl = pd.ExcelFile(FONOS_XLSX)
    df = xl.parse(xl.sheet_names[0])
    status_col, title_col = detect_fonos_columns(df)
    if status_col is None or title_col is None:
        return rows
    mask = df[status_col].astype(str).str.upper().str.strip() == 'LIBERADO'
    idxs = list(df[mask].index)
    for i, idx in enumerate(idxs):
        title = str(df.at[idx, title_col] or '').strip()
        if not title or title.lower() in {'nan','none','null'}:
            continue
        # ISRC scan across row
        isrc = extract_isrc_like(list(df.iloc[idx].values))
        # Optional: look ahead up to next LIBERADO for potential author strings (heuristic)
        next_idx = idxs[i+1] if i+1 < len(idxs) else (idx + 10)
        window = df.iloc[idx+1:next_idx]
        # Check explicit ESTELITA mention in the window as eligibility evidence
        mentions_estelita = False
        # Collect any cell that has letter+space and not numeric-only as author hints
        auth = None
        found = []
        for c in window.columns:
            s = window[c].astype(str)
            mask_text = s.str.contains(r'[A-Za-z]', regex=True) & s.str.contains(' ', regex=False)
            if s.str.upper().str.contains('ESTELITA').any():
                mentions_estelita = True
            for v in s[mask_text].head(3).tolist():
                vv = str(v).strip()
                if vv and not re.fullmatch(r'[0-9\-.,/ ]+', vv):
                    found.append(vv)
            if len(found) >= 3:
                break
        if found:
            auth = '; '.join(found[:3])
        # Only include records that mention ESTELITA around the block
        if not mentions_estelita:
            continue
        rows.append({
            'title': title,
            'artist': auth,
            'isrc': isrc,
            'iswc': None,
            'source': 'FONOGRAMAS',
            'basis': 'LIBERADO+MENTION'
        })
    return rows

def detect_obras_columns(df: pd.DataFrame):
    # Association column: with many 'UBC'
    assoc_col, best_cnt = None, -1
    for c in df.columns:
        vals = df[c].astype(str).str.upper()
        cnt = int((vals == 'UBC').sum())
        if cnt > best_cnt:
            assoc_col, best_cnt = c, cnt
    # Title column: prefer texty col near assoc rows; default to Unnamed: 4 if present
    title_col = 'Unnamed: 4' if 'Unnamed: 4' in df.columns else None
    if title_col is None:
        # choose most textual
        best_score = -1
        for c in df.columns:
            s = df[c].astype(str)
            nn = (s.str.strip()!='') & (~s.str.lower().isin(['nan','none','null']))
            num_only = s.str.match(r'^[0-9\-.,/ ]+$', na=False)
            score = nn.sum() - num_only.sum()
            if score > best_score:
                title_col, best_score = c, score
    # ISWC column: any cell starting with T-
    iswc_col = None
    for c in df.columns:
        if df[c].astype(str).str.startswith('T-').any():
            iswc_col = c
            break
    # Artist columns: 'NOME DO TITULAR' or 'PSEUDÔNIMO' if present
    name_col = next((c for c in df.columns if 'NOME' in str(c).upper() and 'TITULAR' in str(c).upper()), None)
    pseud_col = next((c for c in df.columns if 'PSEUD' in str(c).upper()), None)
    return assoc_col, title_col, iswc_col, name_col, pseud_col

def build_from_obras() -> tuple[list[dict], set[str]]:
    rows = []
    artists = set()
    if not OBRAS_XLSX.exists():
        return rows, artists
    xl = pd.ExcelFile(OBRAS_XLSX)
    df = xl.parse(xl.sheet_names[0])
    assoc_col, title_col, iswc_col, name_col, pseud_col = detect_obras_columns(df)
    if assoc_col is None or title_col is None:
        return rows, artists
    # Eligible songs where association is UBC and title present
    mask = df[assoc_col].astype(str).str.upper().str.contains('UBC', na=False)
    for idx in df[mask].index.tolist():
        title = str(df.at[idx, title_col] or '').strip()
        if not title or title.lower() in {'nan','none','null'}:
            continue
        iswc = None
        if iswc_col and pd.notna(df.at[idx, iswc_col]):
            val = str(df.at[idx, iswc_col]).strip()
            if val.startswith('T-'):
                iswc = val
        rows.append({
            'title': title,
            'artist': None,
            'isrc': None,
            'iswc': iswc,
            'source': 'OBRAS',
            'basis': 'UBC'
        })
    # Artist-only eligibility list
    if name_col:
        for v in df[name_col].dropna().astype(str).tolist():
            n = norm(v)
            if n and n not in {'nome do titular','titular'}:
                artists.add(n)
    if pseud_col:
        for v in df[pseud_col].dropna().astype(str).tolist():
            n = norm(v)
            if n and n not in {'pseudonimo','pseudônimo'}:
                artists.add(n)
    # Heuristic: also gather likely artist name columns seen earlier (Unnamed: 2, Unnamed: 6)
    for extra_col in ['Unnamed: 2','Unnamed: 6']:
        if extra_col in df.columns:
            for v in df[extra_col].dropna().astype(str).tolist():
                n = norm(v)
                # exclude obvious codes like T-... and numeric-only
                if not n or n.startswith('t-') or re.fullmatch(r'[0-9\-.,/ ]+', n):
                    continue
                artists.add(n)
    return rows, artists

def main():
    cat = []
    f_rows = build_from_fonogramas()
    o_rows, artists = build_from_obras()
    cat.extend(f_rows)
    cat.extend(o_rows)
    df = pd.DataFrame(cat)
    # Normalize and deduplicate by title+iswc+isrc
    if not df.empty:
        df['title_norm'] = df['title'].astype(str).map(norm)
        df = df[df['title_norm']!='']
        df = df.drop_duplicates(subset=['title_norm','iswc','isrc','source','basis'])
    out_csv = OUT_DIR / 'Eligible_Catalog.csv'
    df[['title','artist','iswc','isrc','source','basis']].to_csv(out_csv, index=False)
    summary = {
        'total': len(df),
        'by_basis': df['basis'].value_counts().to_dict() if not df.empty else {},
        'artist_aliases_count': len(artists)
    }
    with open(LOG_DIR / 'Eligible_Catalog.summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    # Save artists list
    (OUT_DIR / 'Eligible_Artists.txt').write_text('\n'.join(sorted(list(artists))), encoding='utf-8')
    print(f'Saved Eligible_Catalog: {out_csv} | artists: {len(artists)}')

if __name__ == '__main__':
    main()
