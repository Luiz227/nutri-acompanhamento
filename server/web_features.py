"""Account-scoped diary, profile and evolution for the website."""
import json
import re
import time
import uuid
from datetime import datetime, timedelta

from coaching import BRASILIA
from daily_progress import summarize, diary_rows
from patient_profile import age_of, validate_profile, profile_context
from records import validate_record
from web_accounts import AuthError


def history(store, patient_id):
    rows = store.db.execute("SELECT * FROM records WHERE patient_id=? AND status='confirmed' ORDER BY json_extract(payload,'$.occurredAt'),seq", (patient_id,)).fetchall()
    return [(row, json.loads(row['payload'])) for row in rows]


def evolution(store, patient, days=30):
    profile = json.loads(patient['context']).get('appProfile', {})
    today = datetime.now(BRASILIA).date()
    rows = history(store, patient['id'])
    weights = [{'date': record['occurredAt'], 'kg': record['quantity'], 'id': row['id']}
               for row, record in rows if record['kind'] == 'weight']
    latest = weights[-1]['kg'] if weights else profile.get('weightKg')
    initial = weights[0]['kg'] if weights else profile.get('weightKg')
    height = profile.get('heightCm')
    raw_bmi = latest / (height / 100) ** 2 if latest and height else None
    bmi = round(raw_bmi, 1) if raw_bmi else None
    age = age_of(profile)
    category = None
    if bmi is not None and age is not None and age >= 20:
        category = next(label for threshold, label in [(18.5, 'Baixo peso'), (25, 'Faixa de referência'),
            (30, 'Sobrepeso'), (35, 'Obesidade grau I'), (40, 'Obesidade grau II'), (float('inf'), 'Obesidade grau III')] if raw_bmi < threshold)
    grouped = {}
    for _, record in rows:
        day = datetime.fromisoformat(record['occurredAt']).astimezone(BRASILIA).date()
        grouped.setdefault(day, []).append(record)
    daily = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        records = grouped.get(day, [])
        totals, missing, estimated = summarize(records)
        daily.append({'date': day.isoformat(), 'totals': totals, 'missing': sorted(missing),
                      'estimated': estimated, 'tracked': bool(records),
                      'hasMeals': any(r['kind']=='meal' for r in records),
                      'hasWater': any(r['kind']=='water' for r in records)})
    tracked = [day for day in daily if day['tracked']]
    averages = {}
    for key in daily[0]['totals']:
        samples = [day['totals'][key] for day in tracked
                   if day['hasWater' if key=='waterMl' else 'hasMeals'] and key not in day['missing']]
        averages[key] = round(sum(samples)/len(samples),1) if samples else None
    return {'bmi': bmi, 'bmiCategory': category, 'age': age, 'heightCm': height,
            'currentWeightKg': latest, 'initialWeightKg': initial, 'targetWeightKg': profile.get('targetWeightKg'),
            'changeKg': round(latest-initial, 2) if latest and initial else None,
            'weights': weights, 'daily': daily, 'averages': averages, 'trackedDays': len(tracked)}


