#!/usr/bin/env python3
"""
Per-provider, per-file explicit/alias counts and integer totals.

Reads the four rollups and groups by provider,file_stem.

Output:
- Estelita/Processed/Summaries/Files_Explicit_Alias_Summary.csv
  Columns: provider, file_stem,
           explicit_rows_total, explicit_with_rows, explicit_value_brl_int,
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


def group_counts_with_values(path: Path, key_fields=('provider','file_stem')) -> dict[tuple,str]:
    out = defaultdict(lambda: {'with_rows': 0, 'cents': 0})
    if not path.exists():
        return out
    with open(path, 'r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            key = tuple((row.get(k) or '').strip() for k in key_fields)
            c = int(row.get('amount_cents') or '0')
            if c > 0:
                out[key]['with_rows'] += 1
                out[key]['cents'] += c
    return out


def group_counts_without_values(path: Path, key_fields=('provider','file_stem')) -> dict[tuple,int]:
    out = defaultdict(int)
    if not path.exists():
        return out
    with open(path, 'r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            key = tuple((row.get(k) or '').strip() for k in key_fields)
            out[key] += 1
    return out


def main():
    exp_with = group_counts_with_values(PROC / 'Eligible_Value_Explicit_All_Providers.csv')
    exp_no   = group_counts_without_values(PROC / 'Explicit_Without_Value_All_Providers.csv')
    ali_with = group_counts_with_values(PROC / 'Eligible_Value_Alias_All_Providers.csv')
    ali_no   = group_counts_without_values(PROC / 'Alias_Without_Value_All_Providers.csv')

    keys = sorted(set(exp_with.keys()) | set(exp_no.keys()) | set(ali_with.keys()) | set(ali_no.keys()))
    out_path = SUM / 'Files_Explicit_Alias_Summary.csv'
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['provider','file_stem','explicit_rows_total','explicit_with_rows','explicit_value_brl_int','alias_rows_total','alias_with_rows','alias_value_brl_int'])
        for key in keys:
            e_with = exp_with.get(key, {'with_rows': 0, 'cents': 0})
            a_with = ali_with.get(key, {'with_rows': 0, 'cents': 0})
            e_no = exp_no.get(key, 0)
            a_no = ali_no.get(key, 0)
            e_total = e_with['with_rows'] + e_no
            a_total = a_with['with_rows'] + a_no
            prov, stem = key
            w.writerow([prov, stem, e_total, e_with['with_rows'], int(round(e_with['cents']/100.0)), a_total, a_with['with_rows'], int(round(a_with['cents']/100.0))])
    print(f"Wrote: {out_path}")


if __name__ == '__main__':
    main()

