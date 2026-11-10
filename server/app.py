"""Test deployment bridge for OpenNutriTracker, GPL-3.0. PDFs generated with ReportLab."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import parse_qs, urlsplit
from records import Records
from coaching import Coaching
from messaging import Messaging
from menu_coach import MenuCoach, MENU_READY
from patient_profile import validate_profile, profile_context
from meal_pdf import eligible, make_pdf, MENU_REQUEST_TEXT

PILOT_REPLY = 'Recebi sua mensagem. Nesta versão de teste posso ajudar com o diário alimentar: registre os alimentos e os pesos em gramas no aplicativo. Para mudar seu plano ou tratar dúvidas de saúde, converse com seu nutricionista. Para interromper as mensagens, envie SAIR.'


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, path, allow_ai=False):
        self.allow_ai = allow_ai
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, phone TEXT NOT NULL,
            consent INTEGER NOT NULL, consent_at TEXT NOT NULL, consent_version TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0, code_hash TEXT, code_until REAL,
            attempts INTEGER NOT NULL DEFAULT 0, context TEXT NOT NULL DEFAULT '{}',
            created REAL NOT NULL, registration_id TEXT NOT NULL);
          CREATE UNIQUE INDEX IF NOT EXISTS verified_phone ON patients(phone) WHERE verified=1;
          CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            action TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', optout INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS dispatches (
            id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL REFERENCES events(id),
            patient_id TEXT NOT NULL REFERENCES patients(id), status TEXT NOT NULL,
            provider_id TEXT, created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            role TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0);
        ''')
        self.db.commit()
        self.records = Records(self.db)
        self.coaching = Coaching(self.db)
        self.messaging = Messaging(self)
        self.menu = MenuCoach(self.db)

    def enroll(self, body):
        phone = re.sub(r'[\s()+.-]', '', str(body.get('phone', '')))
        consent = body.get('consent', {})
        if not re.fullmatch(r'55\d{10,11}', phone):
            raise Problem(400, 'Informe DDI 55, DDD e o número do WhatsApp.')
        if consent.get('granted') is not True:
            raise Problem(400, 'Autorize o acompanhamento para conectar o WhatsApp.')
        version = str(consent.get('version', ''))[:80]
        if not version:
            raise Problem(400, 'Versão do consentimento obrigatória.')
        now = time.time()
        token = body.get('appToken') or secrets.token_urlsafe(40)
        code = body.get('pairingCode') or str(secrets.randbelow(900000) + 100000)
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,128}', token) or not isinstance(code, str) or not re.fullmatch(r'\d{6}', code):
            raise Problem(400, 'Credencial de instalação inválida.')
        user_id = str(uuid.uuid4())
        event_id = 'registration:' + str(uuid.uuid4())
        at = datetime.now(timezone.utc).isoformat()
        with self.lock, self.db:
            existing = self.db.execute('SELECT * FROM patients WHERE token_hash=?', (digest(token),)).fetchone()
            if existing:
                if existing['phone'] != phone:
                    raise Problem(409, 'Esta instalação já está vinculada a outro telefone.')
                valid_code = existing['code_hash'] and hmac.compare_digest(existing['code_hash'], digest(code))
                return {'userId': existing['id'], 'token': token, 'pairingCode': code if valid_code else None,
                        'expiresInSeconds': max(0, int(existing['code_until'] - now)),
                        'verified': bool(existing['verified']), 'consentActive': bool(existing['consent'])}
            # Global cap is deliberately conservative for a small pilot.
            recent = self.db.execute('SELECT count(*) FROM patients WHERE created>?', (now - 3600,)).fetchone()[0]
            same = self.db.execute('SELECT count(*) FROM patients WHERE phone=? AND created>?', (phone, now - 3600)).fetchone()[0]
            if recent >= 30 or same >= 3:
                raise Problem(429, 'Limite de solicitações. Tente novamente mais tarde.')
            self.db.execute('INSERT INTO patients(id,token_hash,phone,consent,consent_at,consent_version,code_hash,code_until,created,registration_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (user_id, digest(token), phone, 1, at, version, digest(code), now + 600, now, event_id))
            profile = validate_profile(body.get('profile', {}))
            self.db.execute('UPDATE patients SET context=? WHERE id=?',
                (json.dumps(profile_context(profile),ensure_ascii=False),user_id))
            event = {'eventId': event_id, 'userId': user_id, 'phone': phone,
                     'consent': {'granted': True, 'at': at, 'version': version}}
            self.db.execute('INSERT INTO notifications(id,body) VALUES(?,?)', (event_id, json.dumps(event)))
        return {'userId': user_id, 'token': token, 'pairingCode': code, 'expiresInSeconds': 600,
                'verified': False, 'consentActive': True}

    def patient(self, token):
        with self.lock:
            row = self.db.execute('SELECT * FROM patients WHERE token_hash=?', (digest(token),)).fetchone()
        if not row:
            raise Problem(401, 'Conexão não autorizada. Conecte o WhatsApp novamente.')
        return dict(row)

    def me(self, token):
        p = self.patient(token)
        return {'userId': p['id'], 'phone': p['phone'], 'verified': bool(p['verified']),
                'consentActive': bool(p['consent']), 'context': json.loads(p['context'])}

    def revoke(self, token):
        p = self.patient(token)
        with self.lock, self.db:
            self.db.execute('UPDATE patients SET consent=0, code_hash=NULL WHERE id=?', (p['id'],))
        return {'ok': True, 'consentActive': False}

    def context(self, token, body):
        p = self.patient(token)
        if not p['consent']:
            raise Problem(403, 'A autorização de acompanhamento está cancelada.')
        context = json.loads(p['context'])
        if 'profile' in body:
            profile = validate_profile(body['profile'])
            context.update(profile_context(profile))
        # The device cannot label a self-entered diet as clinician-approved.
        for key in ('displayName', 'recentDiarySummary'):
            if isinstance(body.get(key), str):
                context[key] = body[key][:1500]
        with self.lock, self.db:
            self.db.execute('UPDATE patients SET context=? WHERE id=?', (json.dumps(context), p['id']))
        return {'ok': True, 'profileUpdated': 'profile' in body}

    def ingest(self, event, instance):
        with self.lock, self.db:
            return self._ingest(event, instance)

    def _ingest(self, event, instance):
        if not isinstance(event, dict):
            raise Problem(400, 'Evento inválido.')
        if event.get('kind') == 'incoming' and event.get('instance') != instance:
            return {'action': 'ignore'}
        event_id = event.get('eventId', '')
        if not isinstance(event_id, str) or not 8 <= len(event_id) <= 300:
            raise Problem(400, 'Evento inválido.')
        old = self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
        if old:
            reserved = self.db.execute('SELECT id FROM dispatches WHERE event_id=?', (event_id,)).fetchone()
            if reserved:
                return {'action': 'ignore'}
            p = self.db.execute('SELECT * FROM patients WHERE id=?', (old['patient_id'],)).fetchone()
            if not p or event.get('phone') != p['phone'] or (event.get('kind') == 'registration' and event.get('userId') != p['id']):
                return {'action': 'ignore'}
            return self._job(p, event_id, old['action'], old['text'], bool(old['optout']))
        if event.get('kind') == 'reminder':
            p = self.db.execute('SELECT * FROM patients WHERE id=? AND phone=? AND consent=1 AND verified=1',
                                (event.get('userId'), event.get('phone'))).fetchone()
            text = self.coaching.reminder(event_id, p['id']) if p else None
            if not text:
                return {'action': 'ignore'}
            action, optout = 'reply', False
        elif event.get('kind') == 'registration':
            p = self.db.execute('SELECT * FROM patients WHERE id=? AND registration_id=?',
                (event.get('userId'), event_id)).fetchone()
            if not p or p['phone'] != event.get('phone') or not p['consent']:
                return {'action': 'ignore'}
            action, text, optout = 'welcome', '', False
        elif event.get('kind') == 'incoming' and event.get('instance') == instance:
            phone, text = event.get('phone', ''), str(event.get('text', '')).strip()
            if not re.fullmatch(r'55\d{10,11}', phone) or len(text) > 16000:
                return {'action': 'ignore'}
            stop = text.upper() in ('SAIR', 'PARAR', 'CANCELAR', 'STOP')
            if stop:
                patients = self.db.execute('SELECT * FROM patients WHERE phone=? AND consent=1 ORDER BY verified DESC,created DESC', (phone,)).fetchall()
                if not patients:
                    return {'action': 'ignore'}
                p = patients[0]
                self.db.execute('UPDATE patients SET consent=0,code_hash=NULL WHERE phone=?', (phone,))
                p = self.db.execute('SELECT * FROM patients WHERE id=?', (p['id'],)).fetchone()
                action, text, optout = 'reply', 'As mensagens de acompanhamento foram interrompidas.', True
            else:
                # A live code may connect a new authenticated app installation.
                # Invalidate any old verified link only after matching the code.
                pending = self.db.execute('SELECT * FROM patients WHERE phone=? AND consent=1 AND verified=0 AND code_until>? AND attempts<5 ORDER BY created DESC', (phone, time.time())).fetchall()
                matching = next((r for r in pending if hmac.compare_digest(r['code_hash'] or '', digest(text))), None)
                if matching:
                    p = matching
                    self.db.execute('UPDATE patients SET consent=0, verified=0,code_hash=NULL WHERE phone=? AND id<>?', (phone, p['id']))
                    self.db.execute('UPDATE patients SET verified=1,code_hash=NULL WHERE id=?', (p['id'],))
                    p = self.db.execute('SELECT * FROM patients WHERE id=?', (p['id'],)).fetchone()
                    action, text, optout = 'reply', self.coaching.start(p['id']), False
                else:
                    p = self.db.execute('SELECT * FROM patients WHERE phone=? AND verified=1 AND consent=1', (phone,)).fetchone()
                    if not p:
                        if pending:
                            self.db.execute('UPDATE patients SET attempts=attempts+1 WHERE phone=? AND verified=0', (phone,))
                        return {'action': 'ignore'}
                    action, optout = 'assistant', False
                    before_coaching = self.coaching.get(p['id'])
                    coaching_reply = self.coaching.handle(p['id'], text) if text.upper() not in ('CONFIRMAR', 'CANCELAR REGISTRO') else None
                    if coaching_reply and before_coaching and before_coaching['stage'] == 'reminders' and self.coaching.get(p['id'])['stage'] == 'done':
                        invitation = self.menu.offer(p['id'])
                        if invitation:
                            coaching_reply += '\n\n' + invitation
                    if coaching_reply is None:
                        menu_reply = self.menu.handle(p['id'], text)
                        if menu_reply == MENU_READY:
                            text = MENU_REQUEST_TEXT
                        else:
                            coaching_reply = menu_reply

                    if text.upper() in ('CONFIRMAR', 'CANCELAR REGISTRO'):
                        action, text = 'reply', self.records.confirm(p['id'], text.upper() == 'CONFIRMAR')
                    elif coaching_reply is not None:
                        action, text = 'reply', coaching_reply
                    elif re.search(r'\b(rem[eé]dio|medicamento|dose|dosagem|suplemento|prescreva|prescri[cç][aã]o)\b', text, re.I):
                        action, text = 'reply', 'Para dúvidas clínicas, sintomas, medicamentos ou suplementos, procure seu nutricionista ou profissional de saúde. A assistente virtual ajuda somente com o diário alimentar e hábitos gerais.'
                    elif not self.allow_ai:
                        action, text = 'reply', PILOT_REPLY
        else:
            return {'action': 'ignore'}
        self.db.execute('INSERT INTO events(id,patient_id,action,text,optout,created) VALUES(?,?,?,?,?,?)',
            (event_id, p['id'], action, text, int(optout), time.time()))
        return self._job(p, event_id, action, text, optout)

    def _job(self, p, event_id, action, text, optout):
        if not p or (not p['consent'] and not optout):
            return {'action': 'ignore'}
        if action == 'assistant' and not self.allow_ai:
            action, text = 'reply', PILOT_REPLY
        history = self.db.execute('SELECT role,content FROM history WHERE patient_id=? ORDER BY id DESC LIMIT 8', (p['id'],)).fetchall()
        context = json.loads(p['context']) if p['verified'] else {}
        preferences = self.coaching.get(p['id']) if p['verified'] else None
        if preferences:
            context.update(displayName=preferences['name'] or '',
                           waterReminders='Ativados: ' + preferences['hours'] if preferences['reminders'] else 'Desativados')
        recent = self.db.execute("SELECT payload FROM records WHERE patient_id=? AND status='confirmed' ORDER BY seq DESC LIMIT 12", (p['id'],)).fetchall() if p['verified'] else []
        if recent:
            context['recentDiarySummary'] = json.dumps([{k: v for k, v in json.loads(r['payload']).items() if k in ('kind', 'text', 'quantity', 'unit', 'occurredAt', 'mealType')} for r in reversed(recent)], ensure_ascii=False)
        menu_profile = self.menu.get(p['id']) if p['verified'] else None
        if menu_profile:
            context['menuPreferences'] = json.dumps(menu_profile, ensure_ascii=False)
        return {'eventId': event_id, 'userId': p['id'], 'phone': p['phone'], 'action': action,
                'verified': bool(p['verified']), 'consentActive': bool(p['consent']),
                'optOutPersisted': optout, 'text': text, 'message': text,
                'documentRequested': action == 'assistant' and text == MENU_REQUEST_TEXT and eligible(menu_profile, context.get('appProfile',{}),text),
                'context': context,
                'history': [dict(r) for r in reversed(history)] if p['verified'] else [],
                'catalogueCandidates': self.records.candidates(' '.join(
                    r['content'] for r in reversed(history) if r['role'] == 'user') + ' ' + text) if action == 'assistant' else [],
                'currentTime': datetime.now(timezone(timedelta(hours=-3))).isoformat()}

    def reserve(self, body, instance):
        with self.lock, self.db:
            event = self.db.execute('SELECT * FROM events WHERE id=?', (body.get('eventId'),)).fetchone()
            if not event or event['patient_id'] != body.get('userId'):
                raise Problem(403, 'Evento não autorizado.')
            p = self.db.execute('SELECT * FROM patients WHERE id=?', (event['patient_id'],)).fetchone()
            if not p or p['phone'] != body.get('phone'):
                raise Problem(403, 'Destinatário inválido.')
            if self.db.execute('SELECT id FROM dispatches WHERE event_id=?', (event['id'],)).fetchone():
                return {'approved': False}
            count = self.db.execute('SELECT count(*) FROM dispatches WHERE patient_id=? AND created>?', (p['id'], time.time() - 3600)).fetchone()[0]
            if count >= 20 and not event['optout']:
                return {'approved': False}
            if event['id'].startswith('reminder:') and not self.coaching.reminder(event['id'], p['id']):
                return {'approved': False}
            document = None
            if event['optout']:
                if p['consent']:
                    return {'approved': False}
                text = 'As mensagens de acompanhamento foram interrompidas. Você pode gerenciar sua autorização no aplicativo.'
            else:
                if not p['consent'] or (event['action'] != 'welcome' and not p['verified']):
                    return {'approved': False}
                # Keep automated clinical changes out of this test release.
                # Assistant responses are a fixed low-risk acknowledgement.
                # Enabling unrestricted model text needs a clinician review queue.
                if event['action'] == 'assistant':
                    candidate = body.get('candidate')
                    text = candidate.strip() if self.allow_ai and isinstance(candidate, str) and 0 < len(candidate.strip()) <= 1800 else PILOT_REPLY
                    job = self._job(p, event['id'], event['action'], event['text'], False)
                    if self.allow_ai and job.get('documentRequested'):
                        try:
                            document = make_pdf(body.get('plan'), job['context'].get('displayName'), job['context'].get('appProfile',{}), self.menu.get(p['id']))
                            text = 'Preparei seu guia com sugestões para a sua rotina. Vou enviar o PDF logo abaixo. As ideias são flexíveis e não alteram suas metas no aplicativo.'
                        except (ValueError, TypeError, OverflowError):
                            text = 'Não consegui organizar o PDF desta vez. Pode me pedir para gerar o guia novamente?'
                    elif self.allow_ai and body.get('record') is not None:
                        try:
                            text = self.records.propose(p['id'], event['id'], body['record'], auto_save=True)
                            items = body['record'] if isinstance(body['record'], list) else [body['record']]
                            if any(isinstance(r, dict) and r.get('kind') == 'meal' for r in items) and len(text) < 1640:
                                invitation = self.menu.offer(p['id'])
                                if invitation:
                                    text += '\n\n' + invitation
                        except (ValueError, TypeError, OverflowError):
                            text = 'Antes de registrar, preciso confirmar os dados: refeições em gramas, água em ml/l, peso em kg/g, ou o texto da observação. Pode informar novamente?'
                elif event['action'] == 'reply':
                    text = event['text']
                else:
                    text = 'Olá! Sou a assistente virtual de acompanhamento nutricional do aplicativo. Para confirmar a conexão, envie o código exibido no aplicativo. Se não foi você quem solicitou, envie SAIR.'
            dispatch_id = 'dispatch:' + str(uuid.uuid4())
            self.db.execute('INSERT INTO dispatches(id,event_id,patient_id,status,created) VALUES(?,?,?,?,?)',
                (dispatch_id, event['id'], p['id'], 'reserved', time.time()))
            # Save deterministic, authorized replies only; model candidates are not stored.
            if event['action'] == 'assistant':
                self.db.execute('INSERT INTO history(patient_id,role,content,created) VALUES(?,?,?,?)', (p['id'], 'user', event['text'], time.time()))
            self.db.execute('INSERT INTO history(patient_id,role,content,created) VALUES(?,?,?,?)', (p['id'], 'assistant', text, time.time()))
            expires = datetime.fromtimestamp(time.time() + 30, timezone.utc).isoformat()
            return {'approved': True, 'dispatchId': dispatch_id, 'eventId': event['id'],
                    'userId': p['id'], 'phone': p['phone'], 'instance': instance, 'text': text, 'expiresAt': expires,
                    'parts': self.messaging.prepare(dispatch_id, text, document)}

    def result(self, body):
        if body.get('status') not in ('accepted', 'uncertain'):
            raise Problem(400, 'Estado inválido.')
        with self.lock, self.db:
            row = self.db.execute('SELECT status FROM dispatches WHERE id=?', (body.get('dispatchId'),)).fetchone()
            if not row:
                raise Problem(404, 'Reserva não encontrada.')
            if row['status'] != 'accepted':
                self.db.execute('UPDATE dispatches SET status=?,provider_id=? WHERE id=?',
                    (body['status'], str(body.get('providerMessageId') or '')[:200], body['dispatchId']))
        return {'ok': True}

    def notify_once(self, webhook, secret):
        if not webhook:
            return
        with self.lock:
            row = self.db.execute("SELECT * FROM notifications WHERE status='pending' AND next_at<=? AND attempts<5 ORDER BY next_at LIMIT 1", (time.time(),)).fetchone()
        if not row:
            return
        if row['id'].startswith('reminder:'):
            with self.lock, self.db:
                data = json.loads(row['body'])
                patient = self.db.execute('SELECT consent,verified FROM patients WHERE id=?', (data['userId'],)).fetchone()
                if not patient or not patient['consent'] or not patient['verified'] or not self.coaching.reminder(row['id'], data['userId']):
                    self.db.execute("UPDATE notifications SET status='cancelled' WHERE id=?", (row['id'],))
                    return
        try:
            req = Request(webhook, data=row['body'].encode(), method='POST',
                          headers={'Content-Type': 'application/json', 'X-Nutri-App-Secret': secret})
            with urlopen(req, timeout=120) as response:
                success = 200 <= response.status < 300
        except Exception:
            success = False
        with self.lock, self.db:
            self.db.execute('UPDATE notifications SET status=?,attempts=attempts+1,next_at=? WHERE id=?',
                ('sent' if success else 'pending', time.time() + min(300, 15 * 2 ** row['attempts']), row['id']))

    def cleanup(self):
        with self.lock, self.db:
            self.db.execute('DELETE FROM history WHERE created<?', (time.time() - 30 * 86400,))
            self.db.execute('DELETE FROM inbox WHERE created<?', (time.time() - 30 * 86400,))
            self.db.execute('DELETE FROM media_jobs WHERE created<?', (time.time() - 30 * 86400,))
            self.db.execute('DELETE FROM dispatch_documents WHERE dispatch_id IN (SELECT id FROM dispatches WHERE created<?)', (time.time() - 30 * 86400,))
            self.db.execute('DELETE FROM dispatch_parts WHERE dispatch_id IN (SELECT id FROM dispatches WHERE created<?)', (time.time() - 30 * 86400,))
            self.db.execute('UPDATE patients SET code_hash=NULL WHERE code_until<?', (time.time(),))


def make_server(store, service_token, instance='nutri', port=8080, n8n_configured=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No health payload, token, phone or query string logging.

        def reply(self, status, data):
            content = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def do_PUT(self):
            self.handle_request()

        def do_DELETE(self):
            self.handle_request()

        def handle_request(self):
            try:
                path = self.path.split('?')[0]
                if path == '/healthz' and self.command == 'GET':
                    return self.reply(200, {'ok': True, 'apiVersion': 8, 'n8nConfigured': n8n_configured, 'mode': 'general-ai' if store.allow_ai else 'pilot-fixed-replies'})
                if path == '/' and self.command == 'GET':
                    return self.reply(200, {'name': 'Nutri Acompanhamento - API de teste', 'source': 'https://github.com/luiz227/nutri-acompanhamento', 'license': 'GPL-3.0'})
                body = {}
                if self.command in ('POST', 'PUT'):
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 20000:
                        raise Problem(413, 'Corpo ausente ou muito grande.')
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise Problem(400, 'JSON inválido.')
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                if path.startswith('/v1/nutri/'):
                    if not service_token or not hmac.compare_digest(token, service_token):
                        raise Problem(401, 'Credencial de serviço inválida.')
                    if self.command != 'POST':
                        raise Problem(405, 'Método não permitido.')
                    if path == '/v1/nutri/media/authorize':
                        data = store.messaging.begin_media(body.get('event', {}), instance)
                    elif path == '/v1/nutri/media/complete':
                        data = store.messaging.finish_media(body, instance)
                    elif path == '/v1/nutri/events/collect':
                        data = store.messaging.collect(body.get('event', {}), instance)
                    elif path == '/v1/nutri/dispatches/part':
                        data = store.messaging.authorize(body, instance)
                    elif path == '/v1/nutri/dispatches/part-result':
                        data = store.messaging.receipt(body)
                    elif path == '/v1/nutri/events/ingest':
                        data = store.ingest(body.get('event', {}), instance)
                    elif path == '/v1/nutri/dispatches/reserve':
                        data = store.reserve(body, instance)
                    elif path == '/v1/nutri/dispatches/result':
                        data = store.result(body)
                    else:
                        raise Problem(404, 'Rota não encontrada.')
                elif path == '/api/v1/enroll' and self.command == 'POST':
                    data = store.enroll(body)
                    data['n8nConfigured'] = n8n_configured
                elif path == '/api/v1/me' and self.command == 'GET':
                    data = store.me(token)
                elif path == '/api/v1/records' and self.command == 'GET':
                    patient = store.patient(token)
                    after = int(parse_qs(urlsplit(self.path).query).get('after', ['0'])[0])
                    if after < 0:
                        raise Problem(400, 'Cursor inválido.')
                    with store.lock:
                        data = store.records.list(patient['id'], after)
                elif path == '/api/v1/whatsapp' and self.command == 'DELETE':
                    data = store.revoke(token)
                elif path == '/api/v1/context' and self.command == 'PUT':
                    data = store.context(token, body)
                else:
                    raise Problem(404, 'Rota não encontrada.')
                self.reply(200, data)
            except Problem as error:
                self.reply(error.status, {'error': error.message})
            except (ValueError, TypeError, KeyError):
                self.reply(400, {'error': 'Dados inválidos.'})
            except Exception:
                self.reply(500, {'error': 'Falha interna. Tente novamente.'})

    return ThreadingHTTPServer(('0.0.0.0', port), Handler)


if __name__ == '__main__':
    service_token = os.environ.get('NUTRI_SERVICE_TOKEN', '')
    if len(service_token) < 32 or service_token.startswith('CHANGE_ME'):
        raise SystemExit('Configure NUTRI_SERVICE_TOKEN com pelo menos 32 caracteres aleatórios.')
    directory = Path(os.environ.get('DATA_DIR', '/data'))
    directory.mkdir(parents=True, exist_ok=True)
    store = Store(str(directory / 'nutri.sqlite3'), os.environ.get('AI_RESPONSES_ENABLED', 'false').lower() == 'true')
    webhook = os.environ.get('N8N_REGISTRATION_WEBHOOK', '')
    secret = os.environ.get('N8N_APP_WEBHOOK_SECRET', '')
    if webhook and (not webhook.startswith('https://') or len(secret) < 32 or secret.startswith('CHANGE_ME')):
        raise SystemExit('Configure o webhook HTTPS do n8n e seu segredo com pelo menos 32 caracteres.')
    def worker():
        while True:
            with store.lock, store.db:
                store.coaching.schedule()
            store.notify_once(webhook, secret)
            store.cleanup()
            time.sleep(5)
    threading.Thread(target=worker, daemon=True).start()
    print('Nutri API iniciada; modo de teste; sem logs de dados pessoais.', flush=True)
    make_server(store, service_token, os.environ.get('EVOLUTION_INSTANCE', 'nutri'),
                int(os.environ.get('PORT', '8080')), bool(webhook)).serve_forever()
