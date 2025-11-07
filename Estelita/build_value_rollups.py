#!/usr/bin/env python3
"""
Build consolidated CSVs of provider rows that have monetary values:
- Eligible_Value_Explicit_All_Providers.csv: rows from Explicit_Refs_Only with amount > 0
- Eligible_Value_Alias_All_Providers.csv: rows from Low Probability (alias) with amount > 0

Fast path: If Eligible_Explicit_All_Providers.csv exists, filter it by
VALOR A PAGAR - EDITORA > 0 to produce explicit values, avoiding XLSX parsing.
Fallback: parse eligible_with_refs.xlsx files directly.
"""

from pathlib import Path
import csv
import re
import zipfile
from xml.etree import ElementTree as ET
import pandas as pd

PROC = Path('Estelita/Processed')
FORN_ROOT = Path('/Users/igorcunha/SHRKVSCODE/Estelita/Raw/Fornecedores')

ns = {
    'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'rels': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
}

def letters_to_index(addr: str) -> int:
    col = 0
    for ch in addr:
        if 'A' <= ch <= 'Z':
            col = col * 26 + (ord(ch) - ord('A') + 1)
        else:
            break
    return col

def load_shared_strings(z: zipfile.ZipFile):
    try:
        data = z.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    root = ET.fromstring(data)
    out = []
    for si in root.findall('.//main:si', ns):
        text = []
        for t in si.findall('.//main:t', ns):
            text.append(t.text or '')
        out.append(''.join(text))
    return out

def get_sheets_map(z: zipfile.ZipFile):
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    ridmap = {rel.attrib.get('Id'): rel.attrib.get('Target') for rel in rels.findall('.//rels:Relationship', ns)}
    out = {}
    for s in wb.findall('.//main:sheets/main:sheet', ns):
        name = s.attrib.get('name')
        rid = s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        tgt = ridmap.get(rid)
        if tgt:
            out[name] = 'xl/' + tgt
    return out

def parse_currency_robust(value: str) -> float:
    s = str(value or '').strip()
    if not s:
        return 0.0
    # strip currency symbols
    s = s.replace('R$', '').replace('$', '').replace(' ', '')
    has_dot = '.' in s
    has_comma = ',' in s
    if has_dot and has_comma:
        last_sep = s[max(s.rfind('.'), s.rfind(','))]
        if last_sep == ',':
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
        return float(s)
    except Exception:
        return 0.0

def read_sheet_rows(z: zipfile.ZipFile, sheet_path: str, sst: list[list[str]]):
    sh = ET.fromstring(z.read(sheet_path))
    sheetdata = sh.find('.//main:sheetData', ns)
    if sheetdata is None:
        return [], []
    rows = sheetdata.findall('main:row', ns)
    if not rows:
        return [], []
    header_cells = rows[0].findall('main:c', ns)
    headers = {}
    max_idx = 0
    for c in header_cells:
        r = c.attrib.get('r', 'A1')
        col_letters = ''.join([ch for ch in r if ch.isalpha()])
        idx = letters_to_index(col_letters)
        t = c.attrib.get('t')
        v = c.find('main:v', ns)
        val = ''
        if v is not None:
            if t == 's':
                try:
                    val = sst[int(v.text)]
                except Exception:
                    val = ''
            else:
                val = v.text or ''
        headers[idx] = val
        if idx > max_idx: max_idx = idx
    header_list = [headers.get(i, '') for i in range(1, max_idx + 1)]
    data = []
    for row in rows[1:]:
        cells = {letters_to_index(''.join([ch for ch in c.attrib.get('r','') if ch.isalpha()])): c for c in row.findall('main:c', ns)}
        values = []
        for i in range(1, max_idx + 1):
            c = cells.get(i)
            if c is None:
                values.append(''); continue
            t = c.attrib.get('t')
            v = c.find('main:v', ns)
            if v is None:
                values.append(''); continue
            if t == 's':
                try:
                    values.append(sst[int(v.text)])
                except Exception:
                    values.append('')
            else:
                values.append(v.text or '')
        data.append(values)
    return header_list, data


def find_col(df: 'pd.DataFrame', candidates: list[str]) -> str | None:
    cols = list(df.columns)
    cn = [str(c).strip().lower() for c in cols]
    for opt in candidates:
        optn = opt.strip().lower()
        for i, x in enumerate(cn):
            if optn == x:
                return cols[i]
        for i, x in enumerate(cn):
            if optn in x:
                return cols[i]
    return None