def feature_request(store, patient, path, method, body, query):
    """Caller already authenticates the cookie and enforces same-origin writes."""
    owner = patient['id']
    if path == '/web-api/evolution' and method == 'GET':
        days = int(query.get('days', ['30'])[0])
        if days not in (7, 30, 90, 365):
            raise AuthError(400, 'Escolha 7, 30, 90 ou 365 dias.')
        return evolution(store, patient, days)
    if path == '/web-api/profile' and method == 'POST':
        context = json.loads(patient['context'])
        original = context.get('appProfile', {})
        raw = body.get('profile')
        if not isinstance(raw, dict):
            raise AuthError(400, 'Preencha seu perfil.')
        # Merge fields so a web edit does not silently discard app goals.
        profile = validate_profile({**original, **raw})
        context.update(profile_context(profile))
        store.db.execute('UPDATE patients SET context=? WHERE id=?', (json.dumps(context), owner))
        return {'ok': True}
    if path == '/web-api/preferences' and method in ('GET', 'POST'):
        store.db.execute('INSERT OR IGNORE INTO coaching(patient_id,updated) VALUES(?,?)', (owner,time.time()))
        if method == 'POST':
            name = body.get('name', '')
            hours = body.get('hours')
            if not isinstance(name, str) or len(name.strip()) > 60 or any(ord(c) < 32 for c in name):
                raise AuthError(400, 'Informe um nome com até 60 caracteres.')
            if (not isinstance(hours, list) or not 1 <= len(hours) <= 6 or
                any(not isinstance(h, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', h) for h in hours) or len(set(hours)) != len(hours)):
                raise AuthError(400, 'Informe até seis horários diferentes, como 09:00.')
            if type(body.get('reminders')) is not bool:
                raise AuthError(400, 'Confirme se deseja lembretes.')
            store.db.execute("UPDATE coaching SET name=?,hours=?,reminders=?,consent_at=?,updated=?,stage='done' WHERE patient_id=?",
                (name.strip() or None, json.dumps(sorted(hours)), int(body['reminders']), datetime.now(BRASILIA).isoformat(),time.time(), owner))
        p = store.coaching.get(owner)
        return {'name': p['name'] or '', 'hours': json.loads(p['hours']), 'reminders': bool(p['reminders'])}
    if path == '/web-api/foods' and method == 'GET':
        text = query.get('q', [''])[0][:180]
        barcode = query.get('barcode', [''])[0]
        if barcode:
            if not re.fullmatch(r'\d{8,14}', barcode):
                raise AuthError(400, 'Código de barras inválido.')
            product = store.records.products.product(barcode)
            return {'product': product}
        names = store.records.candidates(text) if len(text.strip()) >= 2 else []
        return {'foods': names}
    if path == '/web-api/library' and method in ('GET', 'POST'):
        if method == 'POST':
            name, kind, foods = body.get('name'), body.get('kind'), body.get('foods')
            if not isinstance(name,str) or not 1 <= len(name.strip()) <= 120 or kind not in ('recipe','favorite'):
                raise AuthError(400, 'Informe o nome da receita ou do favorito.')
            if not isinstance(foods,list) or not 1 <= len(foods) <= 10:
                raise AuthError(400, 'Inclua de um a dez alimentos.')
            validated = [validate_record({**food,'kind':'meal'}) for food in foods if isinstance(food,dict)]
            if len(validated) != len(foods):
                raise AuthError(400, 'Alimentos inválidos.')
            store.records.enrich_meals(validated, auto_save=True)
            if store.db.execute('SELECT count(*) FROM web_library WHERE patient_id=?',(owner,)).fetchone()[0] >= 200:
                raise AuthError(400, 'Sua biblioteca tem 200 itens. Remova um antes de acrescentar outro.')
            store.db.execute('INSERT INTO web_library VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),owner,kind,name.strip(),json.dumps(validated),time.time()))
        return {'items':[{'id':row['id'],'kind':row['kind'],'name':row['name'],'foods':json.loads(row['foods'])}
                         for row in store.db.execute('SELECT * FROM web_library WHERE patient_id=? ORDER BY created DESC',(owner,))]}
    if path in ('/web-api/library-remove','/web-api/library-log') and method == 'POST':
        row = store.db.execute('SELECT * FROM web_library WHERE patient_id=? AND id=?',(owner,body.get('id'))).fetchone()
        if not row:
            raise AuthError(404, 'Item não encontrado.')
        if path.endswith('remove'):
            store.db.execute('DELETE FROM web_library WHERE id=? AND patient_id=?',(row['id'],owner))
            return {'ok':True}
        records = [{**food,'occurredAt':body.get('occurredAt'),'mealType':body.get('mealType')} for food in json.loads(row['foods'])]
        request_id = body.get('requestId')
        if not isinstance(request_id,str) or not re.fullmatch(r'[\w-]{16,80}', request_id):
            raise AuthError(400, 'Atualize a página e tente novamente.')
        event_id = 'web-library:'+owner+':'+request_id
        if not store.db.execute('SELECT 1 FROM records WHERE patient_id=? AND event_id=?',(owner,event_id+'#0')).fetchone():
            store.records.propose(owner,event_id,records,auto_save=True)
        if not store.db.execute('SELECT 1 FROM records WHERE patient_id=? AND event_id=?',(owner,event_id+'#0')).fetchone():
            raise AuthError(400, 'Não foi possível registrar a receita. Confira os alimentos.')
        return {'ok':True}
    if path == '/web-api/entry' and method == 'POST':
        raw = body.get('record')
        record = validate_record(raw)
        record_id = body.get('id')
        if record_id:
            row = store.db.execute("SELECT * FROM records WHERE id=? AND patient_id=? AND status='confirmed'", (record_id, owner)).fetchone()
            if not row:
                raise AuthError(404, 'Registro não encontrado.')
            store.records.enrich_meals([record], auto_save=True)
            store.records.revise(row, record)
        else:
            request_id = body.get('requestId')
            if not isinstance(request_id, str) or not re.fullmatch(r'[\w-]{16,80}', request_id):
                raise AuthError(400, 'Atualize a página e tente novamente.')
            event_id = 'web:' + owner + ':' + request_id
            existing = store.db.execute('SELECT id FROM records WHERE patient_id=? AND event_id=?', (owner, event_id+'#0')).fetchone()
            if not existing:
                # Reuse the same nutrient resolver as WhatsApp and Android sync.
                store.records.propose(owner, event_id, raw, auto_save=True)
            existing = store.db.execute('SELECT id FROM records WHERE patient_id=? AND event_id=?', (owner, event_id+'#0')).fetchone()
            if not existing:
                raise AuthError(400, 'Não foi possível salvar. Confira alimento, quantidade e unidade.')
            record_id = existing['id']
        return {'ok': True, 'id': record_id}
    if path == '/web-api/remove-entry' and method == 'POST':
        row = store.db.execute("SELECT * FROM records WHERE id=? AND patient_id=? AND status='confirmed'", (body.get('id'), owner)).fetchone()
        if not row:
            raise AuthError(404, 'Registro não encontrado.')
        store.records.revise(row, json.loads(row['payload']), removed=True)
        return {'ok': True}
    if path == '/web-api/export' and method == 'GET':
        return {'format': 'garfofala-web-v1', 'exportedAt': datetime.now(BRASILIA).isoformat(),
                'profile': json.loads(patient['context']).get('appProfile', {}),
                'records': [{'id': row['id'], **record} for row, record in history(store, owner)],
                'library': [{'kind':row['kind'],'name':row['name'],'foods':json.loads(row['foods'])} for row in store.db.execute('SELECT * FROM web_library WHERE patient_id=?',(owner,))]}
    return None
