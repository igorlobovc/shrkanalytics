#!/usr/bin/env python3
"""
Build RELATIONS via in-DB join and profile input patterns.
- Detects candidate title columns
- Generates stable recording IDs if missing
- Joins WORKS <> RECORDINGS on normalized titles
- Outputs RELATIONS_AUTO table and CSV
- Reports main input kinds and highlights the second-most common that breaks pattern
"""

import sys
from pathlib import Path
import duckdb
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "primary_archive.duckdb"
OUT_DIR = BASE_DIR / "Processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(DB_PATH))

def q(ident: str) -> str:
    return '"' + ident.replace('"','""') + '"'

def list_text_columns(table: str) -> list[str]:
    info = con.execute(f"PRAGMA table_info({table})").fetchdf()
    return info['name'].tolist()

def pick_title_column(table: str, header_pattern: str | None = None) -> str | None:
    cols = list_text_columns(table)
    best, best_score = None, -1.0
    for c in cols:
        # Skip obvious index placeholders
        # Compute basic stats for scoring
        nn = con.execute(f"SELECT COUNT(*) FROM {table} WHERE {q(c)} IS NOT NULL").fetchone()[0]
        total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if total == 0:
            return None
        if nn == 0:
            continue
        # fraction containing spaces
        space = con.execute(
            f"SELECT AVG(CASE WHEN CAST({q(c)} AS VARCHAR) ~ '\\s' THEN 1 ELSE 0 END)::DOUBLE FROM {table}"
        ).fetchone()[0]
        # header penalty
        header_pen = 0.0
        if header_pattern:
            header_pen = con.execute(
                f"SELECT AVG(CASE WHEN CAST({q(c)} AS VARCHAR) ILIKE ? THEN 1 ELSE 0 END)::DOUBLE FROM {table}",
                [f"%{header_pattern}%"],
            ).fetchone()[0]
        # numeric-only penalty
        num_only = con.execute(
            f"SELECT AVG(CASE WHEN CAST({q(c)} AS VARCHAR) ~ '^[0-9.,-]+$' THEN 1 ELSE 0 END)::DOUBLE FROM {table}"
        ).fetchone()[0]
        # title-like bonus (common PT articles/punctuation in titles)
        title_bonus = con.execute(
            f"SELECT AVG(CASE WHEN LOWER(CAST({q(c)} AS VARCHAR)) LIKE '% de %' OR LOWER(CAST({q(c)} AS VARCHAR)) LIKE '% da %' OR LOWER(CAST({q(c)} AS VARCHAR)) LIKE '% do %' OR CAST({q(c)} AS VARCHAR) LIKE 'A %' OR CAST({q(c)} AS VARCHAR) LIKE 'O %' OR CAST({q(c)} AS VARCHAR) LIKE '%(%' OR CAST({q(c)} AS VARCHAR) LIKE '%-%' THEN 1 ELSE 0 END)::DOUBLE FROM {table}"
        ).fetchone()[0]
        # uniqueness among non-nulls
        uniq = con.execute(
            f"SELECT COUNT(DISTINCT CAST({q(c)} AS VARCHAR)) FROM {table} WHERE {q(c)} IS NOT NULL"
        ).fetchone()[0]
        uniq_ratio = (uniq / nn) if nn else 0.0
        nn_ratio = nn / total
        score = nn_ratio * (0.6 * (space or 0.0) + 0.4 * uniq_ratio) * (1 - (header_pen or 0.0)) * (1 - (num_only or 0.0)) * (1 + 0.5 * (title_bonus or 0.0))
        if score > best_score:
            best, best_score = c, score
    return best

def works_title_column() -> str:
    cols = list_text_columns('WORKS')
    if 'title_base' in cols:
        # prefer base if it has data
        cnt = con.execute("SELECT COUNT(*) FROM WORKS WHERE title_base IS NOT NULL AND title_base <> ''").fetchone()[0]
        if cnt > 0:
            return 'title_base'
    if 'title_original' in cols:
        return 'title_original'
    # fallback heuristic
    cand = pick_title_column('WORKS')
    return cand or cols[0]