def to_cents_series(series: 'pd.Series') -> 'pd.Series':
    def parse(v):
        s = str(v or '').strip()
        if not s:
            return 0
        s = s.replace('R$','').replace('$','')
        s = s.replace(' ', '')
        has_dot = '.' in s
        has_comma = ',' in s
        if has_dot and has_comma:
            last_sep = s[max(s.rfind('.'), s.rfind(','))]
            if last_sep == ',':
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
    return series.map(parse)


def classify_values_from_workbook(xlsx: Path, provider: str):
    explicit_with = []
    alias_with = []
    explicit_no = []
    alias_no = []
    try:
        xl = pd.ExcelFile(xlsx)
    except Exception:
        return explicit_out, alias_out
    for sheet in xl.sheet_names:
        try:
            df = xl.parse(sheet)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        # Identify columns
        col_unc = find_col(df, ['Uncertain Match','uncertain_match'])
        col_basis = find_col(df, ['Eligibility Basis','eligibility basis'])
        col_amt = find_col(df, ['VALOR A PAGAR - EDITORA','Valor (BRL)'])
        if col_amt is None:
            # Fallback: take the last column if present
            if df.shape[1] >= 1:
                col_amt = df.columns[-1]
            else:
                # no columns at all
                continue
        # Build amount_cents (default to 0 if conversion fails)
        if str(col_amt).strip().lower() == 'valor (brl)':
            cents = (pd.to_numeric(df[col_amt], errors='coerce').fillna(0.0)*100).round().astype(int)
        else:
            cents = to_cents_series(df[col_amt])
        # Determine class by sheet name preference (align with user's expectation)
        sname = str(sheet).strip().lower()
        is_explicit_sheet = sname == 'explicit_refs_only'
        is_alias_sheet = ('low probability' in sname) or ('alias' in sname)
        # Select useful columns
        keep_cols = [c for c in ['EDITORA','PROGRAMA','NÚMERO PROGRAMA','EXIBIÇÃO (GRAVADO OU REPRISE)','CATEGORIA DO PROGRAMA (PROGRAMA, NOVELA)','DATA DE EXIBIÇÃO','NOME DA MÚSICA','AUTOR','INTERPRETE','PERCENTUAL A PAGAR - EDITORA',col_amt] if c in df.columns]
        sub = df[keep_cols].copy()
        sub.insert(0, 'file_stem', xlsx.stem.replace('__eligible_with_refs',''))
        sub.insert(0, 'provider', provider)
        sub['amount_cents'] = cents
        sub['amount_int'] = (sub['amount_cents'].astype(int)/100.0).round().astype(int)
        # Classify rows by sheet first; if neither, fall back to uncertainty
        if is_explicit_sheet:
            e_with = sub[(sub['amount_cents']>0)]
            e_no = sub[(sub['amount_cents']<=0)]
            a_with = sub.iloc[0:0]
            a_no = sub.iloc[0:0]
        elif is_alias_sheet:
            a_with = sub[(sub['amount_cents']>0)]
            a_no = sub[(sub['amount_cents']<=0)]
            e_with = sub.iloc[0:0]
            e_no = sub.iloc[0:0]
        else:
            if col_unc and col_unc in df.columns:
                unc = df[col_unc].astype(str).str.strip().str.lower().map(lambda x: True if x=='true' else (False if x=='false' else True))
            elif col_basis and col_basis in df.columns:
                unc = df[col_basis].astype(str).str.contains('artist_alias|editora_alias', case=False, na=False)
            else:
                unc = pd.Series([True]*len(df))
            e_with = sub[(sub['amount_cents']>0) & (~unc)]
            a_with = sub[(sub['amount_cents']>0) & (unc)]
            e_no = sub[(sub['amount_cents']<=0) & (~unc)]
            a_no = sub[(sub['amount_cents']<=0) & (unc)]
        if not e_with.empty:
            explicit_with.append(e_with)
        if not a_with.empty:
            alias_with.append(a_with)
        if not e_no.empty:
            explicit_no.append(e_no)
        if not a_no.empty:
            alias_no.append(a_no)
    return explicit_with, alias_with, explicit_no, alias_no


