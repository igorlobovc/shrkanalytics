import os
from pathlib import Path
import duckdb, pandas as pd
import numpy as np
import re

# Use repo-relative paths instead of absolute
BASE_DIR = Path(__file__).resolve().parent
db = str(BASE_DIR / "primary_archive.duckdb")
out_path = str(BASE_DIR / "Processed/match_sample_50_fixed.csv")

LIMIT_ROWS = int(os.environ.get("MATCH_SAMPLE_LIMIT", "50000"))

con = duckdb.connect(db)
obras = con.execute(f"SELECT * FROM obras_clean LIMIT {LIMIT_ROWS}").df()
fona  = con.execute(f"SELECT * FROM fonogramas_clean LIMIT {LIMIT_ROWS}").df()

# Drop rows that are entirely empty
obras = obras.dropna(how='all')
fona  = fona.dropna(how='all')

def pick_text_col(df: pd.DataFrame) -> str:
    best_col, best_score = None, -1.0
    header_pattern = re.compile(r"RELAT[ÍI]RIO ANAL[ÍI]TICO", re.IGNORECASE)
    for c in df.columns:
        s = df[c].astype(str)
        nn = (s.str.len() > 0) & (~s.str.lower().isin(["nan","none","null"]))
        nn_count = nn.sum()
        if nn_count == 0:
            continue
        # penalize columns that look like headers
        header_penalty = (s.str.contains(header_pattern, na=False)).mean()
        space_ratio = (s.str.contains(r"\s", na=False)).mean()
        uniq_ratio = s[nn].nunique() / max(1, nn_count)
        score = (nn_count / len(s)) * (0.6*space_ratio + 0.4*uniq_ratio) * (1 - header_penalty)
        if score > best_score:
            best_score, best_col = score, c
    return best_col or df.columns[0]

title_o = pick_text_col(obras)
title_f = pick_text_col(fona)

artist_o = next((c for c in obras.columns if any(k in c.lower() for k in ["artist","autor","intérprete","interprete"])), None)
artist_f = next((c for c in fona.columns if any(k in c.lower() for k in ["artist","autor","intérprete","interprete"])), None)

def norm(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower()

if artist_o and artist_f and artist_o in obras.columns and artist_f in fona.columns:
    left = obras.copy()
    right = fona.copy()
    left['__t__'] = norm(left[title_o])
    right['__t__'] = norm(right[title_f])
    left['__a__'] = norm(left[artist_o])
    right['__a__'] = norm(right[artist_f])
    # filter empties
    left = left[(left['__t__']!='') & (~left['__t__'].isin(['nan','none','null'])) & (left['__a__']!='') & (~left['__a__'].isin(['nan','none','null']))]
    right = right[(right['__t__']!='') & (~right['__t__'].isin(['nan','none','null'])) & (right['__a__']!='') & (~right['__a__'].isin(['nan','none','null']))]
    rels = left.merge(right, left_on=['__t__','__a__'], right_on=['__t__','__a__'], how='inner', suffixes=('_obra','_fona'))
    rels["link_method"] = "title_artist"
    rels["confidence"] = 0.95
else:
    left = obras.copy()
    right = fona.copy()
    left['__t__'] = norm(left[title_o])
    right['__t__'] = norm(right[title_f])
    # filter empties
    left = left[(left['__t__']!='') & (~left['__t__'].isin(['nan','none','null']))]
    right = right[(right['__t__']!='') & (~right['__t__'].isin(['nan','none','null']))]
    rels = left.merge(right, left_on='__t__', right_on='__t__', how='inner', suffixes=('_obra','_fona'))
    rels["link_method"] = "title_only"
    rels["confidence"] = 0.90

# Ensure output directory exists
Path(out_path).parent.mkdir(parents=True, exist_ok=True)

rels = rels.assign(source_supplier="ESTELITA", source_sheet="v2_master")
rels.to_csv(out_path, index=False)
con.close()

print(f"✅ RELATIONS file written: {out_path}")
print("Total matched rows:", len(rels))