def ensure_recording_ids(rec_table: str = 'RECORDINGS') -> str:
    cols = list_text_columns(rec_table)
    if 'recording_id' in cols:
        return rec_table  # already has IDs
    # Build a temporary view with synthetic IDs
    con.execute("DROP VIEW IF EXISTS RECORDINGS_WITH_ID")
    con.execute(
        """
        CREATE VIEW RECORDINGS_WITH_ID AS
        SELECT 
          'R' || LPAD(CAST(ROW_NUMBER() OVER () AS VARCHAR), 6, '0') AS recording_id,
          *
        FROM RECORDINGS
        """
    )
    return 'RECORDINGS_WITH_ID'

def normalize_expr(col: str) -> str:
    ident = q(col)
    return f"LOWER(REGEXP_REPLACE(TRIM(CAST({ident} AS VARCHAR)), '\\s+', ' '))"

print("🔎 Profiling columns…")
def pick_recordings_title_by_overlap(w_title_col: str) -> str | None:
    cols = list_text_columns('RECORDINGS')
    # Build normalized works set
    wnorm = normalize_expr(w_title_col)
    con.execute("DROP VIEW IF EXISTS WORKS_NORM_FOR_PICK")
    con.execute(f"CREATE VIEW WORKS_NORM_FOR_PICK AS SELECT DISTINCT {wnorm} AS t FROM WORKS WHERE {wnorm} IS NOT NULL AND {wnorm} <> ''")
    best, best_cnt = None, -1
    for c in cols:
        rnorm = normalize_expr(c)
        cnt = con.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT {rnorm} AS t FROM RECORDINGS WHERE {q(c)} IS NOT NULL) r WHERE t IN (SELECT t FROM WORKS_NORM_FOR_PICK)"
        ).fetchone()[0]
        if cnt > best_cnt:
            best, best_cnt = c, cnt
    return best

w_title_col = works_title_column()
rec_title_col = pick_recordings_title_by_overlap(w_title_col) or pick_title_column('RECORDINGS', header_pattern='RELATÓRIO ANAL')
rec_table = ensure_recording_ids()

if not rec_title_col:
    print("ERROR: Could not determine a recordings title column.")
    sys.exit(1)

print(f"WORKS title column: {w_title_col}")
print(f"RECORDINGS title column: {rec_title_col}")

# Build normalized projections
con.execute("DROP VIEW IF EXISTS WORKS_NORM")
con.execute(
    f"""
    CREATE VIEW WORKS_NORM AS
    SELECT work_id, {normalize_expr(w_title_col)} AS title_norm
    FROM WORKS
    WHERE {normalize_expr(w_title_col)} IS NOT NULL AND {normalize_expr(w_title_col)} <> ''
    """
)

con.execute("DROP VIEW IF EXISTS RECORDINGS_NORM")
con.execute(
    f"""
    CREATE VIEW RECORDINGS_NORM AS
    SELECT recording_id, {normalize_expr(rec_title_col)} AS title_norm
    FROM {rec_table}
    WHERE {normalize_expr(rec_title_col)} IS NOT NULL AND {normalize_expr(rec_title_col)} <> ''
    """
)

print("🔗 Joining WORKS and RECORDINGS on normalized title…")

con.execute("DROP TABLE IF EXISTS RELATIONS_AUTO")
con.execute(
    """
    CREATE TABLE RELATIONS_AUTO AS
    SELECT w.work_id, r.recording_id, 'title_only' AS link_method, 0.90 AS confidence
    FROM WORKS_NORM w
    JOIN RECORDINGS_NORM r USING (title_norm)
    """
)

# Export to CSV
out_csv = OUT_DIR / "RELATIONS_AUTO.csv"
con.execute("COPY (SELECT * FROM RELATIONS_AUTO) TO ? (HEADER, DELIMITER ',')", [str(out_csv)])

