#!/usr/bin/env python3
"""
Build consolidated fornecedores summaries from processed workbooks.

Outputs (under Estelita/Processed/ and Summaries/ copies):
- Fornecedores_Summary.csv (per file)
- Fornecedores_ByProvider_Summary.csv (rollup)
- Fornecedores_Amounts_Presence.csv (diagnostic: which files/sheets have amounts)

Logic:
- Detect provider per file using Supplier_Matches_All.csv mapping (robust, avoids heuristics).
- Count matches rows from *__matches_only_with_refs.(csv|xlsx)
- Count eligible explicit/alias rows from *__eligible_with_refs.xlsx sheets.
- Sum explicit amounts by parsing numeric 'Valor (BRL)' column if present,
  else parse fallback text column containing 'VALOR' and 'EDITORA'.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import re

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'
SUM_DIR = PROC / 'Summaries'
SUM_DIR.mkdir(parents=True, exist_ok=True)

MATCHES_ALL = PROC / 'Supplier_Matches_All.csv'


def parse_currency_robust(value: str) -> float:
    s = str(value or '').strip()
    if not s:
        return 0.0
    s = s.replace('R$', '').replace(' ', '')
    has_dot = '.' in s
    has_comma = ',' in s
    if has_dot and has_comma:
        last_sep = s[max(s.rfind('.'), s.rfind(','))]
        if last_sep == ',':
            s = s.replace('.', '')
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    elif has_comma and not has_dot:
        if re.search(r",\d{2}$", s):
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    elif has_dot and not has_comma:
        if not re.search(r"\.\d{2}$", s):
            s = s.replace('.', '')
    try:
        return float(s)
    except Exception:
        return 0.0


def stem(p: Path) -> str:
    name = p.name
    if name.endswith('__eligible_with_refs.xlsx'):
        return name[:-len('__eligible_with_refs.xlsx')]
    if name.endswith('__matches_only_with_refs.csv'):
        return name[:-len('__matches_only_with_refs.csv')]
    if name.endswith('__matches_only_with_refs.xlsx'):
        return name[:-len('__matches_only_with_refs.xlsx')]
    return p.stem


def load_provider_map() -> dict[str, str]:
    prov: dict[str, str] = {}
    if MATCHES_ALL.exists():
        try:
            m = pd.read_csv(MATCHES_ALL, dtype=str)
            if not m.empty and {'file', 'provider'} <= set(m.columns):
                for fn, grp in m.groupby('file'):
                    try:
                        st = Path(fn).stem
                    except Exception:
                        st = str(fn)
                    # choose most common provider label for a file just in case
                    prov_label = grp['provider'].mode().iloc[0] if not grp['provider'].empty else ''
                    prov[st] = prov_label
        except Exception:
            pass
    return prov


def count_rows_csv_or_xlsx(base_stem: str) -> int:
    # Prefer CSV for performance
    csv_path = PROC / f"{base_stem}__matches_only_with_refs.csv"
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            return int(len(df))
        except Exception:
            return 0
    xlsx_path = PROC / f"{base_stem}__matches_only_with_refs.xlsx"
    if xlsx_path.exists():
        try:
            xl = pd.ExcelFile(xlsx_path)
            # choose first sheet
            sheet = xl.sheet_names[0] if xl.sheet_names else None
            if sheet:
                df = xl.parse(sheet)
                return int(len(df))
        except Exception:
            return 0
    return 0


def eligible_stats_from_xlsx(base_stem: str) -> tuple[int, int, float, int, int, float]:
    """
    Returns: (explicit_rows, alias_rows, sum_brl_explicit, exp_amount_rows, alias_amount_rows, sum_brl_alias)
    """
    xlsx = PROC / f"{base_stem}__eligible_with_refs.xlsx"
    if not xlsx.exists():
        return 0, 0, 0.0, 0, 0, 0.0
    try:
        xl = pd.ExcelFile(xlsx)
    except Exception:
        return 0, 0, 0.0, 0, 0, 0.0
    exp_rows = 0
    alias_rows = 0
    sum_exp = 0.0
    sum_alias = 0.0
    exp_amt_rows = 0
    alias_amt_rows = 0
    # Explicit
    if 'Explicit_Refs_Only' in xl.sheet_names:
        try:
            exp = xl.parse('Explicit_Refs_Only')
            exp_rows = int(len(exp))
            amt_col = next((c for c in exp.columns if 'Valor (BRL)' == c), None)
            if not amt_col:
                amt_col = next((c for c in exp.columns if 'VALOR' in str(c).upper() and 'EDITORA' in str(c).upper()), None)
            if amt_col:
                vals = exp[amt_col].apply(parse_currency_robust)
                sum_exp = float(vals.sum())
                exp_amt_rows = int((vals > 0).sum())
        except Exception:
            pass
    # Alias
    alias_sheet = 'Low Probability Matches SBT' if 'Low Probability Matches SBT' in xl.sheet_names else ('Artist_Alias_Eligible' if 'Artist_Alias_Eligible' in xl.sheet_names else None)
    if alias_sheet:
        try:
            al = xl.parse(alias_sheet)
            alias_rows = int(len(al))
            amt_col = next((c for c in al.columns if 'Valor (BRL)' == c), None)
            if not amt_col:
                amt_col = next((c for c in al.columns if 'VALOR' in str(c).upper() and 'EDITORA' in str(c).upper()), None)
            if amt_col:
                vals = al[amt_col].apply(parse_currency_robust)
                sum_alias = float(vals.sum())
                alias_amt_rows = int((vals > 0).sum())
        except Exception:
            pass
    return exp_rows, alias_rows, sum_exp, exp_amt_rows, alias_amt_rows, sum_alias


def eligible_stats_from_consolidated_csvs(base_stem: str) -> tuple[int, int, float, int, int, float]:
    """
    Fast path using consolidated CSVs if present:
    - Eligible_Explicit_All_Providers.csv: count + parse 'VALOR A PAGAR - EDITORA'
    - Eligible_Value_Alias_All_Providers.csv: count + sum 'Valor (BRL)'
    """
    exp_rows = 0
    alias_rows = 0
    sum_exp = 0.0
    sum_alias = 0.0
    exp_amt_rows = 0
    alias_amt_rows = 0

    import csv
    # Prefer normalized explicit value-only CSV when present
    exp_val = PROC / 'Eligible_Value_Explicit_All_Providers.csv'
    if exp_val.exists():
        try:
            with open(exp_val, 'r', encoding='utf-8', newline='') as f:
                r = csv.DictReader(f)
                for row in r:
                    if row.get('file_stem') != base_stem:
                        continue
                    exp_rows += 1
                    cents = int(row.get('amount_cents') or '0')
                    if cents > 0:
                        exp_amt_rows += 1
                        sum_exp += cents/100.0
        except Exception:
            pass
    else:
        # Fallback: read unnormalized explicit consolidated and parse
        exp_csv = PROC / 'Eligible_Explicit_All_Providers.csv'
        if exp_csv.exists():
            try:
                with open(exp_csv, 'r', encoding='utf-8', newline='') as f:
                    r = csv.DictReader(f)
                    for row in r:
                        if row.get('file_stem') != base_stem:
                            continue
                        exp_rows += 1
                        amt = parse_currency_robust(row.get('VALOR A PAGAR - EDITORA', ''))
                        if amt > 0:
                            exp_amt_rows += 1
                            sum_exp += amt
            except Exception:
                pass
    alias_csv = PROC / 'Eligible_Value_Alias_All_Providers.csv'
    if alias_csv.exists():
        try:
            with open(alias_csv, 'r', encoding='utf-8', newline='') as f:
                r = csv.DictReader(f)
                for row in r:
                    if row.get('file_stem') != base_stem:
                        continue
                    alias_rows += 1
                    cents = int(row.get('amount_cents') or '0')
                    if cents > 0:
                        alias_amt_rows += 1
                        sum_alias += cents/100.0
        except Exception:
            pass
    return exp_rows, alias_rows, sum_exp, exp_amt_rows, alias_amt_rows, sum_alias


def main():
    prov_map = load_provider_map()
    # Identify all stems with matches or eligible outputs
    stems = set()
    for p in PROC.glob('*__matches_only_with_refs.*'):
        stems.add(stem(p))
    for p in PROC.glob('*__eligible_with_refs.xlsx'):
        stems.add(stem(p))
    if not stems:
        print('No processed supplier outputs found to summarize.')
        return

    rows = []
    present = []
    for st in sorted(stems):
        provider = prov_map.get(st, '')
        matches_rows = count_rows_csv_or_xlsx(st)
        # Prefer consolidated CSVs for speed; fallback to xlsx parsing
        exp_rows, alias_rows, sum_exp, exp_amt_rows, alias_amt_rows, sum_alias = eligible_stats_from_consolidated_csvs(st)
        if (exp_rows + alias_rows) == 0:
            exp_rows, alias_rows, sum_exp, exp_amt_rows, alias_amt_rows, sum_alias = eligible_stats_from_xlsx(st)
        rows.append({
            'provider': provider or '',
            'file_stem': st,
            'matches_rows': matches_rows,
            'eligible_explicit_rows': exp_rows,
            'eligible_alias_rows': alias_rows,
            'sum_valor_brl_explicit': f"{sum_exp:.2f}",
        })
        present.append({
            'provider': provider or '',
            'file_stem': st,
            'explicit_rows': exp_rows,
            'alias_rows': alias_rows,
            'explicit_amount_rows': exp_amt_rows,
            'alias_amount_rows': alias_amt_rows,
            'sum_valor_brl_explicit': f"{sum_exp:.2f}",
            'sum_valor_brl_alias': f"{sum_alias:.2f}",
            'has_any_amounts': (exp_amt_rows + alias_amt_rows) > 0,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(['provider', 'file_stem']).reset_index(drop=True)
    out_general = PROC / 'Fornecedores_Summary.csv'
    df.to_csv(out_general, index=False)
    (SUM_DIR / 'Fornecedores_Summary.csv').write_text(out_general.read_text(encoding='utf-8'), encoding='utf-8')

    # By-provider rollup
    byprov = (df.groupby('provider', dropna=False)
                .agg(files=('file_stem', 'nunique'),
                     matches_rows=('matches_rows', 'sum'),
                     eligible_explicit_rows=('eligible_explicit_rows', 'sum'),
                     eligible_alias_rows=('eligible_alias_rows', 'sum'),
                     sum_valor_brl_explicit=('sum_valor_brl_explicit', lambda s: float(pd.to_numeric(s, errors='coerce').sum())))
                .reset_index())
    # format sum as two decimals
    byprov['sum_valor_brl_explicit'] = byprov['sum_valor_brl_explicit'].map(lambda v: f"{float(v):.2f}")
    out_byprov = PROC / 'Fornecedores_ByProvider_Summary.csv'
    byprov.to_csv(out_byprov, index=False)
    (SUM_DIR / 'Fornecedores_ByProvider_Summary.csv').write_text(out_byprov.read_text(encoding='utf-8'), encoding='utf-8')

    # Amounts presence diagnostics
    pres = pd.DataFrame(present).sort_values(['provider','file_stem'])
    pres.to_csv(PROC / 'Fornecedores_Amounts_Presence.csv', index=False)

    print(f"Wrote: {out_general}")
    print(f"Wrote: {out_byprov}")


if __name__ == '__main__':
    main()
