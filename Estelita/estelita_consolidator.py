# estelita_consolidator.py

import os
import pandas as pd
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from rapidfuzz import fuzz
from unidecode import unidecode
import re
import json
from datetime import datetime

# === ENVIRONMENT & PATH SETUP === #
BASE_DIR = Path("/Users/igorcunha/SHRKVSCODE/Estelita")
VENV_PYTHON = "/usr/local/bin/python3"

RAW_OBRAS_PATH = BASE_DIR / "Raw/ESTELITA OBRAS_v2.xlsx"
RAW_FONOS_PATH = BASE_DIR / "Raw/ESTELITA Fonogramas_v2.xlsx"
DUCK_DB_PATH = BASE_DIR / "primary_archive.duckdb"
LOG_DIR = BASE_DIR / "Processed/_logs"
OUTPUT_PARQUET = BASE_DIR / "Processed/Consolidated_Reference.parquet"
OUTPUT_CSV = BASE_DIR / "Processed/Consolidated_Reference.csv"

# === NORMALIZATION RULES === #
def normalize_text(text):
    if pd.isna(text):
        return ""
    text = str(text)
    text = unidecode(text.strip().lower())
    text = re.sub(r"\s+", " ", text)
    return text

def title_case(text):
    return text.title() if isinstance(text, str) else text

# === DURATION PARSER === #
def parse_duration(d):
    if pd.isna(d):
        return None
    try:
        d = str(d).strip()
        if re.match(r"^\d{1,2}:\d{2}$", d):  # mm:ss
            m, s = map(int, d.split(":"))
            return m * 60 + s
        elif re.match(r"^\d{1}:\d{2}:\d{2}$", d):  # h:mm:ss
            h, m, s = map(int, d.split(":"))
            return h * 3600 + m * 60 + s
    except:
        return None
    return None

# === CORE LOAD FUNCTION === #
def load_xlsx(path, expected_sheet=None):
    return pd.read_excel(path, sheet_name=expected_sheet) if path.exists() else pd.DataFrame()

def load_duckdb_table(db_path, table_name):
    con = duckdb.connect(str(db_path))
    try:
        return con.execute(f"SELECT * FROM {table_name}").fetchdf()
    except:
        return pd.DataFrame()

# === DATA SOURCES === #
obras_df = load_xlsx(RAW_OBRAS_PATH)
fonos_df = load_xlsx(RAW_FONOS_PATH)
obras_db_df = load_duckdb_table(DUCK_DB_PATH, "obras_clean")
fonos_db_df = load_duckdb_table(DUCK_DB_PATH, "fonogramas_clean")

# === CONSOLIDATION PREP === #
combined = pd.concat([obras_df, obras_db_df, fonos_df, fonos_db_df], ignore_index=True)

# === NORMALIZE & CLEAN COLUMNS === #
for col in combined.columns:
    combined[col] = combined[col].apply(normalize_text)

combined["duration_seconds"] = combined.get("duracao", "").apply(parse_duration)

# === SYNTHETIC ID GENERATION === #
combined["work_id"] = combined.apply(lambda row: f"OBR_{row.name+1:06}" if "iswc" in row and row["iswc"] else "", axis=1)
combined["recording_id"] = combined.apply(lambda row: f"FON_{row.name+1:06}" if "isrc" in row and row["isrc"] else "", axis=1)

# === MERGE LOGIC BASED ON INSTRUCTIONS === #
combined["merge_key"] = combined.apply(
    lambda row: f"{normalize_text(row.get('titulo',''))}__{normalize_text(row.get('autor',''))}", axis=1
)

deduped = combined.drop_duplicates(subset=["iswc", "isrc", "merge_key"])

# === FINAL FORMATTING === #
deduped["title"] = deduped["titulo"].apply(title_case)
deduped["artist"] = deduped["autor"].apply(title_case)
deduped["association"] = deduped["associacao"].str.upper()
deduped["confidence"] = 1.0  # Placeholder for matching confidence

# === OUTPUT FILES === #
table = pa.Table.from_pandas(deduped)
pq.write_table(table, OUTPUT_PARQUET)
deduped.to_csv(OUTPUT_CSV, index=False)
deduped.head(100).to_csv(LOG_DIR / "Consolidated_Reference.sample_head.csv", index=False)

# === METADATA LOGS === #
report = {
    "timestamp": datetime.now().isoformat(),
    "total_rows": len(deduped),
    "unique_works": deduped["work_id"].nunique(),
    "unique_recordings": deduped["recording_id"].nunique(),
    "null_title_pct": round(deduped["title"].isna().sum() / len(deduped) * 100, 2),
}

with open(LOG_DIR / "Consolidated_Reference.report.json", "w") as f:
    json.dump(report, f, indent=2)

# === AMBIGUOUS & DUPLICATES (SAMPLES) === #
# This would require fuzzy matching pass for ambiguous groups

print("✅ ESTELITA CONSOLIDATOR finished.")