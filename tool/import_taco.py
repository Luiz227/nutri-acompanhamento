"""Rebuild the offline catalogue from the unchanged official NEPA workbook.

Read-only spreadsheet processing. Requires openpyxl (authoring tool only).
No AI, network calls, nutrient inference or household-portion estimates.
"""
import hashlib
import json
import math
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tool/data/taco/taco_4ed.xlsx'
OUTPUT = ROOT / 'assets/data/taco_4ed.json'
EXPECTED_SHA256 = 'a66b8ec528daeabc63bc2b015fc9bd8c6d76b941c2fc0ed93a4311d449302d14'
WORKBOOK_URL = 'https://www.nepa.unicamp.br/arquivo/uploads/taco-4a-edicao/taco-4a-edicao-2/'
PUBLICATION_URL = 'https://nepa.unicamp.br/wp-content/uploads/sites/27/2023/10/taco_4_edicao_ampliada_e_revisada.pdf'

# Columns are zero-based, checked against the official workbook headers below.
COMPOSITION = {
    'energy_kcal_100': 3, 'proteins_100': 5, 'fat_100': 6,
    'cholesterol_100': 7, 'carbohydrates_100': 8, 'fiber_100': 9,
    'calcium_100': 11, 'magnesium_100': 12, 'phosphorus_100': 15,
    'iron_100': 16, 'sodium_100': 17, 'potassium_100': 18,
    'zinc_100': 20, 'vitamin_a_100': 23,  # RAE, not retinol or RE.
    'vitamin_b6_100': 26, 'niacin_100': 27, 'vitamin_c_100': 28,
}
FATS = {'saturated_fat_100': 2, 'monounsaturated_fat_100': 3, 'polyunsaturated_fat_100': 4}
UNREPORTED = ('sugars_100', 'trans_fat_100', 'vitamin_d_100', 'vitamin_b12_100')


def read_nutrient(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or value < 0:
            return None, {'status': 'invalid_source_value', 'raw': str(value)}
        return round(float(value), 6), None
    raw = '' if value is None else str(value).strip()
    status = {'': 'not_analysed', 'Tr': 'trace', 'NA': 'not_applicable', '*': 'under_review'}.get(raw, 'invalid_source_value')
    return None, {'status': status, 'raw': raw}


def main():
    checksum = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if checksum != EXPECTED_SHA256:
        raise ValueError('Source checksum changed: audit the new workbook before importing')
    workbook = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    try:
        composition = list(workbook.worksheets[0].values)
        fats = list(workbook.worksheets[1].values)
        for column, expected in {3: 'Energia', 5: 'Proteína', 6: 'Lipídeos', 7: 'Colesterol', 17: 'Sódio', 23: 'RAE', 26: 'Piridoxina'}.items():
            if str(composition[1][column]).strip() != expected:
                raise ValueError(f'Unexpected header at column {column}')
        fat_rows = {row[0]: (index, row) for index, row in enumerate(fats, 1)
                    if isinstance(row[0], int) and isinstance(row[1], str)}
        if len(fat_rows) != 423:
            raise ValueError('Unexpected fatty-acid row count')
        foods = []
        anomalies = []
        category = ''
        for row_number, row in enumerate(composition, 1):
            if isinstance(row[0], str) and row[1] is None and row_number > 3:
                category = row[0].strip()
            if not isinstance(row[0], int) or not isinstance(row[1], str):
                continue
            nutrients = {}
            statuses = {}
            for key, column in COMPOSITION.items():
                nutrients[key], status = read_nutrient(row[column])
                if status:
                    statuses[key] = status
                    if status['status'] == 'invalid_source_value':
                        anomalies.append({'food_id': row[0], 'row': row_number, 'column': column + 1, 'nutrient': key, 'raw': status['raw']})
            fat_row = fat_rows.get(row[0])
            for key, column in FATS.items():
                nutrients[key], status = read_nutrient(fat_row[1][column] if fat_row else None)
                if status:
                    statuses[key] = status
            # No total sugar, vitamin D/B12 or total trans-fat column exists.
            # Individual trans fatty acids are not a measured total.
            for key in UNREPORTED:
                nutrients[key] = None
                statuses[key] = {'status': 'not_reported', 'raw': ''}
            foods.append({
                'id': row[0], 'name': row[1].strip(), 'category': category,
                'usable_for_tracking': nutrients['energy_kcal_100'] is not None,
                'source_row': row_number, 'fat_source_row': fat_row[0] if fat_row else None,
                'nutrients': nutrients, 'nutrient_status': statuses,
            })
        if [food['id'] for food in foods] != list(range(1, 598)):
            raise ValueError('Food IDs must be unique and cover exactly 1–597')
        document = {
            'schema_version': 1, 'source': 'taco', 'edition': '4ª edição revisada e ampliada',
            'year': 2011, 'attribution': 'NEPA/UNICAMP. Tabela Brasileira de Composição de Alimentos — TACO. 4ª ed. Campinas, 2011.',
            'source_url': PUBLICATION_URL, 'workbook_url': WORKBOOK_URL,
            'source_sha256': checksum, 'basis': {'quantity': 100, 'unit': 'g', 'part': 'edible'},
            'units': {'energy': 'kcal', 'macronutrients': 'g', 'minerals': 'mg', 'vitamin_a': 'µg RAE', 'vitamin_c_b6_niacin': 'mg'},
            'permission': 'É permitida a reprodução parcial ou total desta obra, desde que citada a fonte.',
            'source_anomalies': anomalies, 'foods': foods,
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(json.dumps({'foods': len(foods), 'fatty_acid_rows': len(fat_rows), 'source_anomalies': anomalies}, ensure_ascii=False))
    finally:
        workbook.close()


if __name__ == '__main__':
    main()
