"""Reference composition for fresh foods, ingredients and prepared dishes."""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

FIELDS = ('energy_kcal_100', 'proteins_100', 'carbohydrates_100',
          'fat_100', 'fiber_100', 'sodium_100')
SOURCES = {
    'foundation': 'USDA FoodData Central — Foundation Foods (2026-10)',
    'legacy': 'USDA FoodData Central — SR Legacy (2018)',
    'survey': 'USDA FoodData Central — FNDDS 2021–2023',
    'cofid': 'Public Health England — McCance and Widdowson CoFID (2021)',
}
ALIASES = {
    'quinoa cozida': 'Quinoa, cooked',
    'mirtilo': 'Blueberries, raw',
    'mirtilos': 'Blueberries, raw',
    'mirtilo cru': 'Blueberries, raw',
    'edamame cozido': 'Edamame, cooked',
    'homus': 'Hummus, commercial',
    'homus industrializado': 'Hummus, commercial',
    'hummus': 'Hummus, commercial',
    'kimchi': 'Kimchi',
    'trigo bulgur cozido': 'Bulgur, cooked',
    'bulgur cozido': 'Bulgur, cooked',
    'queijo cottage simples': 'Cheese, cottage, plain',
    'pitaya': 'Dragon fruit',
    'framboesa': 'Raspberries, raw',
    'amora preta': 'Blackberries, raw',
    'tamara medjool': 'Dates, medjool',
    'semente de chia': 'Chia seeds, dry, raw',
    'chia': 'Chia seeds, dry, raw',
    'kefir': 'Kefir',
    'tempeh cozido': 'Tempeh, cooked',
    'tempe cozido': 'Tempeh, cooked',
    'cuscuz marroquino': 'Couscous, cooked',
    'cuscuz marroquino cozido': 'Couscous, cooked',
    'shitake cru': 'Mushrooms, shiitake, raw',
    'shiitake cru': 'Mushrooms, shiitake, raw',
    'shiitake seco': 'Mushrooms, shiitake, dried',
    'semente de abobora crua': 'Seeds, pumpkin seeds (pepitas), raw',
}
PREPARATIONS = {
    'cru': {'raw'}, 'crua': {'raw'}, 'cozido': {'boiled', 'cooked', 'steamed'},
    'cozida': {'boiled', 'cooked', 'steamed'}, 'frito': {'fried'}, 'frita': {'fried'},
    'grelhado': {'grilled', 'broiled'}, 'grelhada': {'grilled', 'broiled'},
    'assado': {'baked', 'roasted'}, 'assada': {'baked', 'roasted'},
    'seco': {'dry', 'dried'}, 'seca': {'dry', 'dried'},
    'defumado': {'smoked'}, 'defumada': {'smoked'},
}


def normalized(value):
    folded = unicodedata.normalize('NFKD', value.casefold())
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(c for c in folded if not unicodedata.combining(c))))


def key(value):
    return tuple(sorted(normalized(value).split()))


@lru_cache(maxsize=1)
def composition_index():
    file = Path(__file__).with_name('food_composition_extra.json')
    if not file.exists():
        file = Path(__file__).parent.parent / 'assets/data/food_composition_extra.json'
    data = json.loads(file.read_text(encoding='utf-8'))
    index = {}
    for dataset in SOURCES:
        for code, name, *values in data[dataset]:
            bucket = index.setdefault(key(name), {})
            bucket.setdefault(dataset, []).append((code, name, values))
    return index


def additional_food(original, hint=None):
    """Match all words within a source, allowing a reviewed alias or model translation."""
    name = normalized(original)
    if re.search(r'\b(?:sem |light|diet|zero|organico|vegano|vegetariano)', name) and not ALIASES.get(name):
        return None  # A generic entry can miss a material dietary qualifier.
    query = ALIASES.get(name) or hint or original
    tokens = set(normalized(query).split())
    for prep in set(name.split()) & PREPARATIONS.keys():
        if not tokens & PREPARATIONS[prep]:
            return None
    candidates = composition_index().get(key(query), {})
    for dataset in SOURCES:
        hits = candidates.get(dataset, [])
        if len(hits) != 1:
            continue
        code, label, values = hits[0]
        return {
            'code': f'cofid:{code}' if dataset == 'cofid' else f'fdc:{code}',
            'name': label, 'nutrients': dict(zip(FIELDS, values, strict=True)),
            'source': SOURCES[dataset],
            'url': ('https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid'
                    if dataset == 'cofid' else f'https://fdc.nal.usda.gov/food-details/{code}/nutrients'),
        }
    return None
