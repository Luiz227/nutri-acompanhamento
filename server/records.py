"""Validated patient records. AI proposes; the server validates and saves."""
import json
import math
import re
import time
import unicodedata
import uuid
import difflib
import random
from nutrition_sources import ProductSource
from food_composition import additional_food
from pof import UNIT_LABELS, pof_food
from portions import portion
from menu_foods import menu_options, resolve_menu
from photo_meals import clean_food_name
from datetime import datetime, timezone, timedelta
from pathlib import Path


def normalized(text):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if not unicodedata.combining(c))).strip()


def sandwich_records(text):
    """Recover an explicitly described single sandwich from a grouped proposal."""
    name = normalized(text)
    match = re.fullmatch(
        r'(?:eu )?(?:comi|foi) (?:um|1) pao(?: frances)? com '
        r'(?:(?:uma|1) fatia de )?presunto e (?:(?:uma|1) (?:fatia )?de )?queijo'
        r'(?: (?:esse foi|foi|no) (?:o )?(?:meu )?cafe da manha| no cafe da manha)',
        name,
    )
    if not match:
        return None
    return [
        dict(kind='meal', text=food, unit=unit, quantity=1, mealType='breakfast')
        for food, unit in (('Pão francês', 'unit'), ('Presunto', 'slice'), ('Queijo', 'slice'))
    ]


# Explicit synonyms only: never infer fat content, preparation, or bread type.
FOOD_ALIASES = {
    'arroz branco': 'Arroz, tipo 1, cozido',
    'arroz branco cozido': 'Arroz, tipo 1, cozido',
    'arroz cozido': 'Arroz, tipo 1, cozido',
    'batata frita': 'Batata, inglesa, frita',
    'batata fritas': 'Batata, inglesa, frita',
    'batatas fritas': 'Batata, inglesa, frita',
    'cenoura cozida': 'Cenoura, cozida',
    'brocolis cozido': 'Brócolis, cozido',
    'molho de tomate': 'Tomate, molho industrializado',
    'mussarela': 'Queijo, mozarela',
    'mucarela': 'Queijo, mozarela',
    'mozarela': 'Queijo, mozarela',
    'queijo mussarela': 'Queijo, mozarela',
    'queijo mucarela': 'Queijo, mozarela',
    'pao de forma integral': 'Pão, trigo, forma, integral',
    'pao frances': 'Pão, trigo, francês',
    'presunto com capa de gordura': 'Presunto, com capa de gordura',
    'presunto sem capa de gordura': 'Presunto, sem capa de gordura',
    'peito de frango sem pele grelhado': 'Frango, peito, sem pele, grelhado',
    'file de peito de frango sem pele grelhado': 'Frango, peito, sem pele, grelhado',
    'peito de frango sem pele cozido': 'Frango, peito, sem pele, cozido',
    'peito de frango sem pele cru': 'Frango, peito, sem pele, cru',
}

MEAL_LABELS = {'breakfast': 'Café da manhã', 'lunch': 'Almoço', 'dinner': 'Jantar', 'snack': 'Lanche'}
NUTRIENTS = {'energyKcal': 'energy_kcal_100', 'proteinG': 'proteins_100',
             'carbsG': 'carbohydrates_100', 'fatG': 'fat_100', 'fiberG': 'fiber_100', 'sodiumMg': 'sodium_100'}


def nutrition_line(values):
    labels = {'energyKcal': ('kcal', ''), 'proteinG': ('g', 'proteínas '),
              'carbsG': ('g', 'carboidratos '), 'fatG': ('g', 'gorduras '),
              'fiberG': ('g', 'fibras '), 'sodiumMg': ('mg', 'sódio ')}
    return '; '.join(prefix + (f'{values[key]:.1f}'.replace('.', ',') + ' ' + unit if values.get(key) is not None else 'não informado')
                     for key, (unit, prefix) in labels.items())


def catalogue():
    file = Path(__file__).with_name('taco_4ed.json')
    if not file.exists():
        file = Path(__file__).parent.parent / 'assets/data/taco_4ed.json'
    return [r for r in json.loads(file.read_text(encoding='utf-8'))['foods'] if r['usable_for_tracking']]


