"""Persistent onboarding and opt-in water reminders (Brazilian local time)."""
import json
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3))
DEFAULT_HOURS = ['09:00', '12:00', '15:00', '18:00']

def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c)).strip()

class Coaching:
    def __init__(self, db):
        self.db = db
        db.executescript('''CREATE TABLE IF NOT EXISTS coaching (
          patient_id TEXT PRIMARY KEY REFERENCES patients(id), name TEXT,
          stage TEXT NOT NULL DEFAULT 'name', reminders INTEGER NOT NULL DEFAULT 0,
          hours TEXT NOT NULL DEFAULT '["09:00","12:00","15:00","18:00"]',
          consent_at TEXT, updated REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS reminder_slots (
          event_id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
          slot TEXT NOT NULL, created REAL NOT NULL, UNIQUE(patient_id,slot));''')

    def get(self, patient_id):
        row = self.db.execute('SELECT * FROM coaching WHERE patient_id=?', (patient_id,)).fetchone()
        return dict(row) if row else None

    def start(self, patient_id):
        self.db.execute('INSERT OR IGNORE INTO coaching(patient_id,updated) VALUES(?,?)', (patient_id, time.time()))
        return 'WhatsApp confirmado! Sou sua assistente virtual de alimentação. Como você gostaria de ser chamado(a)? Se preferir não informar, responda PULAR.'

    def handle(self, patient_id, text):
        p = self.get(patient_id)
        if not p:
            self.start(patient_id)
            return 'Antes de começarmos: como você gostaria de ser chamado(a)? Pode responder PULAR.'
        command = plain(text).rstrip('.!?').strip()
        if command in ('parar lembretes', 'cancelar lembretes', 'parar lembretes de agua', 'cancelar lembretes de agua'):
            self.db.execute("UPDATE coaching SET reminders=0,stage='done',updated=? WHERE patient_id=?", (time.time(), patient_id))
            return 'Combinado, os lembretes de água foram cancelados. Nosso acompanhamento continua por aqui.'
        if command in ('ativar lembretes', 'ativar lembretes de agua'):
            self.db.execute("UPDATE coaching SET stage='reminders',updated=? WHERE patient_id=?", (time.time(), patient_id))
            return self.question()
        if command.startswith('horarios de agua ') or p['stage'] == 'hours':
            hours = re.findall(r'(?<!\d)(?:[01]\d|2[0-3]):[0-5]\d(?!\d)', text)
            remainder = re.sub(r'(?<!\d)(?:[01]\d|2[0-3]):[0-5]\d(?!\d)', '', command.removeprefix('horarios de agua '))
            if not hours or len(hours) > 6 or len(set(hours)) != len(hours) or re.sub(r'[\s,;e]+', '', remainder):
                return 'Quais horários você prefere? Envie até seis, por exemplo: 09:00, 13:00, 17:00 (horário de Brasília).'
            self.db.execute("UPDATE coaching SET hours=?,stage='reminders',updated=? WHERE patient_id=?", (json.dumps(sorted(hours)), time.time(), patient_id))
            return self.question(sorted(hours))
        if command in ('alterar lembretes', 'mudar horarios de agua'):
            self.db.execute("UPDATE coaching SET stage='hours',reminders=0,updated=? WHERE patient_id=?", (time.time(), patient_id))
            return 'Quais horários você prefere? Envie até seis no formato 09:00, 13:00, 17:00 (Brasília). Os lembretes ficam pausados até você confirmar.'
        if p['stage'] == 'preferences':
            from menu_coach import MenuCoach
            menu = MenuCoach(self.db)
            saved = menu.get(patient_id) or {}
            data = {k:v for k,v in saved.items() if k != 'stage'}
            data['foodPreferences'] = text[:800]
            menu.save(patient_id, saved.get('stage', 'preferences_saved'), data)
            self.db.execute("UPDATE coaching SET stage='reminders',updated=? WHERE patient_id=?", (time.time(), patient_id))
            return 'Obrigado por me contar! Vou levar isso em conta nas sugestões.\n\n' + self.question(json.loads(p['hours']))
        if p['stage'] == 'name' or command.startswith('me chame de ') or command.startswith('pode me chamar de '):
            name = re.sub(r'^(?:pode me chamar de|me chame de|meu nome [ée]|sou o|sou a)\s+', '', text.strip(), flags=re.I).strip(' .!')
            if command in ('pular', 'prefiro nao informar'):
                name = None
            elif not 1 <= len(name) <= 60 or not all(c.isalpha() or c in " '-" for c in name) or len(name.split()) > 6 or plain(name).split()[0] in ('comi', 'bebi', 'quero', 'preciso', 'hoje', 'tenho', 'tomei', 'meu', 'minha'):
                return 'Me diga só como prefere ser chamado(a), ou responda PULAR. Depois seguimos com seus registros.'
            if p['stage'] != 'name':
                self.db.execute('UPDATE coaching SET name=?,updated=? WHERE patient_id=?', (name,time.time(),patient_id))
                return f'Combinado, vou chamar você de {name}.' if name else 'Tudo bem, seguimos sem usar um nome.'
            from patient_profile import read_profile, GOALS
            goal = GOALS.get(read_profile(self.db, patient_id).get('goal'))
            if goal:
                self.db.execute("UPDATE coaching SET name=?,stage='preferences',updated=? WHERE patient_id=?", (name,time.time(),patient_id))
                greeting = f'Prazer, {name}!' if name else 'Vamos nos conhecer melhor!'
                return greeting + f' Vi no aplicativo que seu objetivo é {goal}.\n\nQuero conhecer sua alimentação para preparar uma sugestão que combine com você. Você costuma comer de tudo ou tem algo que não gosta ou evita?'
            self.db.execute("UPDATE coaching SET name=?,stage='reminders',updated=? WHERE patient_id=?", (name, time.time(), patient_id))
            return (f'Prazer, {name}! ' if name else 'Tudo bem! ') + self.question(json.loads(p['hours']))
        if p['stage'] == 'reminders':
            if command not in ('sim', 'autorizo', 'sim autorizo', 'pode sim', 'sim pode', 'sim pode mandar', 'pode mandar', 'nao', 'nao quero', 'agora nao'):
                return self.question(json.loads(p['hours']))
            accepted = command in ('sim', 'autorizo', 'sim autorizo', 'pode sim', 'sim pode', 'sim pode mandar', 'pode mandar')
            self.db.execute("UPDATE coaching SET stage='done',reminders=?,consent_at=?,updated=? WHERE patient_id=?", (int(accepted), datetime.now(timezone.utc).isoformat(), time.time(), patient_id))
            return ('Combinado! Vou lembrar você de beber água às ' + ', '.join(json.loads(p['hours'])) + '. ' if accepted else 'Sem problemas, não vou enviar lembretes. ') + 'Pode me contar o que comeu ou bebeu que eu registro por aqui.'
        return None

    @staticmethod
    def question(hours=None):
        return 'Posso enviar lembretes para beber água às ' + ', '.join(hours or DEFAULT_HOURS) + '? Os horários seguem Brasília. Pode responder sim ou não.'

    def schedule(self, now=None):
        now = now or datetime.now(timezone.utc)
        local = now.astimezone(BRASILIA)
        rows = self.db.execute('SELECT c.*,p.phone,p.consent_version FROM coaching c JOIN patients p ON p.id=c.patient_id WHERE c.reminders=1 AND c.stage=\'done\' AND p.consent=1 AND p.verified=1').fetchall()
        for p in rows:
            for hour in json.loads(p['hours']):
                hh, mm = map(int, hour.split(':'))
                due = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
                # No replay of hours missed during downtime.
                if not 0 <= (local - due).total_seconds() < 300:
                    continue
                slot = due.isoformat()
                event_id = f"reminder:{p['patient_id']}:{due.strftime('%Y%m%dT%H%M')}"
                added = self.db.execute('INSERT OR IGNORE INTO reminder_slots(event_id,patient_id,slot,created) VALUES(?,?,?,?)', (event_id, p['patient_id'], slot, now.timestamp())).rowcount
                if added:
                    body = {'kind': 'reminder', 'eventId': event_id, 'userId': p['patient_id'], 'phone': p['phone'], 'consent': {'granted': True, 'version': p['consent_version'], 'at': now.isoformat()}}
                    self.db.execute('INSERT INTO notifications(id,body) VALUES(?,?)', (event_id, json.dumps(body)))

    def reminder(self, event_id, patient_id, now=None):
        now = time.time() if now is None else now
        p = self.get(patient_id)
        row = self.db.execute('SELECT * FROM reminder_slots WHERE event_id=? AND patient_id=?', (event_id, patient_id)).fetchone()
        if not row or not p or not p['reminders'] or now - row['created'] > 600:
            return None
        name = f", {p['name']}" if p['name'] else ''
        return f'Oi{name}! Uma pausa para lembrar da água. 💧 Se beber, pode me contar a quantidade que eu anoto.'
