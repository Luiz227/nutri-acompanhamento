"""Phone-verified web accounts, Argon2id passwords and durable WhatsApp OTPs."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from patient_profile import validate_profile, profile_context

HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 7 * 86400


class AuthError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def phone_number(value):
    digits = re.sub(r'[\s()+.\-]', '', str(value or ''))
    if re.fullmatch(r'\d{10,11}', digits):
        digits = '55' + digits
    if not re.fullmatch(r'55\d{10,11}', digits):
        raise AuthError(400, 'Informe seu WhatsApp com DDD.')
    return digits


def validate_password(body):
    password = body.get('password')
    if (not isinstance(password, str) or not 12 <= len(password) <= 128
            or not any(not c.isalnum() and not c.isspace() for c in password)):
        raise AuthError(400, 'A senha precisa ter de 12 a 128 caracteres e pelo menos um caractere especial.')
    if password != body.get('passwordConfirm'):
        raise AuthError(400, 'As senhas precisam ser iguais.')
    return password


def password_hash(body):
    return HASHER.hash(validate_password(body))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class WebAccounts:
    def __init__(self, store):
        self.store, self.db = store, store.db
        self.secret = (os.environ.get('NUTRI_SERVICE_TOKEN') or secrets.token_urlsafe(48)).encode()
        self.base_url = os.environ.get('EVOLUTION_API_URL', '').rstrip('/')
        self.api_key = os.environ.get('EVOLUTION_API_KEY', '')
        self.instance = os.environ.get('EVOLUTION_INSTANCE', 'nutri')
        parsed = urlsplit(self.base_url)
        self.configured = bool(parsed.scheme == 'https' and parsed.hostname and not parsed.username
                               and not parsed.query and not parsed.fragment and parsed.path in ('', '/')
                               and self.api_key and not self.api_key.startswith('CHANGE_ME'))
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS web_accounts (
            id TEXT PRIMARY KEY, patient_id TEXT UNIQUE NOT NULL REFERENCES patients(id),
            phone TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS web_sessions (
            token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES web_accounts(id),
            expires REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS web_challenges (
            id TEXT PRIMARY KEY, phone TEXT NOT NULL, purpose TEXT NOT NULL,
            code_hash TEXT NOT NULL, password_hash TEXT, profile TEXT,
            account_id TEXT REFERENCES web_accounts(id), created REAL NOT NULL,
            expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            used INTEGER NOT NULL DEFAULT 0, delivery TEXT NOT NULL DEFAULT 'pending',
            sends INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS web_auth_attempts (
            bucket TEXT NOT NULL, created REAL NOT NULL);
          CREATE INDEX IF NOT EXISTS web_auth_attempt_time ON web_auth_attempts(bucket, created);
          CREATE TABLE IF NOT EXISTS web_library (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            kind TEXT NOT NULL, name TEXT NOT NULL, foods TEXT NOT NULL, created REAL NOT NULL);
        ''')
        self.db.commit()

    def code(self, challenge_id):
        value = hmac.new(self.secret, ('web-otp:' + challenge_id).encode(), hashlib.sha256).digest()
        return f'{int.from_bytes(value[:8], "big") % 1000000:06d}'

    def code_digest(self, challenge_id, code):
        return hmac.new(self.secret, ('verify:' + challenge_id + ':' + code).encode(), hashlib.sha256).hexdigest()

    def throttle(self, action, phone, maximum, window):
        bucket = action + ':' + digest(phone)
        count = self.db.execute('SELECT count(*) FROM web_auth_attempts WHERE bucket=? AND created>?',
                                (bucket, time.time()-window)).fetchone()[0]
        if count >= maximum:
            raise AuthError(429, 'Muitas tentativas. Aguarde alguns minutos e tente novamente.')
        self.db.execute('INSERT INTO web_auth_attempts VALUES (?,?)', (bucket, time.time()))

    def start(self, purpose, body):
        if not self.configured:
            raise AuthError(503, 'A confirmação por WhatsApp está indisponível. Tente novamente em instantes.')
        phone = phone_number(body.get('phone'))
        profile, hashed = None, None
        password = None
        if purpose == 'signup':
            password = validate_password(body)
            if body.get('consent') is not True:
                raise AuthError(400, 'Autorize o acompanhamento pelo WhatsApp para criar a conta.')
            profile = validate_profile(body.get('profile', {}))
            if any(key not in profile for key in ('birthday', 'gender', 'heightCm', 'weightKg', 'goal', 'activityLevel')):
                raise AuthError(400, 'Preencha seu perfil antes de criar a conta.')
        with self.store.lock, self.db:
            self.throttle('request-code:' + purpose, phone, 1, 60)
            self.throttle('request-hour', phone, 5, 3600)
        if purpose == 'signup':
            hashed = HASHER.hash(password)
        challenge_id = secrets.token_urlsafe(32)
        code = self.code(challenge_id)
        now = time.time()
        with self.store.lock, self.db:
            account = self.db.execute('SELECT id FROM web_accounts WHERE phone=?', (phone,)).fetchone()
            # Keep the response identical for known and unknown recovery accounts.
            delivery = 'pending' if purpose == 'signup' or account else 'unavailable'
            self.db.execute("UPDATE web_challenges SET used=1 WHERE phone=? AND purpose=? AND used=0",
                            (phone, purpose))
            self.db.execute('''INSERT INTO web_challenges
                (id,phone,purpose,code_hash,password_hash,profile,account_id,created,expires,delivery)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (challenge_id, phone, purpose, self.code_digest(challenge_id, code), hashed,
                 json.dumps(profile, ensure_ascii=False) if profile else None,
                 account['id'] if account else None, now, now+600, delivery))
        return {'challengeId': challenge_id, 'expiresInSeconds': 600,
                'message': 'Se o número puder ser usado nesta solicitação, você receberá um código no WhatsApp.'}

    def verify(self, purpose, body):
        challenge_id, code = body.get('challengeId'), body.get('code')
        if not isinstance(challenge_id, str) or not isinstance(code, str) or not re.fullmatch(r'\d{6}', code):
            raise AuthError(400, 'Código inválido ou expirado.')
        # Commit failed attempts as well, so retries cannot roll back the limit.
        with self.store.lock, self.db:
            row = self.db.execute('SELECT * FROM web_challenges WHERE id=? AND purpose=?',
                                  (challenge_id, purpose)).fetchone()
            valid = bool(row and not row['used'] and row['expires'] > time.time()
                         and row['attempts'] < 5 and row['delivery'] != 'unavailable')
            if valid:
                self.db.execute('UPDATE web_challenges SET attempts=attempts+1 WHERE id=?', (challenge_id,))
                valid = hmac.compare_digest(row['code_hash'], self.code_digest(challenge_id, code))
        if not valid:
            raise AuthError(400, 'Código inválido ou expirado.')
        hashed = password_hash(body) if purpose == 'reset' else row['password_hash']
        with self.store.lock, self.db:
            claimed = self.db.execute('''UPDATE web_challenges SET used=1,password_hash=NULL
                WHERE id=? AND used=0 AND expires>?''', (challenge_id, time.time())).rowcount
            if not claimed:
                raise AuthError(400, 'Código inválido ou expirado.')
            account = self.db.execute('SELECT * FROM web_accounts WHERE phone=?', (row['phone'],)).fetchone()
            if purpose == 'reset':
                if not account or row['account_id'] != account['id']:
                    raise AuthError(400, 'Código inválido ou expirado.')
                self.db.execute('UPDATE web_accounts SET password_hash=? WHERE id=?', (hashed, account['id']))
                self.db.execute('DELETE FROM web_sessions WHERE account_id=?', (account['id'],))
                return {'message': 'Senha atualizada. Entre com seu WhatsApp e sua nova senha.'}, None
            if account:
                # The proof of phone ownership permits a clear account-exists message.
                return {'accountExists': True, 'message': 'Este número já tem conta. Entre ou use Esqueci minha senha.'}, None
            patient_id = self.attach_patient(row['phone'], json.loads(row['profile']))
            account_id = str(uuid.uuid4())
            self.db.execute('INSERT INTO web_accounts VALUES(?,?,?,?,?)',
                            (account_id, patient_id, row['phone'], hashed, time.time()))
            return {'message': 'Conta criada e WhatsApp confirmado.'}, self.new_session(account_id)

    def resend(self, body):
        if not self.configured:
            raise AuthError(503, 'A confirmação por WhatsApp está indisponível.')
        with self.store.lock, self.db:
            row = self.db.execute('SELECT * FROM web_challenges WHERE id=? AND used=0 AND expires>?',
                                  (body.get('challengeId'), time.time())).fetchone()
            if not row:
                raise AuthError(400, 'Código expirado. Inicie uma nova solicitação.')
            self.throttle('request-code:' + row['purpose'], row['phone'], 1, 60)
            self.throttle('request-hour', row['phone'], 5, 3600)
            if row['delivery'] != 'unavailable':
                self.db.execute("UPDATE web_challenges SET delivery='pending',sends=0,next_at=0 WHERE id=?", (row['id'],))
        return {'message': 'Se o número estiver vinculado à solicitação, o código será reenviado.'}

    def attach_patient(self, phone, profile):
        patient = self.db.execute('SELECT * FROM patients WHERE phone=? ORDER BY verified DESC,created DESC LIMIT 1',
                                 (phone,)).fetchone()
        patient_id = patient['id'] if patient else str(uuid.uuid4())
        at = datetime.now(timezone.utc).isoformat()
        event_id = 'registration:' + str(uuid.uuid4())
        if patient:
            context = json.loads(patient['context'])
            # Existing account data and diary take priority over signup defaults.
            if not context.get('appProfile'):
                context.update(profile_context(profile))
            self.db.execute('''UPDATE patients SET verified=1,consent=1,consent_at=?,consent_version=?,
                code_hash=NULL,context=?,registration_id=? WHERE id=?''',
                (at, 'garfofala-web-account-v1', json.dumps(context, ensure_ascii=False), event_id, patient_id))
        else:
            self.db.execute('''INSERT INTO patients
                (id,token_hash,phone,consent,consent_at,consent_version,verified,created,registration_id,context)
                VALUES(?,?,?,1,?,?,1,?,?,?)''',
                (patient_id, digest(secrets.token_urlsafe(48)), phone, at, 'garfofala-web-account-v1',
                 time.time(), event_id, json.dumps(profile_context(profile), ensure_ascii=False)))
        self.db.execute('UPDATE patients SET verified=0,consent=0,code_hash=NULL WHERE phone=? AND id<>?',
                        (phone, patient_id))
        event = {'eventId': event_id, 'userId': patient_id, 'phone': phone,
                 'consent': {'granted': True, 'at': at, 'version': 'garfofala-web-account-v1'}}
        self.db.execute('INSERT INTO notifications(id,body) VALUES(?,?)', (event_id, json.dumps(event)))
        return patient_id

    def link_installation(self, pending):
        """Keep web history attached when the phone owner reinstalls Android."""
        account = self.db.execute('SELECT patient_id FROM web_accounts WHERE phone=?', (pending['phone'],)).fetchone()
        if not account or account['patient_id'] == pending['id']:
            return pending
        patient = self.db.execute('SELECT * FROM patients WHERE id=?', (account['patient_id'],)).fetchone()
        context = json.loads(patient['context'])
        context.update(json.loads(pending['context']))
        self.db.execute('UPDATE patients SET token_hash=?,consent=0,verified=0,code_hash=NULL WHERE id=?',
                        (digest(secrets.token_urlsafe(48)), pending['id']))
        self.db.execute('''UPDATE patients SET token_hash=?,verified=1,consent=1,context=?,
            consent_at=?,consent_version=?,code_hash=NULL WHERE id=?''',
            (pending['token_hash'], json.dumps(context, ensure_ascii=False), pending['consent_at'],
             pending['consent_version'], patient['id']))
        return self.db.execute('SELECT * FROM patients WHERE id=?', (patient['id'],)).fetchone()

    def new_session(self, account_id):
        token = secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO web_sessions VALUES(?,?,?)',
                        (digest(token), account_id, time.time()+SESSION_SECONDS))
        return token

    def login(self, body):
        phone = phone_number(body.get('phone'))
        password = body.get('password')
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise AuthError(401, 'WhatsApp ou senha inválidos.')
        with self.store.lock:
            with self.db:
                self.throttle('login', phone, 10, 900)
            account = self.db.execute('SELECT * FROM web_accounts WHERE phone=?', (phone,)).fetchone()
            try:
                valid = HASHER.verify(account['password_hash'] if account else DUMMY_HASH, password)
            except (VerificationError, InvalidHashError):
                valid = False
            if not account or not valid:
                raise AuthError(401, 'WhatsApp ou senha inválidos.')
            with self.db:
                if HASHER.check_needs_rehash(account['password_hash']):
                    self.db.execute('UPDATE web_accounts SET password_hash=? WHERE id=?',
                                    (HASHER.hash(password), account['id']))
                return self.new_session(account['id'])

    def patient(self, token):
        with self.store.lock:
            row = self.db.execute('''SELECT p.* FROM web_sessions s JOIN web_accounts a ON a.id=s.account_id
                JOIN patients p ON p.id=a.patient_id WHERE s.token_hash=? AND s.expires>?''',
                (digest(token), time.time())).fetchone()
        if not row:
            raise AuthError(401, 'Entre na sua conta para continuar.')
        return row

    def logout(self, token):
        with self.store.lock, self.db:
            self.db.execute('DELETE FROM web_sessions WHERE token_hash=?', (digest(token),))
        return {'ok': True}

    def deliver_once(self):
        if not self.configured:
            return
        now = time.time()
        with self.store.lock, self.db:
            row = self.db.execute('''SELECT * FROM web_challenges WHERE used=0 AND expires>?
                AND attempts<5 AND delivery IN ('pending','sending') AND next_at<=? AND sends<3 ORDER BY created LIMIT 1''',
                (now, now)).fetchone()
            if not row:
                return
            self.db.execute("UPDATE web_challenges SET delivery='sending',sends=sends+1,next_at=? WHERE id=?",
                            (now+60, row['id']))
        action = 'confirmar seu cadastro' if row['purpose'] == 'signup' else 'redefinir sua senha'
        text = f'GarfoFala: seu código para {action} é {self.code(row["id"])}. Válido por 10 minutos. Digite somente no site da GarfoFala. Se não solicitou, ignore esta mensagem.'
        success = False
        try:
            request = Request(self.base_url+'/message/sendText/'+quote(self.instance, safe=''),
                              data=json.dumps({'number': row['phone'], 'text': text, 'linkPreview': False}).encode(),
                              headers={'Content-Type': 'application/json', 'apikey': self.api_key}, method='POST')
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read(100000))
                success = 200 <= response.status < 300 and bool(data.get('key', {}).get('id'))
            print('WEB_OTP: aceito pela Evolution.' if success else
                  'WEB_OTP: Evolution respondeu sem confirmar o envio.', flush=True)
        except HTTPError as error:
            print(f'WEB_OTP: Evolution recusou o envio (HTTP {error.code}).', flush=True)
        except (URLError, TimeoutError):
            print('WEB_OTP: falha de conexão com a Evolution. Confira endereço, DNS e HTTPS.', flush=True)
        except Exception as error:
            print(f'WEB_OTP: falha ao preparar ou interpretar o envio ({type(error).__name__}).', flush=True)
        with self.store.lock, self.db:
            self.db.execute('UPDATE web_challenges SET delivery=?,next_at=? WHERE id=?',
                            ('sent' if success else 'pending', time.time()+30, row['id']))

    def cleanup(self):
        now = time.time()
        self.db.execute('DELETE FROM web_sessions WHERE expires<?', (now,))
        self.db.execute('DELETE FROM web_challenges WHERE created<?', (now-86400,))
        self.db.execute('DELETE FROM web_auth_attempts WHERE created<?', (now-86400,))
