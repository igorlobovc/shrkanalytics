import os
import duckdb, pandas as pd

root = "/Users/igorcunha/SHRKVSCODE/Estelita"
db   = f"{root}/primary_archive.duckdb"
out_path = f"{root}/Processed/match_sample_50_fixed.csv"

con = duckdb.connect(db)
obras = con.execute("SELECT * FROM obras_clean").df()
fona  = con.execute("SELECT * FROM fonogramas_clean").df()

title_o = next((c for c in obras.columns if "title" in c.lower() or "titulo" in c.lower()), obras.columns[0])
title_f = next((c for c in fona.columns if "title" in c.lower() or "titulo" in c.lower()), fona.columns[0])
artist_o = next((c for c in obras.columns if "artist" in c.lower() or "autor" in c.lower()), None)
artist_f = next((c for c in fona.columns if "artist" in c.lower() or "interprete" in c.lower()), None)

if artist_o and artist_f:
    rels = obras.merge(fona, left_on=[title_o, artist_o], right_on=[title_f, artist_f],
                       how='inner', suffixes=('_obra','_fona'))
    rels["link_method"] = "title_artist"
    rels["confidence"] = 0.95
else:
    rels = obras.merge(fona, left_on=title_o, right_on=title_f,
                       how='inner', suffixes=('_obra','_fona'))
    rels["link_method"] = "title_only"
    rels["confidence"] = 0.90

rels = rels.assign(source_supplier="ESTELITA", source_sheet="v2_master")
rels.to_csv(out_path, index=False)
con.close()

print(f"✅ RELATIONS file written: {out_path}")
print("Total matched rows:", len(rels))