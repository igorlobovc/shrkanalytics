#!/usr/bin/env python3
"""
Normalize fornecedores sheets into a standard schema across known models.

Inputs: Estelita/Raw/Fornecedores/**/*.xls[x|b]
Output summary: Estelita/Processed/Normalized/_summary.csv
Per-sheet normalized CSVs (optional large): Estelita/Processed/Normalized/<file_stem>__<sheet_norm>.csv

Standard schema columns (best-effort if present):
- provider, file, sheet
- programa, data_exibicao, numero_programa, exibicao_tipo, categoria_programa
- titulo_musica, autor, interprete, tipo_sincronizacao
- percentual_editora, valor_editora_brl, amount_cents, amount_int
- editora, gravadora, iswc, isrc
"""

from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

BASE = Path(__file__).resolve().parent
RAW = BASE / 'Raw' / 'Fornecedores'
PROC = BASE / 'Processed'
OUT = PROC / 'Normalized'
OUT.mkdir(parents=True, exist_ok=True)


def norm(s: str) -> str:
    s = str(s or '').strip().lower()
    try:
        import unicodedata
        s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    except Exception:
        pass
    s = ' '.join(s.split())
    return s


def parse_cents(v) -> int:
    s = str(v or '').strip()
    if not s:
        return 0
    s = s.replace('R$','').replace('$','').replace(' ', '')
    has_dot = '.' in s
    has_comma = ',' in s
    if has_dot and has_comma:
        last = s[max(s.rfind('.'), s.rfind(','))]
        if last == ',':
            s = s.replace('.', '')
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    elif has_comma and not has_dot:
        if re.search(r",\d{2}$", s):
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    elif has_dot and not has_comma:
        if not re.search(r"\.\d{2}$", s):
            s = s.replace('.', '')
    try:
        return int(round(float(s)*100))
    except Exception:
        return 0


def detect_column(df: pd.DataFrame, options: list[str]) -> str | None:
    cols = list(df.columns)
    cn = [norm(c) for c in cols]
    for opt in options:
        o = norm(opt)
        # exact
        for i, x in enumerate(cn):
            if x == o:
                return cols[i]
        # substring
        for i, x in enumerate(cn):
            if o in x:
                return cols[i]
    return None


def normalize_sheet(df: pd.DataFrame) -> pd.DataFrame:
    # Detect columns
    c_programa = detect_column(df, ['PROGRAMA'])
    c_data = detect_column(df, ['DATA DE EXIBIÇÃO','DATA EXIBIÇÃO','Exibição'])
    c_num_prog = detect_column(df, ['NÚMERO PROGRAMA','NÚMERO EPISÓDIO/CAPÍTULO'])
    c_exib_tipo = detect_column(df, ['EXIBIÇÃO (GRAVADO OU REPRISE)','REPRISE'])
    c_cat = detect_column(df, ['CATEGORIA DO PROGRAMA (PROGRAMA, NOVELA)'])
    c_titulo = detect_column(df, ['NOME DA MÚSICA','TÍTULO DA OBRA MUSICAL','Música','TÍTULO'])
    c_autor = detect_column(df, ['AUTOR'])
    c_inter = detect_column(df, ['INTERPRETE','Intérprete'])
    c_tipo_sinc = detect_column(df, ['TIPO DE SINCRONIZAÇÃO','Sincronização','SUBMIX / TIPO DE ARRANJO'])
    c_percent = detect_column(df, ['PERCENTUAL A PAGAR - EDITORA','percentual'])
    c_valor = detect_column(df, ['VALOR A PAGAR - EDITORA','Valor (BRL)','Total'])
    c_editora = detect_column(df, ['EDITORA'])
    c_grav = detect_column(df, ['GRAVADORA'])
    c_iswc = detect_column(df, ['ISWC'])
    c_isrc = detect_column(df, ['ISRC'])

    out = pd.DataFrame()
    def col(src, dst):
        nonlocal out
        if src and src in df.columns:
            out[dst] = df[src]
        else:
            out[dst] = None

    col(c_programa, 'programa')
    col(c_data, 'data_exibicao')
    col(c_num_prog, 'numero_programa')
    col(c_exib_tipo, 'exibicao_tipo')
    col(c_cat, 'categoria_programa')
    col(c_titulo, 'titulo_musica')
    col(c_autor, 'autor')
    col(c_inter, 'interprete')
    col(c_tipo_sinc, 'tipo_sincronizacao')
    col(c_percent, 'percentual_editora')
    col(c_valor, 'valor_editora_brl')
    col(c_editora, 'editora')
    col(c_grav, 'gravadora')
    col(c_iswc, 'iswc')
    col(c_isrc, 'isrc')

    # amounts
    if c_valor and c_valor in df.columns:
        cents = df[c_valor].map(parse_cents)
    else:
        # heuristic: use last column
        last = df.columns[-1]
        cents = df[last].map(parse_cents)
    out['amount_cents'] = cents
    out['amount_int'] = (cents/100.0).round().astype(int)
    return out


def provider_from_path(p: Path) -> str:
    try:
        rel = p.relative_to(RAW)
        return rel.parts[0]
    except Exception:
        return p.parent.name


def main():
    rows = []
    files = [p for p in RAW.rglob('*') if p.is_file() and p.suffix.lower() in {'.xlsx','.xls','.xlsb'}]
    for path in sorted(files):
        prov = provider_from_path(path)
        try:
            xl = pd.ExcelFile(path)
        except Exception:
            continue
        for sheet in xl.sheet_names:
            try:
                df = xl.parse(sheet)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            try:
                normed = normalize_sheet(df)
                normed.insert(0, 'sheet', sheet)
                normed.insert(0, 'file', path.name)
                normed.insert(0, 'provider', prov)
                # Optional: write per-sheet normalized CSVs
                stem = path.stem
                safe_sheet = re.sub(r"[^A-Za-z0-9_.-]+","_", sheet)
                out_path = OUT / f"{stem}__{safe_sheet}__normalized.csv"
                normed.to_csv(out_path, index=False)
                rows.append({
                    'provider': prov,
                    'file': path.name,
                    'sheet': sheet,
                    'rows': int(len(normed)),
                    'found_columns': ';'.join([c for c in ['programa','data_exibicao','numero_programa','titulo_musica','autor','interprete','percentual_editora','valor_editora_brl','iswc','isrc'] if c in normed.columns and normed[c].notna().any()])
                })
            except Exception:
                continue
    # Summary
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / '_summary.csv', index=False)
    print(f"Wrote summary: {OUT / '_summary.csv'} ({len(summary)} sheets)")


if __name__ == '__main__':
    main()

