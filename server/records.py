"""Validated patient records. AI proposes; only the patient's reply confirms."""
import json
import math
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path


def normalized(text):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFD', text.lower())
                   if not unicodedata.combining(c))).strip()


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
    if raw['kind'] != 'observation':
        amount, unit = raw.get('quantity'), raw.get('unit')
        if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not math.isfinite(amount) or amount <= 0:
            raise ValueError('Confirme a quantidade e a unidade antes de registrar.')
        units = {'meal': {'g': 1}, 'water': {'ml': 1, 'l': 1000}, 'weight': {'kg': 1, 'g': .001}}
        if unit not in units[raw['kind']]:
            raise ValueError('Refeições precisam de gramas, água de ml/l e peso de kg/g.')
        amount *= units[raw['kind']][unit]
        limit = {'meal': 10000, 'water': 20000, 'weight': 600}[raw['kind']]
        if amount > limit:
            raise ValueError('Quantidade fora do limite de um registro; confirme o valor.')
        result.update(quantity=round(amount, 6), unit={'meal': 'g', 'water': 'ml', 'weight': 'kg'}[raw['kind']])
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
        db.executescript('''CREATE TABLE IF NOT EXISTS records (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
          patient_id TEXT NOT NULL REFERENCES patients(id), event_id TEXT UNIQUE NOT NULL,
          payload TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, confirmed REAL);
          CREATE INDEX IF NOT EXISTS records_owner ON records(patient_id,seq);''')

    def candidates(self, text):
        tokens = [t for t in normalized(text).split() if len(t) >= 4]
        scored = [(sum(t in normalized(f['name']).split() for t in tokens), f) for f in self.foods]
        return [{'name': f['name']} for score, f in sorted(scored, key=lambda pair: -pair[0]) if score > 0][:12]

    def propose(self, patient_id, event_id, raw):
        items = raw if isinstance(raw, list) else [raw]
        if not 1 <= len(items) <= 5:
            raise ValueError('Confirme até cinco registros por vez.')
        records = [validate_record(item) for item in items]
        if sum(len(r['text']) for r in records) > 1000:
            raise ValueError('Divida descrições longas em mais de uma mensagem.')
        for record in records:
            if record['kind'] == 'meal':
                # Only an exact canonical name selects nutrients; never guess preparation.
                matches = [f for f in self.foods if normalized(f['name']) == normalized(record['text'])]
                if len(matches) == 1:
                    food = matches[0]
                    record.update(foodCode=f"taco:{food['id']}", foodName=food['name'],
                                  nutrientsPer100g=food['nutrients'], source='TACO/NEPA/UNICAMP (2011)')
                else:
                    record['nutritionStatus'] = 'unknown'
        labels = {'meal': 'Refeição', 'water': 'Água', 'weight': 'Peso', 'observation': 'Observação'}
        lines = []
        for index, record in enumerate(records):
            amount = f" — {record['quantity']:g} {record['unit']}" if 'quantity' in record else ''
            nutrition = ' (Sem cálculo nutricional: alimento não identificado na TACO)' if record.get('nutritionStatus') else ''
            date = datetime.fromisoformat(record['occurredAt']).astimezone(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
            lines.append(f"{index+1}. {labels[record['kind']]} — {record['text']}{amount} — {date} (Brasília){nutrition}.")
        message = 'Entendi:\n' + '\n'.join(lines) + '\nAinda não salvei. Para salvar no aplicativo, responda CONFIRMAR. Para descartar, responda CANCELAR REGISTRO.'
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
