#!/usr/bin/env python3
"""
Produce a definitive, fully-vetted explicit matches CSV across all fornecedores.

Logic: concatenate all rows from Explicit_Refs_Only sheets of every
Processed/*__eligible_with_refs.xlsx workbook, keeping key columns.

Output:
- Estelita/Processed/Summaries/Explicit_Matches_All.csv
  Columns (best-effort superset):
    provider, file_stem, source_sheet, programa, data_exibicao, numero_programa,
    titulo_musica, autor, interprete, matched_title, matched_identifier_iswc,
    eligibility_basis, amount_cents, amount_int, valor_editora_brl
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'
OUT = PROC / 'Summaries'
OUT.mkdir(parents=True, exist_ok=True)


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


def to_cents(v) -> int:
    s = str(v or '').strip()
    if not s:
        return 0
    s = s.replace('R$','').replace('$','').replace(' ','')
    has_dot='.' in s
    has_comma=',' in s
    import re
    if has_dot and has_comma:
        last=s[max(s.rfind('.'), s.rfind(','))]
        if last==',':
            s=s.replace('.',''); s=s.replace(',', '.')
        else:
            s=s.replace(',', '')
    elif has_comma and not has_dot:
        if re.search(r",\d{2}$", s): s=s.replace(',', '.')
        else: s=s.replace(',', '')
    elif has_dot and not has_comma:
        if not re.search(r"\.\d{2}$", s): s=s.replace('.', '')
    try:
        return int(round(float(s)*100))
    except Exception:
        return 0


def main():
    rows = []
    for xlsx in sorted(PROC.glob('*__eligible_with_refs.xlsx')):
        stem = xlsx.stem.replace('__eligible_with_refs', '')
        provider = stem.split()[0] if stem else ''
        try:
            xl = pd.ExcelFile(xlsx)
        except Exception:
            continue
        if 'Explicit_Refs_Only' not in xl.sheet_names:
            continue
        try:
            df = xl.parse('Explicit_Refs_Only')
        except Exception:
            continue
        if df is None or df.empty:
            continue
        # Map columns
        c_prog = find_col(df, ['PROGRAMA'])
        c_date = find_col(df, ['DATA DE EXIBIÇÃO','DATA EXIBIÇÃO','Exibição'])
        c_num  = find_col(df, ['NÚMERO PROGRAMA','NÚMERO EPISÓDIO/CAPÍTULO'])
        c_title= find_col(df, ['NOME DA MÚSICA','TÍTULO DA OBRA MUSICAL','Música','TÍTULO'])
        c_author=find_col(df, ['AUTOR'])
        c_inter = find_col(df, ['INTERPRETE','Intérprete'])
        c_mtitle= find_col(df, ['Matched Title'])
        c_miswc = find_col(df, ['Matched Identifier/ISWC'])
        c_basis = find_col(df, ['Eligibility Basis'])
        c_amt   = find_col(df, ['VALOR A PAGAR - EDITORA','Valor (BRL)','Total'])
        c_src   = '__source_sheet' if '__source_sheet' in df.columns else None
        # assemble
        for _, r in df.iterrows():
            cents = to_cents(r.get(c_amt)) if c_amt else 0
            rows.append({
                'provider': provider,
                'file_stem': stem,
                'source_sheet': str(r.get(c_src)).strip() if c_src else 'Explicit_Refs_Only',
                'programa': str(r.get(c_prog)) if c_prog else None,
                'data_exibicao': str(r.get(c_date)) if c_date else None,
                'numero_programa': str(r.get(c_num)) if c_num else None,
                'titulo_musica': str(r.get(c_title)) if c_title else None,
                'autor': str(r.get(c_author)) if c_author else None,
                'interprete': str(r.get(c_inter)) if c_inter else None,
                'matched_title': str(r.get(c_mtitle)) if c_mtitle else None,
                'matched_identifier_iswc': str(r.get(c_miswc)) if c_miswc else None,
                'eligibility_basis': str(r.get(c_basis)) if c_basis else None,
                'amount_cents': cents,
                'amount_int': int(round(cents/100.0)) if cents else 0,
                'valor_editora_brl': str(r.get(c_amt)) if c_amt else None,
            })
    out = OUT / 'Explicit_Matches_All.csv'
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote: {out} ({len(rows)} rows)")


if __name__ == '__main__':
    main()

