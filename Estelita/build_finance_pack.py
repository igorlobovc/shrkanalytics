#!/usr/bin/env python3
"""
Build a finance-facing Excel pack with two tabs:
- Explicit_Value: rows with positive amounts from explicit matches
- Alias_Value: rows with positive amounts from alias matches

Inputs (under Estelita/Processed):
- Eligible_Value_Explicit_All_Providers.csv
- Eligible_Value_Alias_All_Providers.csv

Output:
- Finance_Pack.xlsx (two sheets)
"""

from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'


def load_explicit() -> pd.DataFrame:
    path = PROC / 'Eligible_Value_Explicit_All_Providers.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    # Normalize duplicated provider/file_stem if present
    cols = list(df.columns)
    if 'provider.1' in cols and 'file_stem.1' in cols:
        df = df.rename(columns={'provider':'provider_src','file_stem':'file_stem_src','provider.1':'provider','file_stem.1':'file_stem'})
    # Ensure numeric amount column exists
    if 'amount_numeric' in df.columns:
        df['amount_numeric'] = pd.to_numeric(df['amount_numeric'], errors='coerce').fillna(0.0)
    else:
        if 'VALOR A PAGAR - EDITORA' in df.columns:
            def parse_brl(s: str) -> float:
                v = str(s or '').strip().replace('R$','').replace(' ','').replace('.','').replace(',', '.')
                try:
                    return float(v)
                except Exception:
                    return 0.0
            df['amount_numeric'] = df['VALOR A PAGAR - EDITORA'].map(parse_brl)
        else:
            df['amount_numeric'] = 0.0
    return df[df['amount_numeric'] > 0].copy()


def load_alias() -> pd.DataFrame:
    path = PROC / 'Eligible_Value_Alias_All_Providers.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    # Try to ensure a numeric value column exists
    if 'amount_numeric' in df.columns:
        df['amount_numeric'] = pd.to_numeric(df['amount_numeric'], errors='coerce').fillna(0.0)
    elif 'Valor (BRL)' in df.columns:
        df['amount_numeric'] = pd.to_numeric(df['Valor (BRL)'], errors='coerce').fillna(0.0)
    else:
        df['amount_numeric'] = 0.0
    return df[df['amount_numeric'] > 0].copy()


def main():
    exp = load_explicit()
    ali = load_alias()
    out = PROC / 'Finance_Pack.xlsx'
    with pd.ExcelWriter(out) as wr:
        exp.to_excel(wr, sheet_name='Explicit_Value', index=False)
        ali.to_excel(wr, sheet_name='Alias_Value', index=False)
    print(f"Wrote finance pack: {out}")


if __name__ == '__main__':
    main()

