"""Permission-based, self-reported preferences for general meal suggestions."""
import json
import re
from coaching import plain
from patient_profile import read_profile, age_of, GOALS, ACTIVITY

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
        request = bool(re.search(r'\b(sugestao|cardapio|dieta|plano alimentar|sugestoes|pdf|guia alimentar)\b', command))
        if not profile:
            if not request:
                return None
            self.offer(patient_id)
            profile = self.get(patient_id)
        stage = profile['stage']
        data = {k:v for k,v in profile.items() if k != 'stage'}
        app = read_profile(self.db, patient_id)
        data['appProfile'] = app
        yes = command in ('sim', 'quero', 'sim quero', 'pode sim', 'pode mandar', 'quero sim')
        no = command in ('nao', 'nao quero', 'agora nao', 'depois')
        if command in ('nao quero mais sugestoes', 'parar sugestoes', 'cancelar sugestoes', 'deixa para depois',
                       'nao quero pdf', 'cancelar pdf', 'nao quero mais pdf', 'cancelar guia'):
            self.save(patient_id, 'declined', data)
            return 'Tudo bem, seguimos com seu diário.'
        if stage == 'ready' and request:
            known_age = age_of(app)
            if known_age is not None and known_age < 18:
                self.save(patient_id, 'clinical', {'reason': 'menor de idade', 'appProfile': app})
                return 'Para um plano individual nessa fase de crescimento, é importante envolver seu responsável e um nutricionista. Posso ajudar com o diário.'
            self.save(patient_id, 'ready', data)
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
                data = {'appProfile': app}
                age = age_of(app)
                if age is not None:
                    if age < 18:
                        self.save(patient_id, 'clinical', {'reason': 'menor de idade', 'appProfile': app})
                        return 'Pelo cadastro você está na fase de crescimento. Para um plano individual, é importante envolver seu responsável e um nutricionista. Posso ajudar com o diário.'
                    data['adult'] = True
                    return self.ask_missing_goal(patient_id, data, app)
                self.save(patient_id, 'adult', data)
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
            return self.ask_missing_goal(patient_id, data, app)
        if stage == 'goal':
            if not app.get('goal') and not re.search(r'perder|emagrecer|ganhar|massa|hipertrofia|manter|saude|organizar|rotina|melhorar', command):
                data['reportedActivity'] = text[:500]
                self.save(patient_id, 'goal', data)
                return 'Entendi. E qual é seu objetivo com a alimentação: perder peso, manter, ganhar massa ou organizar a rotina?'
            data['goalAndActivity'] = text[:500]
            self.save(patient_id, 'health', data)
            return self.health_question(app)
        if stage == 'health':
            clear_no = command in ('nao', 'nenhuma', 'nenhum', 'nao tenho', 'nao tenho nada disso', 'nao tenho restricoes', 'nao tenho alergias')
            if not clear_no and not re.search(r'alerg|restri|intoler|diabet|renal|rim|rins|gestante|gravida|amament|doenca|doen[cç]a|saude|celiac|lactose|gluten|transtorno|anorexia|bulimia|insulina', command):
                return 'Sobre alergias, restrições ou condições de saúde: existe algo que eu precise considerar? Se não, pode responder “não tenho”.'
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

    @staticmethod
    def health_question(app):
        question = 'Você tem alergias, alguma restrição alimentar ou condição de saúde?'
        if app.get('gender') == 'female':
            question += ' Há gestação ou amamentação a considerar?'
        return question + ' Se não houver, pode dizer “não”.'

    def ask_missing_goal(self, patient_id, data, app):
        goal = GOALS.get(app.get('goal'))
        activity = ACTIVITY.get(app.get('activityLevel'))
        if goal and activity:
            data['goalAndActivity'] = f'Objetivo do aplicativo: {goal}. Atividade do cadastro: {activity}.'
            self.save(patient_id, 'health', data)
            return f'Vou considerar seu objetivo de {goal}, que já está no aplicativo. ' + self.health_question(app)
        self.save(patient_id, 'goal', data)
        if goal:
            return f'No aplicativo seu objetivo é {goal}. Como está sua rotina de atividade física?'
        if activity:
            return 'Já tenho seu nível de atividade no aplicativo. Qual é seu objetivo com a alimentação?'
        return 'O que você quer melhorar na alimentação e como costuma ser sua atividade física durante a semana?'

    def save(self, patient_id, stage, data):
        self.db.execute('INSERT OR REPLACE INTO menu_profiles(patient_id,stage,data) VALUES(?,?,?)', (patient_id,stage,json.dumps(data,ensure_ascii=False)))
