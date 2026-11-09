"""Permission-based, self-reported preferences for general meal suggestions."""
import json
import re
from coaching import plain

MENU_READY = '__NUTRI_GENERAL_MENU_READY__'

class MenuCoach:
    def __init__(self, db):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS menu_profiles (patient_id TEXT PRIMARY KEY REFERENCES patients(id), stage TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}')")

    def get(self, patient_id):
        row = self.db.execute('SELECT * FROM menu_profiles WHERE patient_id=?', (patient_id,)).fetchone()
        return {'stage': row['stage'], **json.loads(row['data'])} if row else None

    def offer(self, patient_id):
        if self.get(patient_id):
            return ''
        self.db.execute("INSERT INTO menu_profiles(patient_id,stage) VALUES(?,'offer')", (patient_id,))
        return 'Quer que eu sugira algumas ideias de refeições para a sua rotina?'

    def handle(self, patient_id, text):
        profile = self.get(patient_id)
        command = plain(text).rstrip('.!?').strip()
        request = bool(re.search(r'\b(sugestao|cardapio|dieta|plano alimentar|sugestoes)\b', command))
        if not profile:
            if not request:
                return None
            self.offer(patient_id)
            profile = self.get(patient_id)
        stage = profile['stage']
        data = {k:v for k,v in profile.items() if k != 'stage'}
        yes = command in ('sim', 'quero', 'sim quero', 'pode sim', 'pode mandar', 'quero sim')
        no = command in ('nao', 'nao quero', 'agora nao', 'depois')
        if command in ('nao quero mais sugestoes', 'parar sugestoes', 'cancelar sugestoes', 'deixa para depois'):
            self.save(patient_id, 'declined', data)
            return 'Tudo bem, seguimos com seu diário.'
        if stage == 'ready' and request:
            return MENU_READY
        if stage in ('declined', 'clinical'):
            if not request:
                return None
            stage = 'offer'
        if stage == 'offer':
            if no:
                self.save(patient_id, 'declined', data)
                return 'Tudo bem. Podemos continuar só com seu diário.'
            if yes or request:
                self.save(patient_id, 'adult', {})
                return 'Claro! Primeiro, você tem 18 anos ou mais?'
            return None  # The invitation must not block food logging.
        if stage == 'adult':
            if no or re.search(r'\b(?:[1-9]|1[0-7])\s*anos\b', command):
                self.save(patient_id, 'clinical', {'reason':'menor de idade'})
                return 'Para montar um plano na fase de crescimento, é importante envolver seu responsável e um nutricionista. Posso continuar ajudando com o diário e ideias gerais de alimentação.'
            age = re.search(r'\b(\d{1,3})\s*anos\b', command)
            adult_age = age and 18 <= int(age.group(1)) <= 120
            if not yes and not adult_age and not re.fullmatch(r'(?:1[89]|[2-9]\d|1[01]\d)', command):
                return 'Você tem 18 anos ou mais? Pode responder sim ou não.'
            data['adult'] = True
            self.save(patient_id, 'goal', data)
            return 'O que você quer melhorar na alimentação e como costuma ser sua atividade física durante a semana?'
        if stage == 'goal':
            data['goalAndActivity'] = text[:500]
            self.save(patient_id, 'health', data)
            return 'Você tem alergias, alguma restrição alimentar ou condição de saúde? Está grávida ou amamentando? Se não houver nada disso, pode dizer “não”.'
        if stage == 'health':
            data['restrictionsAndHealth'] = text[:600]
            # This pilot does not create therapeutic diets, even if the user requests one.
            risk = re.search(r'\b(diabet\w*|renal|rim|rins|gestante|gravida|amament\w*|cancer|oncolog\w*|transtorno|anorexia|bulimia|insulina|doenca|doen[cç]a)\b', command)
            if risk and command not in ('nao', 'nenhuma', 'nenhum', 'nao tenho', 'nao tenho nada disso'):
                self.save(patient_id, 'clinical', data)
                return 'Obrigado por me contar. Para adaptar uma dieta a essa situação, vou precisar de um plano definido pelo seu nutricionista. Por aqui posso ajudar com o diário e orientações gerais, sem alterar seu tratamento.'
            self.save(patient_id, 'routine', data)
            return 'Como são seus horários, o que você gosta ou evita comer e quanto tempo e orçamento costuma ter para preparar as refeições?'
        if stage == 'routine':
            if re.search(r'\b(diabetes|renal|gestante|gravida|amamentando|anorexia|bulimia)\b', plain(json.dumps(data)) + ' ' + command):
                self.save(patient_id, 'clinical', data)
                return 'Para adaptar um plano a essa condição, é importante seguir seu nutricionista. Posso ajudar com o diário e ideias gerais.'
            data['routineAndPreferences'] = text[:800]
            self.save(patient_id, 'ready', data)
            return MENU_READY
        return None

    def save(self, patient_id, stage, data):
        self.db.execute('INSERT OR REPLACE INTO menu_profiles(patient_id,stage,data) VALUES(?,?,?)', (patient_id,stage,json.dumps(data,ensure_ascii=False)))