print(f"✅ RELATIONS_AUTO created with {con.execute('SELECT COUNT(*) FROM RELATIONS_AUTO').fetchone()[0]} rows")
print(f"💾 Saved: {out_csv}")

# Input pattern profiling
print("\n🧪 Profiling input kinds…")

# WORKS categories
w_title_expr = normalize_expr(w_title_col)
w_cats = con.execute(
    f"""
    SELECT CASE 
             WHEN {w_title_expr} IS NULL OR {w_title_expr} = '' THEN 'missing_title'
             WHEN {w_title_col} = title_base AND {w_title_col} IS NOT NULL THEN 'title_base'
             ELSE 'title_original_or_other'
           END AS category,
           COUNT(*) AS cnt
    FROM WORKS
    GROUP BY 1
    ORDER BY cnt DESC
    """
).fetchdf()

# RECORDINGS categories
rec_title_expr = normalize_expr(rec_title_col)
r_cats = con.execute(
    f"""
    SELECT CASE 
             WHEN {rec_title_expr} IS NULL OR {rec_title_expr} = '' THEN 'blank_row'
             WHEN CAST({q(rec_title_col)} AS VARCHAR) ILIKE '%RELATÓRIO ANAL%' THEN 'header_row'
             ELSE 'has_title'
           END AS category,
           COUNT(*) AS cnt
    FROM {rec_table}
    GROUP BY 1
    ORDER BY cnt DESC
    """
).fetchdf()

def summarize(df: pd.DataFrame, label: str):
    if df.empty:
        print(f"No categories for {label}")
        return
    print(f"\n{label} categories:")
    for _, row in df.iterrows():
        print(f"- {row['category']}: {int(row['cnt'])}")
    if len(df) >= 2:
        second = df.iloc[1]
        print(f"  ↳ Second most common: {second['category']} ({int(second['cnt'])})")

summarize(w_cats, "WORKS")
summarize(r_cats, "RECORDINGS")

# Sample rows for second-most common that breaks pattern
def sample_second_most(table: str, expr: str, selector_sql: str, title_col: str, limit: int = 10) -> pd.DataFrame:
    cats = con.execute(
        f"SELECT cat, cnt FROM (SELECT {selector_sql} AS cat, COUNT(*) AS cnt FROM {table} GROUP BY 1) ORDER BY cnt DESC"
    ).fetchdf()
    if len(cats) < 2:
        return pd.DataFrame()
    target = cats.iloc[1]['cat']
    return con.execute(
        f"""
        SELECT * FROM {table}
        WHERE {selector_sql} = ?
        LIMIT {limit}
        """ , [target]
    ).fetchdf()

works_selector = f"CASE WHEN {w_title_expr} IS NULL OR {w_title_expr} = '' THEN 'missing_title' ELSE 'has_title' END"
rec_selector = f"CASE WHEN {rec_title_expr} IS NULL OR {rec_title_expr} = '' THEN 'blank_row' WHEN CAST({q(rec_title_col)} AS VARCHAR) ILIKE '%RELATÓRIO ANAL%' THEN 'header_row' ELSE 'has_title' END"

works_second = sample_second_most('WORKS', w_title_expr, works_selector, w_title_col)
recs_second = sample_second_most(rec_table, rec_title_expr, rec_selector, rec_title_col)

sample_out = OUT_DIR / "RELATIONS_INPUT_PATTERNS.xlsx"
with pd.ExcelWriter(sample_out) as wr:
    w_cats.to_excel(wr, sheet_name="WORKS_CATEGORIES", index=False)
    r_cats.to_excel(wr, sheet_name="RECORDINGS_CATEGORIES", index=False)
    if not works_second.empty:
        works_second.to_excel(wr, sheet_name="WORKS_SECOND_SAMPLE", index=False)
    if not recs_second.empty:
        recs_second.to_excel(wr, sheet_name="RECS_SECOND_SAMPLE", index=False)

print(f"📝 Pattern report saved: {sample_out}")
con.close()
