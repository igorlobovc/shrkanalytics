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
    s = s.replace('R$', '').replace(' ', '')
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

    # Explicit values (fast path from consolidated explicit CSV)
    explicit_in = PROC / 'Eligible_Explicit_All_Providers.csv'
    explicit_out = PROC / 'Eligible_Value_Explicit_All_Providers.csv'
    if explicit_in.exists():
        try:
            with open(explicit_in, 'r', encoding='utf-8', newline='') as inf, \
                 open(explicit_out, 'w', encoding='utf-8', newline='') as outf:
                rin = csv.DictReader(inf)
                cols = rin.fieldnames or []
                # Keep a useful subset + numeric amount; avoid duplicates
                base_keep = ['provider','file_stem']
                rest = [c for c in cols if c not in {'__title_norm','__author_norm','__is_match','__sheet'} and c not in base_keep]
                keep = base_keep + rest
                w = csv.DictWriter(outf, fieldnames=keep + ['amount_numeric'])
                w.writeheader()
                for row in rin:
                    amt = parse_currency_robust(row.get('VALOR A PAGAR - EDITORA',''))
                    if amt > 0:
                        out = {k: row.get(k, '') for k in keep}
                        out['amount_numeric'] = f"{amt:.2f}"
                        w.writerow(out)
        except Exception:
            pass

    # Alias values
    alias_rows: list[list[str]] = []
    # Prefer existing consolidated alias file; if absent, derive from xlsx
    alias_in = PROC / 'Eligible_Value_Alias_All_Providers.csv'
    if not alias_in.exists():
        write_alias_values_from_xlsx(stem_to_provider, alias_rows)
        write_alias_values_csv(alias_rows)

if __name__ == '__main__':
    main()
