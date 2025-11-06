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
