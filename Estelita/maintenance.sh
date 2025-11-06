#!/bin/zsh
cd /Users/igorcunha/SHRKVSCODE/Estelita

echo "🔍 Verifying database tables..."
python3 - <<'PY'
import duckdb
con = duckdb.connect("primary_archive.duckdb")
for t in ["OBRAS","RECORDINGS","GAZETTEER","RELATIONS"]:
    try:
        c = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {c} rows")
    except Exception as e:
        print(f"{t}: not found ({e})")
con.close()
PY

echo "\n🧹 Removing temporary junk..."
rm -f match_sample_50_fixed.csv *_clean.duckdb

echo "\n📂 Folder overview:"
tree -L 2
