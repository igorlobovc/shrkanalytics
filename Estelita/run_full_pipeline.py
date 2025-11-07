#!/usr/bin/env python3
"""
Run end-to-end pipeline across Fornecedores and Unified sources:
1) Build searchable base (if desired)
2) Run batch matches for Fornecedores and Unified; merge into Supplier_Matches_All.csv
3) Export eligible workbooks for every supplier file found
4) Rebuild sheet-based rollups (with/without value)
5) Rebuild fornecedores and unified summaries
"""

from __future__ import annotations

import os
import subprocess as sp
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
RAW_F = BASE / 'Raw' / 'Fornecedores'
RAW_U = BASE / 'Raw' / 'Unified'
PROC = BASE / 'Processed'


def run(cmd: list[str], env: dict | None = None):
    print('RUN', ' '.join(cmd))
    sp.run(cmd, check=True, env=env)


def batch_matches_for(dirpath: Path, out_copy: Path):
    env = os.environ.copy()
    env['SUPPLIER_DIR'] = str(dirpath)
    run(['python3', str(BASE / 'batch_match_suppliers.py')], env)
    src = PROC / 'Supplier_Matches_All.csv'
    if src.exists():
        out_copy.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')


def merge_matches(paths: list[Path], dest: Path):
    dfs = []
    for p in paths:
        if p.exists():
            try:
                dfs.append(pd.read_csv(p))
            except Exception:
                pass
    if not dfs:
        return
    merged = pd.concat(dfs, ignore_index=True).drop_duplicates()
    merged.to_csv(dest, index=False)
    print(f'Merged matches -> {dest} ({len(merged)} rows)')


def export_all(files: list[Path]):
    for f in files:
        env = os.environ.copy()
        env['SUPPLIER_FILE'] = str(f)
        print('EXPORT', f.name)
        try:
            run(['python3', str(BASE / 'export_sbt_rights_eligible.py')], env)
        except Exception as e:
            print('WARN: export failed for', f, e)


def main():
    # 1) Build searchable base (idempotent)
    try:
        run(['python3', str(BASE / 'build_searchable_base.py')])
    except Exception as e:
        print('WARN: searchable base build failed:', e)

    # 2) Batch matches for both roots
    copies = []
    if RAW_F.exists():
        tmp_f = PROC / '_matches_fornecedores.csv'
        batch_matches_for(RAW_F, tmp_f)
        copies.append(tmp_f)
    if RAW_U.exists():
        tmp_u = PROC / '_matches_unified.csv'
        batch_matches_for(RAW_U, tmp_u)
        copies.append(tmp_u)
    # Merge into canonical matches file
    merge_matches(copies, PROC / 'Supplier_Matches_All.csv')

    # 3) Export eligible workbooks for every supplier file
    files = []
    for root in [RAW_F, RAW_U]:
        if root.exists():
            files.extend([p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.xlsx','.xls'}])
    export_all(sorted(files))

    # 4) Rebuild rollups
    run(['python3', str(BASE / 'build_value_rollups.py')])

    # 5) Rebuild fornecedores + unified summaries
    run(['python3', str(BASE / 'build_fornecedores_summaries.py')])
    run(['python3', str(BASE / 'build_unified_summaries.py')])

    print('Pipeline completed.')


if __name__ == '__main__':
    main()

