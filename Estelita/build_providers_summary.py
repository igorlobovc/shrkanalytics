#!/usr/bin/env python3
"""
Build provider-level summary for Explicit and Low Probability (Alias) matches.

Inputs (under Estelita/Processed):
- Eligible_Value_Explicit_All_Providers.csv (sheet-based explicit with value)
- Explicit_Without_Value_All_Providers.csv (sheet-based explicit without value)
- Eligible_Value_Alias_All_Providers.csv (sheet-based alias with value)
- Alias_Without_Value_All_Providers.csv (sheet-based alias without value)

Output:
- Estelita/Processed/Summaries/Providers_Explicit_Alias_Summary.csv
  Columns:
    provider, explicit_rows_total, explicit_with_rows, explicit_value_brl_int,
    alias_rows_total, alias_with_rows, alias_value_brl_int
"""

from __future__ import annotations

from pathlib import Path
import csv
from collections import defaultdict

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'
SUM = PROC / 'Summaries'
SUM.mkdir(parents=True, exist_ok=True)


def load_counts_with_values(path: Path) -> dict[str, dict[str, int]]:
    out = defaultdict(lambda: {'with_rows': 0, 'cents': 0})
    if not path.exists():
        return out
    with open(path, 'r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            prov = (row.get('provider') or '').strip()
            c = int(row.get('amount_cents') or '0')
            if c > 0:
                out[prov]['with_rows'] += 1
                out[prov]['cents'] += c
    return out


def load_counts_without_values(path: Path) -> dict[str, int]:
    out = defaultdict(int)
    if not path.exists():
        return out
    with open(path, 'r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            prov = (row.get('provider') or '').strip()
            out[prov] += 1
    return out


def main():
    exp_with = load_counts_with_values(PROC / 'Eligible_Value_Explicit_All_Providers.csv')
    exp_no = load_counts_without_values(PROC / 'Explicit_Without_Value_All_Providers.csv')
    ali_with = load_counts_with_values(PROC / 'Eligible_Value_Alias_All_Providers.csv')
    ali_no = load_counts_without_values(PROC / 'Alias_Without_Value_All_Providers.csv')

    providers = sorted(set(exp_with.keys()) | set(exp_no.keys()) | set(ali_with.keys()) | set(ali_no.keys()))
    out_path = SUM / 'Providers_Explicit_Alias_Summary.csv'
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'provider',
            'explicit_rows_total','explicit_with_rows','explicit_value_brl_int',
            'alias_rows_total','alias_with_rows','alias_value_brl_int'
        ])
        for prov in providers:
            e_with = exp_with.get(prov, {'with_rows': 0, 'cents': 0})
            a_with = ali_with.get(prov, {'with_rows': 0, 'cents': 0})
            e_no = exp_no.get(prov, 0)
            a_no = ali_no.get(prov, 0)
            e_total = e_with['with_rows'] + e_no
            a_total = a_with['with_rows'] + a_no
            w.writerow([
                prov,
                e_total, e_with['with_rows'], int(round(e_with['cents']/100.0)),
                a_total, a_with['with_rows'], int(round(a_with['cents']/100.0))
            ])
    print(f"Wrote: {out_path}")


if __name__ == '__main__':
    main()

