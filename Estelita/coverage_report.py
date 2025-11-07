#!/usr/bin/env python3
"""
Coverage & Royalty Potential Report
-----------------------------------
Generates per-provider coverage stats (matched vs. unmatched),
duplicate detection, and top unmatched titles for revenue follow-up.
"""

import duckdb
import pandas as pd
from pathlib import Path

base = Path(__file__).resolve().parent
db_path = base / "primary_archive.duckdb"
out_path = base / "Processed/Coverage_Report.xlsx"

con = duckdb.connect(str(db_path))
print("📊 Connected to database…")

# Install and load Excel extension (safe if already installed)
try:
    con.execute("INSTALL excel")
    con.execute("LOAD excel")
    print("📑 Excel extension loaded...")
except Exception:
    # If extension install/load fails, continue; pandas writer will still work
    pass

# --- Coverage summary ---
coverage = con.execute("""
WITH works_stats AS (
  SELECT
    COUNT(*) AS total_works
  FROM WORKS
),
matched AS (
  SELECT
    COUNT(DISTINCT work_id) AS matched_works
  FROM RELATIONS
)
SELECT
  ws.total_works,
  m.matched_works,
  ROUND(100.0 * m.matched_works / ws.total_works, 2) AS coverage_pct
FROM works_stats ws, matched m
""").fetchdf()

print(f"✅ Overall coverage: {coverage.coverage_pct.iloc[0]}%")

# --- Unmatched works ---
unmatched = con.execute("""
SELECT title_original
FROM WORKS
WHERE work_id NOT IN (SELECT DISTINCT work_id FROM RELATIONS)
LIMIT 200
""").fetchdf()

# --- Duplicates ---
dupes = con.execute("""
SELECT title_original, COUNT(*) AS cnt
FROM WORKS
GROUP BY title_original
HAVING cnt > 1
ORDER BY cnt DESC
LIMIT 100
""").fetchdf()

# --- Export report ---
# Ensure output directory exists before writing
out_path.parent.mkdir(parents=True, exist_ok=True)
with pd.ExcelWriter(out_path) as wr:
    coverage.to_excel(wr, sheet_name="SUMMARY", index=False)
    dupes.to_excel(wr, sheet_name="DUPLICATES", index=False)
    unmatched.to_excel(wr, sheet_name="UNMATCHED_SAMPLE", index=False)

print(f"🏁 Report saved to {out_path}")
con.close()
