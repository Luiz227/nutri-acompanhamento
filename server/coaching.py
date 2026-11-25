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
        if 'reminder_count' not in {row['name'] for row in db.execute('PRAGMA table_info(coaching)')}:
            db.execute('ALTER TABLE coaching ADD COLUMN reminder_count INTEGER')

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
        configuring = p['stage'] in ('reminders', 'reminder_count', 'reminder_hours', 'reminder_confirm', 'hours')
        if command in ('parar lembretes', 'cancelar lembretes', 'parar lembretes de agua', 'cancelar lembretes de agua') or configuring and command in ('nao', 'nao quero', 'agora nao', 'cancelar'):
            self.db.execute("UPDATE coaching SET reminders=0,stage='done',updated=? WHERE patient_id=?", (time.time(), patient_id))
            return 'Combinado, os lembretes de água foram cancelados. Nosso acompanhamento continua por aqui.'
        if command in ('ativar lembretes', 'ativar lembretes de agua'):
            self.db.execute("UPDATE coaching SET stage='reminders',reminders=0,reminder_count=NULL,updated=? WHERE patient_id=?", (time.time(), patient_id))
            return self.question()
        if command.startswith('horarios de agua ') or p['stage'] in ('hours', 'reminder_hours'):
            expression = r'(?<!\d)([01]?\d|2[0-3])(?:(?::|h)([0-5]\d)?)?(?!\d)'
            value = command.removeprefix('horarios de agua ')
            hours = [f'{int(h):02d}:{m or "00"}' for h,m in re.findall(expression, value)]
            remainder = re.sub(expression, '', value)
            remainder = re.sub(r'\b(?:as|e|horas|hora)\b', '', remainder)
            if not hours or len(hours) > 6 or len(set(hours)) != len(hours) or re.sub(r'[\s,;e]+', '', remainder):
                return 'Me diga os horários, por exemplo: 9h, 13h e 17h. Use horários diferentes, entre 00:00 e 23:59.'
            if p['stage'] == 'reminder_hours' and len(hours) != p['reminder_count']:
                return f'Você escolheu {p["reminder_count"]} lembretes por dia. Quais são os {p["reminder_count"]} horários?'
            active = p['stage'] == 'reminder_hours'
            self.db.execute("UPDATE coaching SET hours=?,stage=?,reminders=?,reminder_count=?,consent_at=?,updated=? WHERE patient_id=?",
                (json.dumps(sorted(hours)), 'done' if active else 'reminder_confirm', int(active),len(hours),datetime.now(timezone.utc).isoformat(),time.time(),patient_id))
            return self.confirmation(hours) if active else 'Posso ativar seus lembretes às ' + ', '.join(sorted(hours)) + '? Pode responder sim ou não.'
        if command in ('alterar lembretes', 'mudar horarios de agua'):
            self.db.execute("UPDATE coaching SET stage='reminder_count',reminders=0,reminder_count=NULL,updated=? WHERE patient_id=?", (time.time(), patient_id))
            return 'Vamos ajustar! Quantas vezes por dia você quer ser lembrado(a) de beber água? Pode escolher de 1 a 6.'
        if p['stage'] == 'reminder_count':
            words = {'uma':1,'um':1,'duas':2,'dois':2,'tres':3,'quatro':4,'cinco':5,'seis':6}
            answer = re.sub(r'\s+(?:vez(?:es)?|lembretes?)(?:\s+por dia|\s+ao dia)?$', '', command)
            count = int(answer) if re.fullmatch(r'[1-6]',answer) else words.get(answer)
            if not count:
                return 'Quantas vezes por dia? Escolha um número de 1 a 6.'
            self.db.execute("UPDATE coaching SET stage='reminder_hours',reminder_count=?,updated=? WHERE patient_id=?",(count,time.time(),patient_id))
            prompt = 'E em qual horário você prefere receber o lembrete?' if count == 1 else f'E quais horários você prefere para os {count} lembretes?'
            return prompt + ' Pode escrever, por exemplo, 9h ou 14:30. Vou usar o horário de Brasília.'
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
        if p['stage'] in ('reminders', 'reminder_confirm'):
            if command not in ('sim', 'autorizo', 'sim autorizo', 'pode sim', 'sim pode', 'sim pode mandar', 'pode mandar', 'nao', 'nao quero', 'agora nao'):
                return self.question(json.loads(p['hours']))
            accepted = command in ('sim', 'autorizo', 'sim autorizo', 'pode sim', 'sim pode', 'sim pode mandar', 'pode mandar')
            if accepted and p['stage'] == 'reminders':
                self.db.execute("UPDATE coaching SET stage='reminder_count',reminders=0,consent_at=?,updated=? WHERE patient_id=?",(datetime.now(timezone.utc).isoformat(),time.time(),patient_id))
                return 'Quantas vezes por dia você gostaria de receber um lembrete de água? Pode escolher de 1 a 6.'
            self.db.execute("UPDATE coaching SET stage='done',reminders=?,consent_at=?,updated=? WHERE patient_id=?", (int(accepted), datetime.now(timezone.utc).isoformat(), time.time(), patient_id))
            return ('Combinado! Vou lembrar você de beber água às ' + ', '.join(json.loads(p['hours'])) + '. ' if accepted else 'Sem problemas, não vou enviar lembretes. ') + 'Pode me contar o que comeu ou bebeu que eu registro por aqui.'
        return None

    @staticmethod
    def question(hours=None):
        return 'Você gostaria que eu lembrasse você de beber água durante o dia? Pode responder sim ou não.'

    @staticmethod
    def confirmation(hours):
        frequency = 'uma vez' if len(hours) == 1 else str(len(hours)) + ' vezes'
        return 'Combinado! Vou lembrar você de beber água ' + frequency + ' por dia, às ' + ', '.join(sorted(hours)) + '. Quando atingir sua meta diária de água, os lembretes param até o dia seguinte.'

    def schedule(self, now=None):
        from daily_progress import water_goal_reached
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
                if water_goal_reached(self.db, p['patient_id'], local.date()):
                    break
                slot = due.isoformat()
                event_id = f"reminder:{p['patient_id']}:{due.strftime('%Y%m%dT%H%M')}"
                added = self.db.execute('INSERT OR IGNORE INTO reminder_slots(event_id,patient_id,slot,created) VALUES(?,?,?,?)', (event_id, p['patient_id'], slot, now.timestamp())).rowcount
                if added:
                    body = {'kind': 'reminder', 'eventId': event_id, 'userId': p['patient_id'], 'phone': p['phone'], 'consent': {'granted': True, 'version': p['consent_version'], 'at': now.isoformat()}}
                    self.db.execute('INSERT INTO notifications(id,body) VALUES(?,?)', (event_id, json.dumps(body)))

    def reminder(self, event_id, patient_id, now=None):
        from daily_progress import water_goal_reached
        now = time.time() if now is None else now
        p = self.get(patient_id)
        row = self.db.execute('SELECT * FROM reminder_slots WHERE event_id=? AND patient_id=?', (event_id, patient_id)).fetchone()
        if not row or not p or not p['reminders'] or now - row['created'] > 600:
            return None
        local = datetime.fromtimestamp(now, BRASILIA)
        if datetime.fromisoformat(row['slot']).date() != local.date() or water_goal_reached(self.db, patient_id, local.date()):
            return None
        name = f", {p['name']}" if p['name'] else ''
        return f'Oi{name}! Uma pausa para lembrar da água. 💧 Se beber, pode me contar a quantidade que eu anoto.'
