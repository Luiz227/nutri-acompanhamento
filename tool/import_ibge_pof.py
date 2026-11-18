"""Build the server's POF catalogue from the official IBGE ZIP archives."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

import xlrd

BASE = ('https://ftp.ibge.gov.br/Orcamentos_Familiares/'
        'Pesquisa_de_Orcamentos_Familiares_2008_2009/')
COMPOSITION = BASE + 'Tabelas_de_Composicao_Nutricional_dos_Alimentos_Consumidos_no_Brasil/'
MEASURES = BASE + 'Tabela_de_Medidas_Referidas_para_os_Alimentos_Consumidos_no_Brasil/'


def read_rows(path, url, sha256, member, columns):
    if path:
        data = path.read_bytes()
    else:
        with urlopen(url, timeout=40) as response:
            data = response.read(2_000_000)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f'Arquivo IBGE diferente da edição esperada: {member}')
    with ZipFile(io.BytesIO(data)) as archive:
        sheet = xlrd.open_workbook(file_contents=archive.read(member)).sheet_by_index(0)
    if sheet.ncols != columns:
        raise ValueError(f'Formato inesperado: {member}')
    return (sheet.row_values(i) for i in range(4, sheet.nrows))


def number(value):
    return round(value, 5) if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--composition', type=Path)
    parser.add_argument('--measures', type=Path)
    args = parser.parse_args()
    composition = read_rows(args.composition, COMPOSITION + 'tabelacompleta.zip',
                            '3aa01426f16f8041ce830de2dda7e5003806b437917cb829f8cefe84a0ac21e0',
                            'tabelacompleta.xls', 43)
    measures = read_rows(args.measures, MEASURES + 'tabelamedidas_bd.zip',
                         '3d0ff06acf0b55c22a621f57e6fb218d4505af204ed2be1571bfbe02fbab17c9',
                         'tabelamedidas_bd.xls', 11)
    foods = []
    for row in composition:
        if not isinstance(row[0], (float, int)):
            continue
        values = [number(row[i]) for i in (6, 7, 9, 8, 10, 16)]
        foods.append([int(row[0]), int(row[2]), row[1].strip(), row[3].strip(), *values])
    portions = []
    for row in measures:
        grams = number(row[8])
        if isinstance(row[0], (float, int)) and grams:
            portions.append([int(row[0]), int(row[2]), row[5].strip(), grams, row[10].strip()])
    if len(foods) < 1900 or len(portions) < 11000:
        raise ValueError(f'Catálogo POF incompleto: {len(foods)} fichas, {len(portions)} medidas')
    args.output.write_text(json.dumps({'foods': foods, 'portions': portions}, ensure_ascii=False,
                                      separators=(',', ':')), encoding='utf-8')
    print(f'POF: {len(foods)} fichas nutricionais e {len(portions)} medidas.')


if __name__ == '__main__':
    main()
