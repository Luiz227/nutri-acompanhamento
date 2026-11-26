"""Exact Portuguese food and household measure matches from IBGE POF."""
from functools import lru_cache
import json
import os
from pathlib import Path
import re

from food_composition import FIELDS, normalized

SOURCE = 'IBGE — POF 2008–2009'
SOURCE_URL = 'https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2008_2009/'
COMPOSITION_URL = SOURCE_URL + 'Tabelas_de_Composicao_Nutricional_dos_Alimentos_Consumidos_no_Brasil/'
MEASURES_URL = SOURCE_URL + 'Tabela_de_Medidas_Referidas_para_os_Alimentos_Consumidos_no_Brasil/'
UNIT_LABELS = {
    'unit': ('unidade', 'unidades'), 'slice': ('fatia', 'fatias'),
    'ladle': ('concha', 'conchas'), 'tablespoon': ('colher de sopa', 'colheres de sopa'),
    'servingSpoon': ('colher de servir', 'colheres de servir'), 'cup': ('xícara', 'xícaras'),
}
MEASURE_NAMES = {
    'unidade': 'unit', 'fatia': 'slice', 'concha': 'ladle', 'colher de sopa': 'tablespoon',
    'colher de arroz servir': 'servingSpoon', 'xicara de cha': 'cup', 'xicara': 'cup',
}
PREPARATIONS = {
    1: ('cru', 'crua'), 2: ('cozido', 'cozida'), 3: ('grelhado', 'grelhada'),
    4: ('assado', 'assada'), 5: ('frito', 'frita'), 6: ('empanado', 'empanada', 'a milanesa'),
    7: ('refogado', 'refogada'), 13: ('ensopado', 'ensopada'),
}
ALIASES = {
    'feijoada tradicional': 'feijoada', 'feijoada com carne': 'feijoada',
    'feijoada caseira': 'feijoada', 'coxinha de frango': 'coxinha',
    'coxinha de galinha': 'coxinha',
    'baiao de 2': 'baiao de dois',
    'arroz de carreteiro': 'arroz carreteiro',
    'feijao a tropeira': 'feijao tropeiro',
    'feijao tropeiro mineiro': 'feijao tropeiro',
    'moqueca de peixe baiana': 'moqueca baiana',
    'moqueca baiana de peixe': 'moqueca baiana',
    'moqueca de peixe capixaba': 'moqueca capixaba',
    'moqueca capixaba de peixe': 'moqueca capixaba',
    'arroz com galinha': 'galinhada',
    'cuscuz a paulista': 'cuscuz paulista',
    'angu de fuba': 'angu de milho',
    'acaraje baiano': 'acaraje',
    'vatapa baiano': 'vatapa',
    'estrogonofe': 'strogonoff',
    'strogonofe': 'strogonoff',
}
# The IBGE composition references a beef croquette and wheat couscous for these.
INCOMPATIBLE_COMPOSITION = {8500205, 6902901}
SIZE_WORDS = {'small': r'pequen[oa]', 'medium': r'medi[oa]', 'large': r'grand[ea]'}
FILL_WORDS = {'full': r'chei[oa]', 'level': r'ras[oa]'}


@lru_cache(maxsize=1)
def catalogue():
    configured = os.environ.get('FOOD_POF_PATH')
    path = Path(configured) if configured else Path(__file__).with_name('food_pof.json')
    if not configured and not path.exists():
        return {}, {}
    data = json.loads(path.read_text(encoding='utf-8'))
    foods, portions = {}, {}
    for code, prep, name, preparation, *values in data['foods']:
        label = name if prep == 99 else f'{name} — {preparation}'
        entry = (code, prep, label, values)
        base = normalized(name)
        if prep == 99:
            foods.setdefault(base, []).append(entry)
        for word in PREPARATIONS.get(prep, ()):
            foods.setdefault(f'{base} {word}', []).append(entry)
    for code, prep, measure, grams, reference in data['portions']:
        unit = MEASURE_NAMES.get(normalized(measure))
        if unit:
            portions.setdefault((code, prep, unit), []).append((grams, reference))
    return foods, portions


def exact_entry(text):
    name = normalized(text)
    name = ALIASES.get(name, name)
    foods = catalogue()[0]
    hits = foods.get(name, ())
    if not hits:
        # Reordering the same fully specified words is safe; ingredients and
        # preparation remain mandatory. Never choose by a shared first word.
        words = sorted(name.split())
        hits = [entry for label, entries in foods.items() if sorted(label.split()) == words for entry in entries]
        hits = list({(entry[0],entry[1]):entry for entry in hits}.values())
    return hits[0] if len(hits) == 1 else None


def pof_food(text):
    entry = exact_entry(text)
    if not entry or entry[0] in INCOMPATIBLE_COMPOSITION:
        return None
    code, prep, name, values = entry
    if any(value is None for value in values[:4]):
        return None
    return {'code': f'pof:{code}:{prep}', 'name': name.capitalize(),
            'nutrients': dict(zip(FIELDS, values, strict=True)),
            'source': SOURCE, 'url': COMPOSITION_URL}


def pof_portion(text, unit, size, fill=None):
    entry = exact_entry(text)
    if not entry or size not in tuple(SIZE_WORDS) or fill not in (None, 'full', 'level'):
        return None
    code, prep, *_ = entry
    choices = {}
    for grams, reference in catalogue()[1].get((code, prep, unit), ()):
        description = normalized(reference)
        sizes = [k for k, pattern in SIZE_WORDS.items() if re.search(rf'\b{pattern}\b', description)]
        if size not in (sizes or ['medium']):
            continue
        if fill and not re.search(rf'\b{FILL_WORDS[fill]}\b', description):
            continue
        choices[grams] = reference
    if len(choices) == 1:
        grams, reference = next(iter(choices.items()))
        return {'grams': grams, 'reference': reference, 'unit': unit, 'size': size,
                'source': f'{SOURCE}, medidas referidas', 'url': MEASURES_URL}
    return None