def write_values_csv(path: Path, frames: list['pd.DataFrame']):
    if not frames:
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        return
    df = pd.concat(frames, ignore_index=True)
    if 'amount_cents' in df.columns and 'amount_numeric' not in df.columns:
        df['amount_numeric'] = (df['amount_cents'].astype(int)/100.0).map(lambda v: f"{v:.2f}")
    cols = ['provider','file_stem'] + [c for c in df.columns if c not in {'provider','file_stem'}]
    df[cols].to_csv(path, index=False)

def build_stem_provider_map():
    stem_to_provider = {}
    for p in FORN_ROOT.rglob('*'):
        if p.is_file() and p.suffix.lower() in ('.xlsx', '.xls'):
            stem_to_provider[p.stem] = p.parent.name
    # Also consult matches file if present (more robust)
    matches_csv = PROC / 'Supplier_Matches_All.csv'
    if matches_csv.exists():
        try:
            with open(matches_csv, 'r', encoding='utf-8', newline='') as f:
                r = csv.DictReader(f)
                for row in r:
                    fn = str(row.get('file') or '')
                    prov = str(row.get('provider') or '')
                    st = Path(fn).stem if fn else ''
                    if st and prov:
                        stem_to_provider[st] = prov
        except Exception:
            pass
    return stem_to_provider


def write_alias_values_from_xlsx(stem_to_provider, alias_rows):
    # Scan eligible workbooks for alias values
    for xlsx in PROC.glob('*__eligible_with_refs.xlsx'):
        stem = xlsx.stem.replace('__eligible_with_refs', '')
        provider = stem_to_provider.get(stem, '')
        try:
            with zipfile.ZipFile(xlsx, 'r') as z:
                sst = load_shared_strings(z)
                name_map = get_sheets_map(z)
                alias_sheet = 'Low Probability Matches SBT' if 'Low Probability Matches SBT' in name_map else ('Artist_Alias_Eligible' if 'Artist_Alias_Eligible' in name_map else None)
                if alias_sheet and alias_sheet in name_map:
                    header, data = read_sheet_rows(z, name_map[alias_sheet], sst)
                    if header and data:
                        try:
                            v_idx = header.index('Valor (BRL)')
                        except ValueError:
                            v_idx = header.index('VALOR A PAGAR - EDITORA') if 'VALOR A PAGAR - EDITORA' in header else -1
                        for r in data:
                            amount = 0.0
                            if v_idx >= 0 and v_idx < len(r):
                                v = r[v_idx]
                                try:
                                    amount = float(v)
                                except Exception:
                                    amount = parse_currency_robust(v)
                            if amount > 0:
                                alias_rows.append([provider, stem] + r + [f"{amount:.2f}"])
        except Exception:
            continue


def write_alias_values_csv(alias_rows):
    out2 = PROC / 'Eligible_Value_Alias_All_Providers.csv'
    if alias_rows:
        with open(out2, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            # best-effort header; depends on source sheet columns
            w.writerow(['provider','file_stem','title','artist','valor_text','Valor (BRL)','Valor (BRL, sem centavos)'])
            w.writerows(alias_rows)
    return out2


def main():
    stem_to_provider = build_stem_provider_map()
    exp_with = []
    ali_with = []
    exp_no = []
    ali_no = []
    for xlsx in PROC.glob('*__eligible_with_refs.xlsx'):
        stem = xlsx.stem.replace('__eligible_with_refs', '')
        provider = stem_to_provider.get(stem, '')
        e_w, a_w, e_n, a_n = classify_values_from_workbook(xlsx, provider)
        if e_w:
            exp_with.extend(e_w)
        if a_w:
            ali_with.extend(a_w)
        if e_n:
            exp_no.extend(e_n)
        if a_n:
            ali_no.extend(a_n)
    # With value
    write_values_csv(PROC / 'Eligible_Value_Explicit_All_Providers.csv', exp_with)
    write_values_csv(PROC / 'Eligible_Value_Alias_All_Providers.csv', ali_with)
    # Without value
    write_values_csv(PROC / 'Explicit_Without_Value_All_Providers.csv', exp_no)
    write_values_csv(PROC / 'Alias_Without_Value_All_Providers.csv', ali_no)

if __name__ == '__main__':
    main()
