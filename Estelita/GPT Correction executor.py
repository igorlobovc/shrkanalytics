import pandas as pd
import os

root = "/Users/igorcunha/SHRKVSCODE/Estelita"
raw_path = f"{root}/Raw/ESTELITA Fonogramas_v2.xlsx"
processed = f"{root}/Processed"
os.makedirs(processed, exist_ok=True)

df = pd.read_excel(raw_path, header=None)
col_f = df.iloc[:, 5].astype(str).fillna("")

groups = []
current_title = None
current_rows = []
current_associations = []
work_id = 0
titles_seen = set()

def is_association(text):
    return "ASSOCIAÇÃO" in text.upper()

for i, val in enumerate(col_f):
    val_clean = val.strip().upper()

    # Detect start of new block
    if "TÍTULO PRINCIPAL DA OBRA MUSICAL" in val_clean:
        # If there is an existing block, save it
        if current_title is not None and current_rows:
            work_id += 1
            groups.append({
                "work_id": f"OBR_{work_id:04d}",
                "title": current_title.title(),
                "associations": current_associations,
                "rows_in_block": len(current_rows),
                "start_row": current_rows[0],
                "end_row": current_rows[-1]
            })
        current_title = None
        current_rows = []
        current_associations = []
    elif val_clean != "":
        # If no current title, assign this as title
        if current_title is None:
            current_title = val_clean
            current_rows = [i]
            current_associations = []
        else:
            # If this is a new title different from current title, start a new block
            if val_clean != current_title and not is_association(val_clean):
                # Save current block
                if current_title is not None and current_rows:
                    work_id += 1
                    groups.append({
                        "work_id": f"OBR_{work_id:04d}",
                        "title": current_title.title(),
                        "associations": current_associations,
                        "rows_in_block": len(current_rows),
                        "start_row": current_rows[0],
                        "end_row": current_rows[-1]
                    })
                # Start new block
                current_title = val_clean
                current_rows = [i]
                current_associations = []
            else:
                # This is an association or same title line inside block
                current_rows.append(i)
                if is_association(val_clean):
                    current_associations.append(val_clean)

# Add the last block if exists
if current_title is not None and current_rows:
    work_id += 1
    groups.append({
        "work_id": f"OBR_{work_id:04d}",
        "title": current_title.title(),
        "associations": current_associations,
        "rows_in_block": len(current_rows),
        "start_row": current_rows[0],
        "end_row": current_rows[-1]
    })

grouped = pd.DataFrame(groups)
before_dedup = len(grouped)
grouped = grouped.drop_duplicates(subset=["title"]).reset_index(drop=True)
duplicates_collapsed = before_dedup - len(grouped)

output_path = os.path.join(processed, "grouped_fonogramas.xlsx")
grouped.to_excel(output_path, index=False)

print(f"✅ Grouped file written: {output_path}")
print(f"Total blocks found: {before_dedup}, unique titles: {len(grouped)}, duplicates collapsed: {duplicates_collapsed}, rows processed: {len(df)}")

import pandas as pd
import os
import re
from unidecode import unidecode

root = "/Users/igorcunha/SHRKVSCODE/Estelita/Raw"
processed = "/Users/igorcunha/SHRKVSCODE/Estelita/Processed"
os.makedirs(processed, exist_ok=True)

def detect_header(path):
    """
    Detects the correct Excel header row by searching for key columns in first 5 rows.
    """
    for i in range(5):
        df = pd.read_excel(path, header=i, nrows=5)
        cols = [str(c).lower() for c in df.columns]
        if any('obra' in c or 'titulo' in c or 'isrc' in c for c in cols):
            print(f"Header detected at row {i+1} for {os.path.basename(path)}")
            return i
    print(f"Header defaulted to row 1 for {os.path.basename(path)}")
    return 0

def clean_file(path, out_name):
    """
    Cleans the Excel file at `path` and writes the result to `out_name` in the processed folder.
    Returns the cleaned DataFrame.
    """
    print(f"--- Cleaning {os.path.basename(path)} ---")
    header_row = detect_header(path)
    df = pd.read_excel(path, header=header_row)
    original_len = len(df)
    # Clean column names
    df.columns = [unidecode(str(c)).strip().lower().replace(' ', '_') for c in df.columns]
    # Drop rows that are completely empty
    df = df.dropna(how='all')
    # Drop rows with no title (if 'titulo' or 'titulo_da_obra' present)
    title_col = None
    for t in ['titulo', 'titulo_da_obra', 'titulo_do_fonograma']:
        if t in df.columns:
            title_col = t
            break
    if title_col:
        before = len(df)
        df = df[df[title_col].notna()]
        print(f"Dropped {before - len(df)} rows without title.")
    # Convert numeric IDs to strings without .0
    id_cols = []
    for c in df.columns:
        if any(x in c for x in ['cod', 'isrc', 'id', 'obra']): # likely ID columns
            id_cols.append(c)
    for c in id_cols:
        if c in df.columns:
            # Only convert if column is numeric or mixed
            if pd.api.types.is_numeric_dtype(df[c]) or df[c].dtype == object:
                df[c] = df[c].astype(str).str.replace(r'\.0$', '', regex=True)
    out_path = os.path.join(processed, out_name)
    df.to_excel(out_path, index=False)
    print(f"✅ {out_name} written: {len(df):,} rows (from {original_len:,})")
    return df, original_len

summary = []
for f, out in [("ESTELITA OBRAS_v2.xlsx", "OBRAS_CLEAN.xlsx"), ("ESTELITA Fonogramas_v2.xlsx", "FONOGRAMAS_CLEAN.xlsx")]:
    full_path = os.path.join(root, f)
    if os.path.exists(full_path):
        raw = pd.read_excel(full_path)
        cleaned, orig_len = clean_file(full_path, out)
        summary.append({
            "file": f,
            "rows_in": orig_len,
            "rows_out": len(cleaned),
            "dropped_%": round(100 * (1 - len(cleaned)/orig_len), 2) if orig_len else 0.0
        })
    else:
        print(f"⚠️ File not found: {full_path}")

if summary:
    pd.DataFrame(summary).to_csv(os.path.join(processed, "cleaning_report.csv"), index=False)
    print("🧾 Cleaning summary saved.")
else:
    print("No files cleaned, no summary written.")