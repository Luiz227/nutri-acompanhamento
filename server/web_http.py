"""Same-origin website and cookie-authenticated web API."""
import json
import os
from datetime import date, datetime
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from coaching import BRASILIA
from daily_progress import diary_rows, summarize
from web_accounts import AuthError, SESSION_SECONDS
from web_features import feature_request

COOKIE = '__Host-garfofala_session'
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/entrar': ('index.html', 'text/html; charset=utf-8'),
          '/recuperar-senha': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
          '/profile.mjs': ('profile.mjs', 'application/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8'),
          '/garfofala-logo.png': ('garfofala-logo.png', 'image/png'),
          '/prato.webp': ('prato.webp', 'image/webp')}
SECURITY = {
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
    'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


def session_cookie(token, clear=False):
    return (f'{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Lax; '
            f'Max-Age={0 if clear else SESSION_SECONDS}')


def serve_static(handler, path):
    if path not in STATIC:
        return False
    if handler.command != 'GET':
        raise AuthError(405, 'Método não permitido.')
    filename, mime = STATIC[path]
    directory = Path(__file__).with_name('web')
    if not directory.is_dir():
        directory = Path(__file__).parent.parent / 'web'
    file = directory / filename
    if not file.is_file():
        raise AuthError(503, 'A página está sendo preparada. Tente novamente.')
    content = file.read_bytes()
    handler.send_response(200)
    handler.send_header('Content-Type', mime)
    handler.send_header('Content-Length', str(len(content)))
    for key, value in SECURITY.items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(content)
    return True


def handle_web(handler, store, path, body):
    if not path.startswith('/web-api/'):
        return False
    auth = store.web
    if handler.command != 'GET':
        origin = handler.headers.get('Origin', '').rstrip('/')
        expected = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
        if expected:
            valid_origin = origin == expected
        else:
            parsed = urlsplit(origin)
            valid_origin = parsed.scheme in ('http', 'https') and parsed.netloc.lower() == handler.headers.get('Host', '').lower()
        if not valid_origin:
            raise AuthError(403, 'Atualize a página e tente novamente.')
        if not handler.headers.get('Content-Type', '').startswith('application/json'):
            raise AuthError(415, 'Envie os dados no formato JSON.')
    try:
        cookie = SimpleCookie()
        cookie.load(handler.headers.get('Cookie', ''))
        token = cookie[COOKIE].value if COOKIE in cookie else ''
    except CookieError:
        token = ''
    data, new_cookie = None, None
    feature_paths = {'/web-api/evolution', '/web-api/profile', '/web-api/preferences', '/web-api/foods',
                     '/web-api/entry', '/web-api/remove-entry', '/web-api/export',
                     '/web-api/library', '/web-api/library-remove', '/web-api/library-log'}
    if path in feature_paths:
        with store.lock, store.db:
            patient = auth.patient(token)
            data = feature_request(store, patient, path, handler.command, body, parse_qs(urlsplit(handler.path).query))
            if data is None:
                raise AuthError(405, 'Método não permitido.')
        handler.reply(200, data)
        return True
    if path in ('/web-api/signup', '/web-api/forgot-password') and handler.command == 'POST':
        data = auth.start('signup' if path.endswith('signup') else 'reset', body)
    elif path in ('/web-api/verify-signup', '/web-api/reset-password') and handler.command == 'POST':
        data, session = auth.verify('signup' if path.endswith('verify-signup') else 'reset', body)
        if session:
            new_cookie = session_cookie(session)
        elif path.endswith('reset-password'):
            new_cookie = session_cookie('', clear=True)
    elif path == '/web-api/login' and handler.command == 'POST':
        new_cookie = session_cookie(auth.login(body))
        data = {'message': 'Você entrou na sua conta.'}
    elif path == '/web-api/resend-code' and handler.command == 'POST':
        data = auth.resend(body)
    elif path == '/web-api/logout' and handler.command == 'POST':
        data = auth.logout(token)
        new_cookie = session_cookie('', clear=True)
    elif path == '/web-api/me' and handler.command == 'GET':
        patient = auth.patient(token)
        with store.lock:
            preferences = store.coaching.get(patient['id']) or {}
            day = datetime.now(BRASILIA).date()
            totals, missing, estimated = summarize(record for _, record in diary_rows(store.db, patient['id'], day))
        data = {'phone': patient['phone'], 'verified': bool(patient['verified']),
                'consentActive': bool(patient['consent']),
                'displayName': preferences.get('name') or '',
                'profile': json.loads(patient['context']).get('appProfile', {}),
                'today': {'date': day.isoformat(), 'totals': totals, 'missing': sorted(missing),
                          'estimated': estimated}}
    elif path == '/web-api/records' and handler.command == 'GET':
        patient = auth.patient(token)
        query = parse_qs(urlsplit(handler.path).query)
        if 'day' in query:
            selected = date.fromisoformat(query['day'][0])
            with store.lock:
                rows = store.db.execute("SELECT id,payload FROM records WHERE patient_id=? AND status='confirmed'", (patient['id'],)).fetchall()
                records = [{'id': row['id'], **json.loads(row['payload'])} for row in rows
                           if datetime.fromisoformat(json.loads(row['payload'])['occurredAt']).astimezone(BRASILIA).date() == selected]
            records.sort(key=lambda record: record['occurredAt'])
            handler.reply(200, {'date': selected.isoformat(), 'records': records})
            return True
        cursor = int(query.get('after', ['0'])[0])
        if cursor < 0:
            raise AuthError(400, 'Cursor inválido.')
        with store.lock:
            data = store.records.list(patient['id'], cursor, revisions=True, removals=True)
    else:
        raise AuthError(404, 'Página não encontrada.')
    handler.reply(200, data, {'Set-Cookie': new_cookie} if new_cookie else None)
    return True
