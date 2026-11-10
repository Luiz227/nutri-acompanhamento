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
from portions import portion
from datetime import datetime, timezone, timedelta
from pathlib import Path


def normalized(text):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if not unicodedata.combining(c))).strip()


# Explicit synonyms only: never infer fat content, preparation, or bread type.
FOOD_ALIASES = {
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
        if raw['kind'] == 'meal' and unit in ('unit', 'slice'):
            measure = portion(text, unit, raw.get('portionSize', 'medium'))
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
          CREATE INDEX IF NOT EXISTS records_owner ON records(patient_id,seq);''')

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

    def closest(self, text):
        query = normalized(text)
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
        paragraphs = []
        introductions = ('Anotei', 'Registrei', 'Já deixei salvo')
        for record in records:
            if record['kind'] == 'water':
                paragraphs.append(f"{random.choice(introductions)} {record['quantity']:g} ml de água no seu diário. 💧")
            elif record['kind'] == 'meal':
                label = MEAL_LABELS.get(record.get('mealType'), 'refeição').lower()
                if record.get('estimateSource') == 'household':
                    measure = 'fatia' if record['portionReference']['unit'] == 'slice' else 'unidade'
                    if record['portionCount'] != 1:
                        measure += 's'
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

    def propose(self, patient_id, event_id, raw, auto_save=False):
        items = raw if isinstance(raw, list) else [raw]
        if not 1 <= len(items) <= 5:
            raise ValueError('Confirme até cinco registros por vez.')
        records = [validate_record(item) for item in items]
        if sum(len(r['text']) for r in records) > 1000:
            raise ValueError('Divida descrições longas em mais de uma mensagem.')
        for record in records:
            if record['kind'] == 'meal':
                # Match canonical names or reviewed synonyms, never fuzzy guesses.
                name = normalized(record['text'])
                name = normalized(FOOD_ALIASES.get(name, name))
                matches = [f for f in self.foods if normalized(f['name']) == name]
                if not matches:
                    # Word order and punctuation do not change a fully specified food.
                    words = sorted(name.split())
                    matches = [f for f in self.foods if sorted(normalized(f['name']).split()) == words]
                food = matches[0] if len(matches) == 1 else None
                if auto_save and record.get('barcode'):
                    food = self.products.product(record['barcode'])
                if not food and auto_save:
                    food = self.closest(record['text'])
                    if food:
                        record['estimated'] = True
                if food:

                    record.update(foodCode=food.get('code') or f"taco:{food['id']}", foodName=food['name'],
                                  nutrientsPer100g=food['nutrients'], source=food.get('source', 'TACO/NEPA/UNICAMP (2011)'))
                    record['nutrition'] = {key: round(food['nutrients'][column] * record['quantity'] / 100, 4)
                                           if isinstance(food['nutrients'].get(column), (int, float)) else None
                                           for key, column in NUTRIENTS.items()}
                else:
                    if 'frango' in name.split():
                        self.db.execute("UPDATE records SET status='superseded' WHERE patient_id=? AND status='pending'", (patient_id,))
                        return (f"Você informou {record['quantity']:g} g de {record['text']}. "
                                'Para calcular os nutrientes certos, me conta: qual era o corte e como foi preparado? '
                                'Por exemplo, peito sem pele grelhado, peito sem pele cozido ou filé à milanesa. '
                                'Mantenho a quantidade que você informou; ainda não salvei esta refeição.')
                    record['nutritionStatus'] = 'unknown'
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

    def list(self, patient_id, after=0):
        rows = self.db.execute("SELECT * FROM records WHERE patient_id=? AND status='confirmed' AND seq>? ORDER BY seq LIMIT 201", (patient_id, after)).fetchall()
        return {'records': [{'id': r['id'], 'seq': r['seq'], **json.loads(r['payload'])} for r in rows[:200]],
                'nextCursor': rows[min(len(rows), 200) - 1]['seq'] if rows else after, 'hasMore': len(rows) > 200}