def validate_record(raw):
    if not isinstance(raw, dict) or raw.get('kind') not in ('meal', 'water', 'weight', 'observation'):
        raise ValueError('Tipo de registro inválido.')
    text = raw.get('text')
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 600:
        raise ValueError('Descrição obrigatória (até 600 caracteres).')
    result = {'kind': raw['kind'], 'text': text.strip()}
    query = raw.get('catalogueQuery')
    if raw['kind'] == 'meal' and isinstance(query, str) and 1 <= len(query.strip()) <= 180:
        result['catalogueQuery'] = query.strip()
    if raw.get('barcode') is not None:
        if not isinstance(raw['barcode'], str) or not re.fullmatch(r'\d{8,14}', raw['barcode']):
            raise ValueError('Código de barras inválido.')
        result['barcode'] = raw['barcode']
    if raw['kind'] == 'meal' and raw.get('mealType') is not None:
        if raw['mealType'] not in MEAL_LABELS:
            raise ValueError('Informe café da manhã, almoço, jantar ou lanche.')
        result['mealType'] = raw['mealType']
    if raw['kind'] != 'observation':
        amount, unit = raw.get('quantity'), raw.get('unit')
        if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not math.isfinite(amount) or amount <= 0:
            raise ValueError('Confirme a quantidade e a unidade antes de registrar.')
        if raw['kind'] == 'meal' and unit in tuple(UNIT_LABELS):
            measure = portion(text, unit, raw.get('portionSize', 'medium'), raw.get('portionFill'))
            if not measure or amount > 30:
                raise ValueError('Para esse alimento ainda não tenho uma medida média confiável. Você consegue dizer o tamanho ou uma quantidade aproximada em gramas?')
            result.update(estimated=True, portionCount=amount, portionReference=measure,
                          estimateSource='household')
            amount *= measure['grams']
            unit = 'g'
        if raw['kind'] == 'meal' and raw.get('estimateSource') == 'photo':
            result.update(estimated=True, estimateSource='photo')
        units = {'meal': {'g': 1}, 'water': {'ml': 1, 'l': 1000}, 'weight': {'kg': 1, 'g': .001}}
        if unit not in units[raw['kind']]:
            raise ValueError('Refeições precisam de gramas, água de ml/l e peso de kg/g.')
        amount *= units[raw['kind']][unit]
        limit = {'meal': 10000, 'water': 20000, 'weight': 600}[raw['kind']]
        if amount > limit:
            raise ValueError('Quantidade fora do limite de um registro; confirme o valor.')
        result.update(quantity=round(amount, 6), unit={'meal': 'g', 'water': 'ml', 'weight': 'kg'}[raw['kind']])
        if raw['kind'] == 'meal':
            prefix = re.match(r'^\s*(\d+(?:[.,]\d+)?)\s*(?:gramas?|g)\b\s*(?:de\s+)?', result['text'], re.I)
            if prefix:
                if abs(float(prefix.group(1).replace(',', '.')) - amount) > .000001:
                    raise ValueError('A quantidade na descrição não coincide com a porção.')
                result['text'] = result['text'][prefix.end():].strip()
                if not result['text']:
                    raise ValueError('Informe o nome do alimento.')
    if raw.get('estimateSource') == 'photo':
        result.update(estimateSource='photo',estimated=True)
        if raw.get('visualConfidence') in ('high','medium','low'):
            result['visualConfidence']=raw['visualConfidence']
        if raw.get('mealTypeSource') in ('time','explicit'):
            result['mealTypeSource']=raw['mealTypeSource']
    date = raw.get('occurredAt')
    if date:
        if not isinstance(date, str):
            raise ValueError('Data inválida.')
        when = datetime.fromisoformat(date.replace('Z', '+00:00'))
        if when.tzinfo is None or not time.time() - 366 * 86400 <= when.timestamp() <= time.time() + 300:
            raise ValueError('Data inválida ou futura. Confirme a data.')
    else:
        when = datetime.now(timezone.utc)
    result['occurredAt'] = when.astimezone(timezone.utc).isoformat()
    return result


