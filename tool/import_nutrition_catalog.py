"""Build the compact nutrition catalog from official downloadable data.

Usage: python tool/import_nutrition_catalog.py SOURCE_DIR OUTPUT_JSON
SOURCE_DIR contains usda-{foundation,legacy,survey}.zip and cofid-2021.xlsx.
The CoFID import uses openpyxl; the deployed server needs only the JSON.
"""
import csv
import io
import json
import math
import sys
from pathlib import Path
from zipfile import ZipFile

# Energy (kcal), protein, total carbohydrate, fat, fiber and sodium.
USDA = ((1008, 2047, 2048), (1003,), (1005,), (1004,), (1079,), (1093,))
IDS = {i for group in USDA for i in group}


def number(value):
    if value == 'Tr':
        return 0
    try:
        value = float(value)
        return round(value, 6) if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def usable(row):
    _, name, kcal, protein, carbs, fat, _, _ = row
    return (name and all(v is not None for v in (kcal, protein, carbs, fat))
            and kcal <= 950 and protein + carbs + fat <= 110)


def nutrient_values(values):
    return [next((values[i] for i in group if values.get(i) is not None), None) for group in USDA]


def usda_json(file):
    with ZipFile(file) as archive:
        with archive.open(next(name for name in archive.namelist() if name.endswith('.json'))) as entry:
            foods, = json.load(entry).values()
    for food in foods:
        values = {}
        for item in food['foodNutrients']:
            n = item['nutrient']['id']
            if n in IDS and item.get('amount') is not None:
                values.setdefault(n, number(item['amount']))
        yield [food['fdcId'], food['description'], *nutrient_values(values)]


def csv_rows(archive, name):
    with archive.open(next(p for p in archive.namelist() if p.endswith('/' + name))) as entry:
        yield from csv.DictReader(io.TextIOWrapper(entry, encoding='utf-8-sig'))


def usda_legacy(file):
    with ZipFile(file) as archive:
        by_food = {}
        for item in csv_rows(archive, 'food_nutrient.csv'):
            n = int(item['nutrient_id'])
            if n in IDS:
                by_food.setdefault(item['fdc_id'], {}).setdefault(n, number(item['amount']))
        for food in csv_rows(archive, 'food.csv'):
            fid = food['fdc_id']
            yield [int(fid), food['description'], *nutrient_values(by_food.get(fid, {}))]


def cofid(file):
    from openpyxl import load_workbook
    book = load_workbook(file, read_only=True, data_only=True)
    try:
        sodium = {row[0]: number(row[7]) for row in book['1.4 Inorganics'].iter_rows(min_row=4, values_only=True)}
        sheet = book['1.3 Proximates']
        _, codes = sheet.iter_rows(max_row=2, values_only=True)
        fiber_index = codes.index('AOACFIB')
        for row in sheet.iter_rows(min_row=4, values_only=True):
            code, name = row[:2]
            if not code or not name or str(row[3]).startswith('Q'):
                continue  # Alcoholic drinks are per 100 ml, not per 100 g.
            fiber = number(row[fiber_index])
            # CoFID's CHO is available carbohydrate; harmonize with the total
            # carbohydrate convention used by the diary when AOAC fiber exists.
            carbs = number(row[11])
            carbs = round(carbs + fiber, 6) if carbs is not None and fiber is not None else None
            yield [code, name, number(row[12]), number(row[9]), carbs, number(row[10]), fiber, sodium.get(code)]
    finally:
        book.close()


def main():
    source, destination = map(Path, sys.argv[1:])
    records = {
        'foundation': usda_json(source / 'usda-foundation.zip'),
        'survey': usda_json(source / 'usda-survey.zip'),
        'legacy': usda_legacy(source / 'usda-legacy.zip'),
        'cofid': cofid(source / 'cofid-2021.xlsx'),
    }
    output = {key: [row for row in data if usable(row)] for key, data in records.items()}
    destination.write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print({key: len(data) for key, data in output.items()})


if __name__ == '__main__':
    main()
