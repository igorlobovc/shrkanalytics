#!/usr/bin/env python3
"""
Print explicit-match metrics using normalized integer cents to avoid locale issues.

Reads:
- Estelita/Processed/Eligible_Explicit_All_Providers.csv (exact match rows)
- Estelita/Processed/Eligible_Value_Explicit_All_Providers.csv (value-only rows with amount_cents)
"""

from pathlib import Path
import csv

BASE = Path(__file__).resolve().parent
PROC = BASE / 'Processed'


def main():
    exp_all = PROC / 'Eligible_Explicit_All_Providers.csv'
    exp_val = PROC / 'Eligible_Value_Explicit_All_Providers.csv'

    exact_total = 0
    by_provider_exact: dict[str,int] = {}
    if exp_all.exists():
        with open(exp_all, 'r', encoding='utf-8', newline='') as f:
            r = csv.DictReader(f)
            for row in r:
                exact_total += 1
                prov = row.get('provider','')
                by_provider_exact[prov] = by_provider_exact.get(prov, 0) + 1

    with_value = 0
    cents_total = 0
    by_provider_value: dict[str, dict[str,int]] = {}
    if exp_val.exists():
        with open(exp_val, 'r', encoding='utf-8', newline='') as f:
            r = csv.DictReader(f)
            for row in r:
                prov = row.get('provider','')
                cents = int(row.get('amount_cents') or '0')
                if cents > 0:
                    with_value += 1
                    cents_total += cents
                    st = by_provider_value.setdefault(prov, {'rows':0,'cents':0})
                    st['rows'] += 1
                    st['cents'] += cents

    without_value = exact_total - with_value
    print(f"OVERALL exact_matches={exact_total} with_value={with_value} without_value={without_value} total_brl={cents_total/100:.2f}")
    # Per provider
    for prov, st in sorted(by_provider_value.items(), key=lambda kv: kv[1]['cents'], reverse=True):
        print(f"PROVIDER {prov} exact={by_provider_exact.get(prov,0)} with_value={st['rows']} without_value={by_provider_exact.get(prov,0)-st['rows']} total_brl={st['cents']/100:.2f}")


if __name__ == '__main__':
    main()