class Records:
    def __init__(self, db):
        self.db = db
        self.foods = catalogue()
        self.products = ProductSource(db)
        db.executescript('''CREATE TABLE IF NOT EXISTS records (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
          patient_id TEXT NOT NULL REFERENCES patients(id), event_id TEXT UNIQUE NOT NULL,
          payload TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, confirmed REAL);
          CREATE INDEX IF NOT EXISTS records_owner ON records(patient_id,seq);
          CREATE TABLE IF NOT EXISTS record_original_cursors (
            record_id TEXT PRIMARY KEY, original_seq INTEGER NOT NULL
          );''')

    def menu_options(self):
        return menu_options(self.foods)

    def enrich_menu(self, records, auto_save=False):
        resolve_menu(records, self.foods)

    def candidates(self, text):
        query = normalized(text)
        tokens = {t for t in query.split() if len(t) >= 3 and t not in ('com', 'uma', 'meu', 'hoje', 'mais')}
        aliases = {normalized(name) for alias, name in FOOD_ALIASES.items()
                   if f' {alias} ' in f' {query} '}
        scored = [(sum(t in normalized(f['name']).split() for t in tokens)
                   + (10 if normalized(f['name']) in aliases else 0)
                   + (3 if 'frango' in tokens and ('file' in tokens or 'peito' in tokens)
                      and normalized(f['name']).startswith('frango peito ') else 0), f) for f in self.foods]
        return [{'name': f['name']} for score, f in sorted(scored, key=lambda pair: -pair[0]) if score > 0][:12]

    def reviewed(self, text):
        name=clean_food_name(text)
        defaults = {'mandioca': 'Mandioca, cozida', 'presunto': 'Presunto, sem capa de gordura',
                    'queijo': 'Queijo, prato', 'farofa': 'Mandioca, farofa, temperada',
                    'farofa de mandioca': 'Mandioca, farofa, temperada',
                    'linguica frita': 'Lingüiça, porco, frita'}
        canonical = defaults.get(name) or FOOD_ALIASES.get(name)
        if name in ('feijoada', 'feijoada tradicional', 'feijoada com carne'):
            # Representative recipe, not a measured plate or the TBCA recipe.
            composition = {'Feijão, preto, cozido': .70, 'Porco, costela, assada': .15,
                           'Lingüiça, porco, frita': .10, 'Toucinho, frito': .05}
            foods = [(food, composition[food['name']]) for food in self.foods if food['name'] in composition]
            if len(foods) != len(composition):
                return None
            columns = ('energy_kcal_100','proteins_100','carbohydrates_100','fat_100','fiber_100','sodium_100')
            nutrients = {
                key: sum(food['nutrients'][key] * fraction for food, fraction in foods)
                if all(isinstance(food['nutrients'].get(key),(int,float)) for food, _ in foods) else None
                for key in columns
            }
            return {'code':'recipe:feijoada-taco', 'name':'Feijoada tradicional (receita de referência)',
                    'nutrients':nutrients, 'source':'Receita estimada com ingredientes da TACO/NEPA/UNICAMP (2011)',
                    'referenceIds':[food['id'] for food, _ in foods]}
        if canonical:
            return next((f for f in self.foods if normalized(f['name'])==normalized(canonical)),None)
        words=set(name.split())
        incompatible=words & {'milanesa','empanado','empanada','frango','suino','suina','porco','vegetal','soja','hamburguer','figado'}
        if not incompatible and ('bife' in words or {'carne','bovina'} <= words) and words & {'grelhado','grelhada'}:
            # Unknown cut: a transparent, derived reference across common cuts,
            # never claim the photo identified a specific cut or exact fat content.
            ids={344,346,358,368,370,377}
            cuts=words & {'picanha','patinho','alcatra','maminha','costela','acem','cupim','mignon','contra'}
            foods=[f for f in self.foods if f['id'] in ids and all(isinstance(f['nutrients'].get(k),(int,float)) for k in ('energy_kcal_100','proteins_100','fat_100','carbohydrates_100'))]
            if cuts:foods=[f for f in foods if cuts <= set(normalized(f['name']).split())]
            if not foods:return None
            columns=set().union(*(f['nutrients'] for f in foods))
            values={k:sum(f['nutrients'][k] for f in foods)/len(foods) if all(isinstance(f['nutrients'].get(k),(int,float)) for f in foods) else None for k in columns}
            return {'code':'taco-estimate:beef-grilled','name':'Carne bovina grelhada (referência média)',
                    'nutrients':values,'source':'Estimativa derivada da TACO/NEPA/UNICAMP (2011)',
                    'referenceIds':[f['id'] for f in foods]}
        return None

    def closest(self, text):
        reviewed=self.reviewed(text)
        if reviewed:return reviewed
        query = clean_food_name(text)
        stop = {'de', 'do', 'da', 'com', 'sem', 'um', 'uma', 'tipo', 'comum'}
        words = set(query.split()) - stop
        if 'frango' in words and not words & {'cru','crua','cozido','cozida','grelhado','grelhada','assado','assada','frito','frita','milanesa'}:
            return None
        candidates = []
        for food in self.foods:
            name = normalized(food['name'])
            tokens = set(name.split()) - stop
            # Only compare within the same named food family.
            family = name.split()[0]
            if family not in words:
                continue
            if (tokens & {'carreteiro','milanesa','risoto','recheado','recheada','bolonhesa','queijo','chocolate','bacon','toucinho','linguica'}) - words:
                continue
            if (words & {'doce','carreteiro','parboilizado'}) - tokens:
                continue
            if 'integral' not in words and 'integral' in tokens:
                continue
            if 'comum' in query and tokens & {'aveia', 'soja', 'milho', 'gluten'}:
                continue
            if 'sem pele' in query and 'com pele' in name or 'sem gordura' in query and 'com capa' in name:
                continue
            incompatible = False
            for group in ({'cru','crua'}, {'cozido','cozida'}, {'grelhado','grelhada'}, {'assado','assada'}, {'frito','frita'}, {'milanesa'}, {'integral'}, {'recheado','recheada'}):
                if words & group and not tokens & group:
                    incompatible = True
            if incompatible:
                continue
            # A dietary qualifier is not interchangeable with an ordinary variant.
            if any(q in words and q not in tokens for q in ('soja', 'amendoas', 'amendoa', 'aveia', 'coco', 'vegetal', 'vegano', 'vegetariano', 'desnatado', 'light', 'diet')):
                continue
            if 'sem lactose' in query and 'sem lactose' not in name:
                continue
            score = len(words & tokens) / max(1, len(words)) + .25 * difflib.SequenceMatcher(None, query, name).ratio()
            candidates.append((score, food))
        candidates.sort(key=lambda pair: -pair[0])
        return candidates[0][1] if candidates and candidates[0][0] >= .55 else None

    def automatic_reply(self, records):
        if any(r.get('estimateSource')=='photo' for r in records):
            return self.photo_reply(records)
        paragraphs = []
        introductions = ('Anotei', 'Registrei', 'Já deixei salvo')
        for record in records:
            if record['kind'] == 'water':
                paragraphs.append(f"{random.choice(introductions)} {record['quantity']:g} ml de água no seu diário. 💧")
            elif record['kind'] == 'meal':
                label = MEAL_LABELS.get(record.get('mealType'), 'refeição').lower()
                if record.get('estimateSource') == 'household':
                    measure = UNIT_LABELS[record['portionReference']['unit']][record['portionCount'] != 1]
                    paragraphs.append(f"{random.choice(introductions)} no {label}: {record['portionCount']:g} {measure} de {record['text']}. Considerei aproximadamente {record['quantity']:g} g pela medida média.")
                elif record.get('estimateSource') == 'photo':
                    paragraphs.append(f"Pela foto, anotei no {label} aproximadamente {record['quantity']:g} g de {record['text']}. O peso foi estimado pela imagem.")
                else:
                    paragraphs.append(f"{random.choice(introductions)} no {label}: {record['quantity']:g} g de {record['text']}.")
                if 'nutrition' in record:
                    n = record['nutrition']
                    def value(key, unit):
                        return f"{n[key]:.1f}".replace('.', ',') + ' ' + unit if n.get(key) is not None else 'valor não disponível'
                    prefix = 'Para essa porção, estimei ' if record.get('estimated') else 'Essa porção tem cerca de '
                    paragraphs.append(prefix + f"{value('energyKcal','kcal')}, com {value('proteinG','g de proteína')}, {value('carbsG','g de carboidratos')} e {value('fatG','g de gordura')}.")
                else:
                    paragraphs.append('Guardei como anotação, mas ainda não tenho uma referência nutricional compatível. Se for um produto de mercado, pode mandar o código de barras para eu consultar o rótulo.')
            elif record['kind'] == 'weight':
                paragraphs.append(f"Anotei seu peso de {record['quantity']:g} kg.")
            else:
                paragraphs.append('Deixei sua observação salva no diário.')
        meals = [r for r in records if r['kind'] == 'meal']
        known = [r for r in meals if 'nutrition' in r]
        if len(meals) > 1 and known:
            keys = [('energyKcal','kcal'), ('proteinG','g de proteína'), ('carbsG','g de carboidratos'), ('fatG','g de gordura')]
            values = []
            for key, unit in keys:
                values.append((f"{sum(r['nutrition'][key] for r in known):.1f}".replace('.', ',') + ' ' + unit) if all(r['nutrition'][key] is not None for r in known) else 'valor não disponível')
            paragraphs.append(('No total da refeição' if len(known) == len(meals) else 'Somando apenas os alimentos identificados') + ': ' + ', '.join(values) + '.')
        # Keep the WhatsApp payload bounded without truncating saved food data.
        message = '\n\n'.join(paragraphs)
        if len(message) > 1800:
            compact = [p for p in paragraphs if not p.startswith(('Essa porção tem', 'Para essa porção, estimei'))]
            message = '\n\n'.join(compact)
        if len(message) > 1800:
            raise ValueError('Envie até três alimentos por mensagem para eu organizar os detalhes.')
        return message

    def photo_reply(self, records):
        meals=[r for r in records if r['kind']=='meal']
        known=[r for r in meals if 'nutrition' in r]
        unknown=[r for r in records if 'nutrition' not in r and (r['kind']=='meal' or r.get('visualConfidence')=='low')]
        label=MEAL_LABELS.get(next((r.get('mealType') for r in meals),None),'refeição').lower()
        paragraphs=[f'Registrei seu {label}. As porções e os valores abaixo são estimados pela foto.'] if known else []
        def value(number):return f'{number:.1f}'.replace('.',',')
        for r in known:
            n=r['nutrition'];name=r['text'][:55].rstrip()
            def fmt(k):return value(n[k]) if n.get(k) is not None else 'não disponível'
            paragraphs.append(f"{name.capitalize()} ({r['quantity']:g} g): {fmt('energyKcal')} kcal.\nProteína: {fmt('proteinG')} g | Carboidratos: {fmt('carbsG')} g | Gordura: {fmt('fatG')} g.")
        if len(known)>1 or (known and unknown):
            sums={k:sum(r['nutrition'][k] for r in known) if all(r['nutrition'].get(k) is not None for r in known) else None for k in ('energyKcal','proteinG','carbsG','fatG')}
            def total(k):return value(sums[k]) if sums[k] is not None else 'não disponível'
            title='Subtotal estimado dos alimentos identificados' if unknown else 'Total estimado'
            paragraphs.append(f"{title}: {total('energyKcal')} kcal.\nProteína: {total('proteinG')} g | Carboidratos: {total('carbsG')} g | Gordura: {total('fatG')} g.")
        if unknown:
            names=', '.join(r['text'][:40] for r in unknown[:4])
            paragraphs.append(f'Não incluí {names} no cálculo porque não foi possível identificar com segurança.' if known else 'Não consegui identificar esta refeição com segurança. Pode enviar outra foto mais nítida, mostrando o prato inteiro?')
        message='\n\n'.join(paragraphs)
        if len(message)>1800:
            # Keep individual food/energy bubbles; total retains all four macros.
            paragraphs=[p.split('\nProteína:')[0] if i and i<=len(known) else p for i,p in enumerate(paragraphs)]
            message='\n\n'.join(paragraphs)
        if len(message)>1800:raise ValueError('Muitos detalhes na imagem.')
        return message

    def enrich_meals(self, records, auto_save):
        for record in records:
            if record['kind'] == 'meal':
                # Match canonical names or reviewed synonyms, never fuzzy guesses.
                if record.get('visualConfidence')=='low':
                    record['nutritionStatus']='unknown'
                    continue
                name = clean_food_name(record['text'])
                name = normalized(FOOD_ALIASES.get(name, name))
                matches = [f for f in self.foods if normalized(f['name']) == name]
                if not matches:
                    # Word order and punctuation do not change a fully specified food.
                    words = sorted(name.split())
                    matches = [f for f in self.foods if sorted(normalized(f['name']).split()) == words]
                food = matches[0] if len(matches) == 1 else None
                if auto_save and record.get('barcode'):
                    food = self.products.product(record['barcode'])
                elif not food and auto_save:
                    food = (pof_food(record['text'])
                            or self.reviewed(record['text'])
                            or additional_food(record['text'], record.get('catalogueQuery'))
                            or self.closest(record['text']))
                    if food:
                        record['estimated'] = True
                if food:

                    record.update(foodCode=food.get('code') or f"taco:{food['id']}", foodName=food['name'],
                                  nutrientsPer100g=food['nutrients'], source=food.get('source', 'TACO/NEPA/UNICAMP (2011)'))
                    if food.get('url'):
                        record['referenceUrl'] = food['url']
                    if food.get('referenceIds'):record['referenceIds']=food['referenceIds']
                    record['nutrition'] = {key: round(food['nutrients'][column] * record['quantity'] / 100, 4)
                                           if isinstance(food['nutrients'].get(column), (int, float)) else None
                                           for key, column in NUTRIENTS.items()}
                else:
                    if 'frango' in name.split() and not record.get('barcode') and record.get('estimateSource')!='photo':
                        raise ValueError(f"Você informou {record['quantity']:g} g de {record['text']}. "
                                'Para calcular os nutrientes certos, me conta: qual era o corte e como foi preparado? '
                                'Por exemplo, peito sem pele grelhado, peito sem pele cozido ou filé à milanesa. '
                                'Mantenho a quantidade que você informou; ainda não salvei esta refeição.')
                    record['nutritionStatus'] = 'unknown'

    def propose(self, patient_id, event_id, raw, auto_save=False):
        items = raw if isinstance(raw, list) else [raw]
        if not 1 <= len(items) <= 10:
            raise ValueError('Envie até dez registros por vez.')
        records = [validate_record(item) for item in items]
        if sum(len(r['text']) for r in records) > 1800:
            raise ValueError('Divida descrições longas em mais de uma mensagem.')
        try:
            self.enrich_meals(records, auto_save)
        except ValueError as error:
            self.db.execute("UPDATE records SET status='superseded' WHERE patient_id=? AND status='pending'", (patient_id,))
            return str(error)
        if auto_save:
            message = self.automatic_reply(records)
            self.db.execute("UPDATE records SET status='superseded' WHERE patient_id=? AND status='pending'", (patient_id,))
            for index, record in enumerate(records):
                self.db.execute('INSERT INTO records(id,patient_id,event_id,payload,status,created,confirmed) VALUES(?,?,?,?,?,?,?)',
                    (str(uuid.uuid4()), patient_id, f'{event_id}#{index}', json.dumps(record), 'confirmed', time.time(), time.time()))
            return message
        labels = {'meal': 'Refeição', 'water': 'Água', 'weight': 'Peso', 'observation': 'Observação'}
        lines = []
        for index, record in enumerate(records):
            amount = f" — {record['quantity']:g} {record['unit']}" if 'quantity' in record else ''
            nutrition = ' (Sem cálculo nutricional: alimento não identificado na TACO)' if record.get('nutritionStatus') else ''
            if record.get('foodName'):
                nutrition = f" (TACO: {record['foodName']})\n   {nutrition_line(record['nutrition'])}."
            date = datetime.fromisoformat(record['occurredAt']).astimezone(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
            label = MEAL_LABELS.get(record.get('mealType'), labels[record['kind']])
            lines.append(f"{index+1}. {label} — {record['text']}{amount} — {date} (Brasília){nutrition}.")
        meals = [r for r in records if r['kind'] == 'meal']
        total = ''
        if meals:
            known = [r for r in meals if 'nutrition' in r]
            if known:
                totals = {key: sum(r['nutrition'][key] for r in known) if all(r['nutrition'][key] is not None for r in known) else None for key in NUTRIENTS}
                title = 'Total estimado' if len(known) == len(meals) else 'Subtotal dos alimentos identificados (refeição incompleta)'
                total = '\n' + title + ': ' + nutrition_line(totals) + '. Valores da TACO, sujeitos a variações de marca e preparo.'
        message = 'Vamos conferir o que você me contou:\n' + '\n'.join(lines) + total + '\nEstá certo? Responda CONFIRMAR para salvar no app ou CANCELAR REGISTRO para descartar. Ainda não salvei.'
        if len(message) > 1800:
            raise ValueError('Divida descrições longas em mais de uma mensagem.')
        self.db.execute("UPDATE records SET status='superseded' WHERE patient_id=? AND status='pending'", (patient_id,))
        for index, record in enumerate(records):
            self.db.execute('INSERT INTO records(id,patient_id,event_id,payload,status,created) VALUES(?,?,?,?,?,?)',
                (str(uuid.uuid4()), patient_id, f'{event_id}#{index}', json.dumps(record), 'pending', time.time()))
        return message

    def confirm(self, patient_id, accept):
        pending = self.db.execute("SELECT * FROM records WHERE patient_id=? AND status='pending' ORDER BY seq DESC LIMIT 1", (patient_id,)).fetchone()
        if not pending:
            return 'Não há registro aguardando confirmação.'
        if pending['created'] < time.time() - 1800:
            self.db.execute("UPDATE records SET status='expired' WHERE id=?", (pending['id'],))
            return 'A confirmação expirou. Envie os dados novamente para eu conferir com você.'
        self.db.execute("UPDATE records SET status=?,confirmed=? WHERE patient_id=? AND status='pending'",
                        ('confirmed' if accept else 'rejected', time.time(), patient_id))
        return 'Registro salvo no aplicativo. Ele aparecerá quando o app se conectar à internet.' if accept else 'Registro descartado. Pode me enviar a informação corrigida.'

    def correct_meal(self, patient_id, text):
        normalized_message = normalized(text)
        half = re.fullmatch(r'(?:na verdade )?(?:eu )?comi (?:so |apenas )?(?:a )?metade(?: (?:do|da) (.+))?', normalized_message)
        swap = re.fullmatch(r'(?:na verdade[, ]+)?(?:era|foi) (.{1,100}),?\s+(?:e )?n[aã]o (?:era |foi )?(.{1,100})',
                            text.strip().rstrip('.!'), re.I)
        if swap and re.match(r'^(?:sei|sabia|tenho|lembro|medi|pesei|contei|comi|vou)\b', normalized(swap[2])):
            swap = None
        feijoada = re.fullmatch(r'(?:na verdade )?era (?:uma )?feijoada(?: pode corrigir essa)?', normalized_message)
        explicit = re.match(r'^(?:(?:pode )?(?:corrig[ae]|corrigir|corrige)|correcao)\b', normalized_message)
        if not (half or swap or explicit or feijoada):
            return None

        # Edits retain the original creation time and event, even after resync.
        rows = self.db.execute("""
            SELECT * FROM records WHERE patient_id=? AND status='confirmed'
            AND json_extract(payload,'$.kind')='meal' AND created>=?
            ORDER BY created DESC, seq DESC
        """, (patient_id, time.time()-24*3600)).fetchall()
        if not rows:
            return 'Não encontrei uma refeição recente no seu diário do WhatsApp para corrigir.'
        event = rows[0]['event_id'].rsplit('#', 1)[0]
        latest = [(row, json.loads(row['payload'])) for row in rows
                  if row['event_id'].rsplit('#', 1)[0] == event]
        if feijoada:
            return self.correct_photo_feijoada(latest)
        if explicit and not (half or swap):
            if any(normalized(record['text']) == 'feijoada' for _, record in latest):
                return 'A feijoada já está no seu último registro. Quer ajustar a porção ou outro alimento?'
            return 'O que você quer mudar na última refeição: o alimento ou a quantidade?'
        target = normalized(swap[2]) if swap else half[1]
        if target:
            matches = [(row, record) for row, record in latest
                       if any(f' {target} ' in f' {normalized(name)} '
                              for name in (record['text'], record.get('foodName', '')))]
            if len(matches) != 1:
                return 'Não consegui identificar um único alimento na última refeição. Qual nome aparece no recibo?'
            latest = matches

        updates = []
        for row, record in latest:
            if swap:
                replacement = swap[1].rstrip(', ').strip()
                record = validate_record(dict(kind='meal', text=replacement, quantity=record['quantity'],
                                              unit='g', mealType=record.get('mealType'), occurredAt=record['occurredAt'],
                                              estimateSource='photo' if record.get('estimateSource') == 'photo' else None))
                try:
                    self.enrich_meals([record], auto_save=True)
                except ValueError as error:
                    return str(error)
                if not record.get('foodCode'):
                    return 'Ainda não encontrei uma referência para esse alimento. Pode me dizer como ele foi preparado?'
            else:
                record['quantity'] = round(record['quantity'] / 2, 6)
                if record['quantity'] <= 0:
                    return 'Essa porção ficou pequena demais para atualizar. Informe o peso em gramas.'
                if 'portionCount' in record:
                    record['portionCount'] /= 2
                if 'nutrition' in record:
                    record['nutrition'] = {key: round(value / 2, 4) if value is not None else None
                                           for key, value in record['nutrition'].items()}
            updates.append((row, record))

        for row, record in updates:
            self.revise(row, record)
        summary = self.automatic_reply([record for _, record in updates])
        return 'Corrigi sua última refeição no diário.\n\n' + summary if len(summary) < 1730 else 'Corrigi sua última refeição no diário.'

    def revise(self, row, record, removed=False):
        self.db.execute('INSERT OR IGNORE INTO record_original_cursors VALUES (?,?)', (row['id'], row['seq']))
        self.db.execute('DELETE FROM records WHERE id=?', (row['id'],))
        self.db.execute("""
            INSERT INTO records(id, patient_id, event_id, payload, status, created, confirmed)
            VALUES (?,?,?,?,?,?,?)
        """, (row['id'], row['patient_id'], row['event_id'], json.dumps(record),
              'removed' if removed else 'confirmed', row['created'], row['confirmed']))

    def correct_photo_feijoada(self, latest):
        if any(normalized(record['text']) == 'feijoada' for _, record in latest):
            return 'A feijoada já está no seu diário. Se quiser, posso ajustar a porção.'
        components = [(row, record) for row, record in latest
                      if record.get('estimateSource') == 'photo' and
                      re.search(r'\b(carne|linguica|feijao|bacon|costela|paio|toucinho|bife)\b',
                                normalized(record['text']))]
        if not components:
            return 'Quais itens do último prato faziam parte da feijoada? Assim consigo corrigir sem apagar os acompanhamentos.'
        row, first = components[0]
        estimated = sum(item['quantity'] for _, item in components)
        record = validate_record(dict(kind='meal', text='Feijoada', unit='g', quantity=estimated,
                                      occurredAt=first['occurredAt'], mealType=first.get('mealType'),
                                      estimateSource='photo'))
        self.enrich_meals([record], auto_save=True)
        if not record.get('foodCode'):
            return 'Ainda não tenho uma receita de referência para recalcular esse prato.'
        self.revise(row, record)
        for old_row, old_record in components[1:]:
            self.revise(old_row, old_record, removed=True)
        return ('Corrigi o prato: agrupei os itens da feijoada e mantive os acompanhamentos. '
                'A porção continua estimada pela foto.\n\n' + nutrition_line(record['nutrition']) + '.')

    def list(self, patient_id, after=0, revisions=False, legacy_after=0, removals=False):
        cursor = 'r.seq' if revisions else 'COALESCE(c.original_seq,r.seq)'
        rows = self.db.execute(f"""
            SELECT r.id,r.payload,r.status,{cursor} AS seq FROM records r
            LEFT JOIN record_original_cursors c ON c.record_id=r.id
            WHERE r.patient_id=? AND (r.status='confirmed' OR (? AND r.status='removed')) AND {cursor}>?
            AND (r.seq>? OR c.record_id IS NOT NULL)
            ORDER BY seq LIMIT 201
        """, (patient_id, revisions and removals, after, legacy_after if revisions else 0)).fetchall()
        return {'records': [{'id': r['id'], 'seq': r['seq'], **({'removed':True} if r['status']=='removed' else json.loads(r['payload']))} for r in rows[:200]],
                'nextCursor': rows[min(len(rows), 200) - 1]['seq'] if rows else after, 'hasMore': len(rows) > 200}
