#!/usr/bin/env python3
"""
Build a consolidated, normalized searchable base from Estelita side:
- Titles, authors from OBRAS and FONOGRAMAS
- ISWC and ISRC identifiers
- Publisher aliases (Estelita and owner variations)
- Eligible artists (from Eligible_Artists.txt if present)

Outputs:
- Estelita/Processed/Searchable_Base.csv
  columns: key_norm, key_type, raw_value, source
- Estelita/Processed/_logs/Searchable_Stats.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

BASE = Path(__file__).resolve().parent
RAW = BASE / 'Raw'
PROC = BASE / 'Processed'
LOG = PROC / '_logs'
PROC.mkdir(parents=True, exist_ok=True)
LOG.mkdir(parents=True, exist_ok=True)


def norm(s: str) -> str:
    s = str(s or '').strip().lower()
    # basic unicode folding without external deps
    try:
        import unicodedata
        s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    except Exception:
        pass
    s = ' '.join(s.split())
    return s


def load_xlsx(path: Path, sheets: Iterable[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        if sheets is None:
            return pd.read_excel(path)
        out = []
        xl = pd.ExcelFile(path)
        for s in xl.sheet_names:
            if sheets and s not in sheets:
                continue
            try:
                out.append(xl.parse(s))
            except Exception:
                continue
        return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def collect_from_df(df: pd.DataFrame, cols: list[str]) -> set[str]:
    vals: set[str] = set()
    for c in cols:
        if c in df.columns:
            ser = df[c].dropna().astype(str).map(norm)
            vals |= set(x for x in ser.unique() if x)
    return vals


def main():
    rows = []
    stats = {}

    # OBRAS and FONOGRAMAS
    obras = load_xlsx(RAW / 'ESTELITA OBRAS_v2.xlsx')
    fonos = load_xlsx(RAW / 'ESTELITA Fonogramas_v2.xlsx')

    # Titles, Authors
    titles = set()
    authors = set()
    if not obras.empty:
        titles |= collect_from_df(obras, ['Unnamed: 4', 'TÍTULO', 'titulo', 'Título', 'OBRA MUSICAL'])
        authors |= collect_from_df(obras, ['Unnamed: 6', 'AUTOR', 'Autor', 'autor'])
    if not fonos.empty:
        titles |= collect_from_df(fonos, ['TÍTULO', 'titulo', 'Título'])
        authors |= collect_from_df(fonos, ['AUTOR', 'Autor', 'autor', 'Intérprete', 'INTERPRETE'])

    # Identifiers
    iswcs = set()
    isrcs = set()
    id_df = pd.concat([obras, fonos], ignore_index=True) if not obras.empty or not fonos.empty else pd.DataFrame()
    if not id_df.empty:
        for c in id_df.columns:
            ser = id_df[c].astype(str)
            for v in ser.dropna().unique():
                s = str(v).strip()
                if not s:
                    continue
                if re.fullmatch(r'T-[0-9.]+-[0-9X]', s):
                    iswcs.add(s)
                if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{3}\d{7}', s, flags=re.I):
                    isrcs.add(s.upper())

    # Eligible catalog
    elig = PROC / 'Eligible_Catalog.csv'
    if elig.exists():
        try:
            ec = pd.read_csv(elig)
            titles |= set(ec.get('title', pd.Series(dtype=str)).dropna().map(norm).unique())
            iswcs |= set(str(x).strip() for x in ec.get('iswc', pd.Series(dtype=str)).dropna().unique())
        except Exception:
            pass

    # Eligible artists
    elig_artists = set()
    artists_file = PROC / 'Eligible_Artists.txt'
    if artists_file.exists():
        try:
            elig_artists = set(norm(x) for x in artists_file.read_text(encoding='utf-8').splitlines() if x.strip())
        except Exception:
            pass

    # Publisher / Estelita aliases
    publisher_aliases = {
        'estelita',
        'eduardo melo pereira',
        'eduardo melo pereira ltda',
        'eduardo melo',
        'estelita editora',
    }

    # Build rows
    def add_keys(keys: set[str], key_type: str, source: str):
        for k in sorted(keys):
            rows.append({'key_norm': k, 'key_type': key_type, 'raw_value': k, 'source': source})

    add_keys(titles, 'title', 'OBRAS/FONOGRAMAS/Eligible')
    add_keys(authors, 'author', 'OBRAS/FONOGRAMAS')
    add_keys(set(x.upper() for x in iswcs), 'iswc', 'OBRAS/FONOGRAMAS/Eligible')
    add_keys(set(x.upper() for x in isrcs), 'isrc', 'OBRAS/FONOGRAMAS')
    add_keys(elig_artists, 'eligible_artist', 'Eligible_Artists')
    add_keys(publisher_aliases, 'publisher_alias', 'manual')

    # Write outputs
    out = PROC / 'Searchable_Base.csv'
    pd.DataFrame(rows).drop_duplicates().to_csv(out, index=False)
    stats = {
        'titles': len(titles),
        'authors': len(authors),
        'iswcs': len(iswcs),
        'isrcs': len(isrcs),
        'eligible_artists': len(elig_artists),
        'publisher_aliases': len(publisher_aliases),
        'total_rows': len(rows),
    }
    (LOG / 'Searchable_Stats.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
    print(f"Wrote: {out}\nStats: {stats}")


if __name__ == '__main__':
    main()

