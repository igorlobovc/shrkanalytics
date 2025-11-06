#!/usr/bin/env python3
"""
Enhanced version — no file skipped silently. Generates clean files, unified dataset and pending log.
"""

import unicodedata
from pathlib import Path
from typing import List, Dict, Optional, Any
import pandas as pd
import datetime

# === Paths ===
RAW_ROOT = Path("/Users/igorcunha/SHRKVSCODE/Estelita/Raw/Fornecedores")
OUTPUT_CLEAN_DIR = Path("/Users/igorcunha/SHRKVSCODE/Processed/Cleaned_Per_Provider")
OUTPUT_UNIFIED_PATH = Path("/Users/igorcunha/SHRKVSCODE/Processed/Unified_CheckBase.xlsx")
OUTPUT_LOG_PATH = Path("/Users/igorcunha/SHRKVSCODE/Processed/Logs/Pending_Files.csv")

# Ensure directories
OUTPUT_CLEAN_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_UNIFIED_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

unified = []

def nfkd_lower(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()

def detect_schema(df: pd.DataFrame) -> str:
    header_lines = []
    for i in range(min(10, len(df))):
        vals = df.iloc[i].astype(str).tolist()
        line = " ".join([v for v in vals if v and v != "nan"])[:200]
        header_lines.append(nfkd_lower(line))
    header_text = " ".join(header_lines)
    if ("titulo original" in header_text and "data exibicao" in header_text) or ("titulo da obra" in header_text and "planilha de sincronizacao" in header_text):
        return "UBEM_CUESHEET"
    if "sincronizacao musical" in header_text or ("canal:" in header_text and "periodo:" in header_text):
        return "UBEM_RELATORIO"
    return "UNKNOWN"

def parse_cuesheet(path: Path, sheet: str, df: pd.DataFrame, provider: str) -> List[Dict[str, Any]]:
    records = []
    cols = [nfkd_lower(str(c)) for c in df.columns]
    def find_col(options): 
        for opt in options:
            if opt in cols:
                return df.columns[cols.index(opt)]
        return None
    col_title = find_col(["titulo original","titulo","titulo da obra"])
    col_artist = find_col(["intérprete","interprete","artista","autor"])
    for idx, row in df.iterrows():
        title = str(row.get(col_title)) if col_title else None
        if not title or title.strip().lower() == "nan":
            continue
        records.append({
            "provider": provider, "schema_type": "UBEM_CUESHEET",
            "title_original": title.strip(),
            "artist": str(row.get(col_artist)).strip() if col_artist else None,
            "ref_file": path.name, "ref_sheet": sheet, "ref_row": idx + 1
        })
    return records

def parse_relatorio(path: Path, sheet: str, df: pd.DataFrame, provider: str) -> List[Dict[str, Any]]:
    records = []
    canal = programa = periodo = None
    for i in range(min(10, len(df))):
        line = " ".join([str(x) for x in df.iloc[i].dropna().astype(str).tolist()])
        if "canal:" in nfkd_lower(line): canal = line.split(":",1)[1].strip()
        if "programa:" in nfkd_lower(line): programa = line.split(":",1)[1].strip()
        if "periodo:" in nfkd_lower(line): periodo = line.split(":",1)[1].strip()
    header_row = next((i for i in range(len(df)) if any("titulo" in str(c).lower() for c in df.iloc[i].tolist())), 3)
    df_data = pd.read_excel(path, sheet_name=sheet, header=header_row)
    col_title = next((c for c in df_data.columns if "titulo" in nfkd_lower(str(c))), None)
    for idx, row in df_data.iterrows():
        title = row.get(col_title)
        if not title or str(title).strip() == "":
            continue
        records.append({
            "provider": provider, "schema_type": "UBEM_RELATORIO",
            "title_original": str(title).strip(),
            "channel": canal, "program": programa, "period": periodo,
            "ref_file": path.name, "ref_sheet": sheet, "ref_row": idx + header_row + 1
        })
    return records

def process_file(path: Path, provider: str, pending: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    recs = []
    try:
        xl = pd.ExcelFile(path)
    except Exception as e:
        print(f"🚨 Falha ao abrir {path.name}: {e}")
        pending.append({"provider": provider, "file": path.name, "issue": f"Erro ao abrir: {e}"})
        return recs
    for sheet in xl.sheet_names:
        try:
            df = xl.parse(sheet, header=None)
        except Exception as e:
            print(f"🚨 Falha ao ler sheet {sheet} em {path.name}: {e}")
            pending.append({"provider": provider, "file": path.name, "sheet": sheet, "issue": str(e)})
            continue
        schema = detect_schema(df)
        if schema == "UBEM_CUESHEET":
            recs.extend(parse_cuesheet(path, sheet, xl.parse(sheet, header=0), provider))
        elif schema == "UBEM_RELATORIO":
            recs.extend(parse_relatorio(path, sheet, df, provider))
        else:
            print(f"🚨 {path.name} ({sheet}) NÃO reconhecido — adicionado aos pendentes.")
            pending.append({"provider": provider, "file": path.name, "sheet": sheet, "issue": "Schema desconhecido"})
    return recs

def main():
    global unified
    unified, pending, schema_stats = [], [], []
    if not RAW_ROOT.exists():
        print(f"❌ Diretório não encontrado: {RAW_ROOT}")
        return
    run_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines = [f"===== EXECUÇÃO {run_time} =====\n"]
    for pdir in RAW_ROOT.iterdir():
        if not pdir.is_dir(): continue
        provider, prov_recs = pdir.name, []
        provider_files = list(pdir.glob("**/*"))
        if not provider_files:
            print(f"⚠️ {provider}: sem arquivos encontrados.")
            log_lines.append(f"[{provider}] Nenhum arquivo encontrado.\n")
            continue
        for path in provider_files:
            if path.is_file() and path.suffix.lower() in {".xlsx",".xls",".xlsb"}:
                print(f"📂 Processando {provider}/{path.name}")
                start_count = len(prov_recs)
                prov_recs.extend(process_file(path, provider, pending))
                schema_used = 'DESCONHECIDO'
                if prov_recs and len(prov_recs) > start_count:
                    schema_used = prov_recs[-1].get("schema_type", "DESCONHECIDO")
                schema_stats.append({"provider": provider, "file": path.name, "schema": schema_used})
        if prov_recs:
            dfp = pd.DataFrame(prov_recs)
            outp = OUTPUT_CLEAN_DIR / f"{provider}_clean.xlsx"
            dfp.to_excel(outp, index=False)
            print(f"✅ {provider}: {len(prov_recs)} registros salvos em {outp}")
            unified.extend(prov_recs)
            log_lines.append(f"[{provider}] {len(prov_recs)} registros ({len(provider_files)} arquivos)\n")
        else:
            print(f"⚠️ Nenhum registro reconhecido em {provider}")
            log_lines.append(f"[{provider}] 0 registros reconhecidos ({len(provider_files)} arquivos)\n")
    if unified:
        try:
            pd.DataFrame(unified).to_excel(OUTPUT_UNIFIED_PATH, index=False)
            print(f"✅ Base unificada salva em {OUTPUT_UNIFIED_PATH}")
        except Exception as e:
            print(f"🚨 Erro ao salvar base unificada: {e}")
    if pending:
        try:
            pd.DataFrame(pending).to_csv(OUTPUT_LOG_PATH, index=False, encoding="utf-8")
            print(f"🚨 Arquivos pendentes registrados em {OUTPUT_LOG_PATH}")
        except Exception as e:
            print(f"🚨 Erro ao salvar arquivo pendente: {e}")
    if schema_stats:
        df_schema = pd.DataFrame(schema_stats)
        try:
            df_schema.to_excel(OUTPUT_LOG_PATH.parent / "Schema_Stats.xlsx", index=False)
            print(f"📘 Estatísticas de schema salvas em Schema_Stats.xlsx")
        except Exception as e:
            print(f"🚨 Erro ao salvar estatísticas de schema: {e}")
    # Summary report
    processed_counts = {}
    skipped_counts = {}
    pending_counts = {}
    for s in schema_stats:
        processed_counts[s["provider"]] = processed_counts.get(s["provider"], 0) + 1
    for p in pending:
        pending_counts[p["provider"]] = pending_counts.get(p["provider"], 0) + 1
    for pdir in RAW_ROOT.iterdir():
        if not pdir.is_dir():
            continue
        provider = pdir.name
        total_files = len([f for f in pdir.glob("**/*") if f.is_file() and f.suffix.lower() in {".xlsx",".xls",".xlsb"}])
        processed = processed_counts.get(provider, 0)
        pending_c = pending_counts.get(provider, 0)
        skipped = total_files - processed
        skipped_counts[provider] = skipped
        summary_line = f"[{provider}] Arquivos: {total_files}, Processados: {processed}, Pendentes: {pending_c}, Ignorados: {skipped}\n"
        print(summary_line.strip())
        log_lines.append(summary_line)
        if total_files > 0 and processed == 0:
            warning_line = f"⚠️ Atenção: {provider} não processou nenhum arquivo válido.\n"
            print(warning_line.strip())
            log_lines.append(warning_line)
    with open(OUTPUT_LOG_PATH.parent / "Run_Log.txt", "a", encoding="utf-8") as f:
        f.writelines(log_lines)
        f.write("\n")
    print("🏁 Execução finalizada — verifique o Run_Log.txt para detalhes.")

    # Extra safeguard: loga qualquer pasta sem arquivos válidos
    if not unified:
        print("⚠️ Nenhum registro unificado foi gerado. Revise a origem dos arquivos.")

if __name__ == "__main__":
    main()