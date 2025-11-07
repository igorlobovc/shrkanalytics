#!/usr/bin/env python3
"""
Summarize unified raw workbooks under Estelita/Raw/Unified:
- For each unified file, report explicit match counts from the processed
  eligible workbook (Explicit_Refs_Only sheet), and also count rows with
  amounts present (integer) on the unified workbook's last column.

Outputs:
- Estelita/Processed/Summaries/Unified_Explicit_Summary.csv
  Columns: file_stem, explicit_rows, explicit_with_value_rows,
           unified_lastcol_amount_rows
"""

from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

BASE = Path(__file__).resolve().parent
RAWU = BASE / 'Raw' / 'Unified'
PROC = BASE / 'Processed'
SUMDIR = PROC / 'Summaries'
SUMDIR.mkdir(parents=True, exist_ok=True)


def to_int_amount(value) -> int:
    s = str(value or '').strip()
    if not s:
        return 0
    s = s.replace('R$', '').replace('$', '').replace(' ', '')
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
        return int(round(float(s)))
    except Exception:
        return 0


def explicit_counts_for_stem(stem: str) -> tuple[int, int]:
    """Return (explicit_rows, explicit_with_value_rows) from eligible workbook.
    Counts rows on sheet 'Explicit_Refs_Only'. For value rows, attempts to
    read 'VALOR A PAGAR - EDITORA' or 'Valor (BRL)'; if absent, uses last column.
    """
    xlsx = PROC / f"{stem}__eligible_with_refs.xlsx"
    if not xlsx.exists():
        return 0, 0
    try:
        xl = pd.ExcelFile(xlsx)
    except Exception:
        return 0, 0
    sheet = next((s for s in xl.sheet_names if str(s).strip().lower() == 'explicit_refs_only'), None)
    if sheet is None:
        return 0, 0
    try:
        df = xl.parse(sheet)
    except Exception:
        return 0, 0
    if df is None or df.empty:
        return 0, 0
    explicit_rows = int(len(df))
    # Determine amount column
    col_amt = None
    for c in df.columns:
        n = str(c).strip().lower()
        if n == 'valor (brl)' or n == 'valor a pagar - editora':
            col_amt = c
            break
    if col_amt is None:
        col_amt = df.columns[-1]
    vals = df[col_amt].map(to_int_amount)
    explicit_with_value_rows = int((vals > 0).sum())
    return explicit_rows, explicit_with_value_rows


def is_currency_like(s: str) -> bool:
    s = str(s or '').strip()
    if not s:
        return False
    s = s.replace(' ', '')
    return bool(re.search(r"^(R\$|\$)?\d{1,3}([.,]\d{3})*([.,]\d{2})$|^(R\$|\$)?\d+$", s))


def detect_amount_column(df: pd.DataFrame) -> str | None:
    # Prefer named columns first
    for name in df.columns:
        n = str(name).strip().lower()
        if n in { 'valor (brl)', 'valor a pagar - editora', 'valor', 'amount', 'montante'}:
            return name
    # Otherwise, pick the column with most currency-like cells
    best_col = None
    best_hits = 0
    for name in df.columns:
        series = df[name]
        try:
            hits = int(series.apply(is_currency_like).sum())
        except Exception:
            hits = 0
        if hits > best_hits:
            best_hits = hits
            best_col = name
    # Require at least some hits to consider it an amount column
    return best_col if best_hits >= 3 else None


def unified_amount_counts(stem: str) -> int:
    """Return count of rows with positive integer amounts in the detected
    amount column of the unified raw workbook for this stem."""
    raw = RAWU / f"{stem}.xlsx"
    if not raw.exists():
        return 0
    try:
        xl = pd.ExcelFile(raw)
    except Exception:
        return 0
    total = 0
    for s in xl.sheet_names:
        try:
            df = xl.parse(s)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        amt_col = detect_amount_column(df) or df.columns[-1]
        vals = df[amt_col].map(to_int_amount)
        total += int((vals > 0).sum())
    return total


def main():
    rows = []
    for p in sorted(RAWU.glob('*.xlsx')):
        stem = p.stem
        exp_rows, exp_val_rows = explicit_counts_for_stem(stem)
        un_last = unified_amount_counts(stem)
        rows.append({
            'file_stem': stem,
            'explicit_rows': exp_rows,
            'explicit_with_value_rows': exp_val_rows,
            'unified_lastcol_amount_rows': un_last,
        })
    out = SUMDIR / 'Unified_Explicit_Summary.csv'
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote: {out}")


if __name__ == '__main__':
    main()
