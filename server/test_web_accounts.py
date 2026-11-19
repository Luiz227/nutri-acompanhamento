import json
import os
import threading
import unittest
from http.cookies import SimpleCookie
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_app as fixtures
from app import Store, make_server
from web_accounts import AuthError, digest


class WebAccountTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp
    tearDown = fixtures.BridgeTests.tearDown
    verify = fixtures.BridgeTests.verify
    event = fixtures.BridgeTests.event

    def signup(self, phone='5511988887777'):
        self.store.web.configured = True
        body = {'phone': phone, 'password': 'MinhaSenhaSegura!123', 'passwordConfirm': 'MinhaSenhaSegura!123',
                'consent': True, 'profile': {'birthday': '1990-04-10', 'gender': 'male',
                'heightCm': 170, 'weightKg': 79, 'goal': 'loseWeight', 'activityLevel': 'active'}}
        challenge = self.store.web.start('signup', body)
        response, session = self.store.web.verify('signup', {
            'challengeId': challenge['challengeId'], 'code': self.store.web.code(challenge['challengeId'])})
        return body, response, session

    def test_signup_login_hash_and_cookie_session(self):
        body, _, session = self.signup()
        row = self.store.db.execute('SELECT * FROM web_accounts').fetchone()
        self.assertTrue(row['password_hash'].startswith('$argon2id$'))
        self.assertNotIn(body['password'], row['password_hash'])
        self.assertEqual(self.store.web.patient(session)['phone'], body['phone'])
        self.assertEqual(self.store.db.execute('SELECT token_hash FROM web_sessions').fetchone()[0], digest(session))
        with self.assertRaises(AuthError):
            self.store.web.login({'phone': body['phone'], 'password': 'Senha incorreta!'})
        other = self.store.web.login({'phone': body['phone'], 'password': body['password']})
        self.assertEqual(self.store.web.patient(other)['id'], row['patient_id'])
        self.store.web.logout(session)
        with self.assertRaises(AuthError):
            self.store.web.patient(session)

    def test_number_ownership_is_required_before_creating_account(self):
        self.store.web.configured = True
        body = {'phone': '5511988887777', 'password': 'MinhaSenhaSegura!123',
                'passwordConfirm': 'MinhaSenhaSegura!123', 'consent': True,
                'profile': {'birthday': '1990-04-10', 'gender': 'male', 'heightCm': 170,
                            'weightKg': 79, 'goal': 'loseWeight', 'activityLevel': 'active'}}
        challenge = self.store.web.start('signup', body)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM web_accounts').fetchone()[0], 0)
        correct = self.store.web.code(challenge['challengeId'])
        wrong = '111111' if correct != '111111' else '222222'
        for _ in range(5):
            with self.assertRaises(AuthError):
                self.store.web.verify('signup', {'challengeId': challenge['challengeId'], 'code': wrong})
        with self.assertRaises(AuthError):
            self.store.web.verify('signup', {'challengeId': challenge['challengeId'], 'code': correct})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM web_accounts').fetchone()[0], 0)

    def test_link_existing_app_and_reinstall_preserve_patient_and_history(self):
        self.verify()
        owner = self.patient['id']
        self.store.db.execute("INSERT INTO history(patient_id,role,content,created) VALUES(?,'user','Meu histórico',0)", (owner,))
        _, _, session = self.signup(self.patient['phone'])
        self.assertEqual(self.store.web.patient(session)['id'], owner)
        replacement = self.store.enroll({'phone': self.patient['phone'],
            'appToken': 'a' * 64, 'pairingCode': '123456',
            'consent': {'granted': True, 'version': 'test-reinstall'}})
        self.store.ingest(self.event('123456', 'web-app-reinstall'), 'nutri')
        self.assertEqual(self.store.patient(replacement['token'])['id'], owner)
        self.assertEqual(self.store.web.patient(session)['id'], owner)
        self.assertTrue(self.store.web.patient(session)['verified'])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM history WHERE patient_id=? AND content='Meu histórico'", (owner,)).fetchone()[0], 1)

    def test_password_reset_uses_one_code_and_revokes_web_sessions_only(self):
        self.verify()
        body, _, session = self.signup(self.patient['phone'])
        self.store.db.execute("DELETE FROM web_auth_attempts")
        challenge = self.store.web.start('reset', {'phone': body['phone']})
        payload = {'challengeId': challenge['challengeId'], 'code': self.store.web.code(challenge['challengeId']),
                   'password': 'MinhaNovaSenha!456', 'passwordConfirm': 'MinhaNovaSenha!456'}
        self.store.web.verify('reset', payload)
        with self.assertRaises(AuthError):
            self.store.web.patient(session)
        with self.assertRaises(AuthError):
            self.store.web.verify('reset', payload)
        with self.assertRaises(AuthError):
            self.store.web.login({'phone': body['phone'], 'password': body['password']})
        self.assertTrue(self.store.web.login({'phone': body['phone'], 'password': payload['password']}))
        self.assertEqual(self.store.patient(self.enrollment['token'])['id'], self.patient['id'])
        self.assertTrue(self.store.me(self.enrollment['token'])['verified'])
        self.assertTrue(self.store.web.patient(self.store.web.login({'phone': body['phone'], 'password': payload['password']}))['consent'])

    def test_unknown_recovery_is_generic_and_resend_is_limited(self):
        self.store.web.configured = True
        response = self.store.web.start('reset', {'phone': '5511988887777'})
        row = self.store.db.execute('SELECT * FROM web_challenges WHERE id=?', (response['challengeId'],)).fetchone()
        self.assertEqual(row['delivery'], 'unavailable')
        self.assertNotIn('code', response)
        with self.assertRaises(AuthError):
            self.store.web.resend({'challengeId': response['challengeId']})
        with self.assertRaises(AuthError):
            self.store.web.start('reset', {'phone': '5511988887777'})

    def test_password_policy_and_expired_code(self):
        self.store.web.configured = True
        from web_accounts import password_hash
        for value in ('curta!', 'SenhaLongaSemEspecial'):
            with self.assertRaises(AuthError):
                password_hash({'password': value, 'passwordConfirm': value})
        body, _, _ = self.signup()
        self.store.db.execute("DELETE FROM web_auth_attempts")
        challenge = self.store.web.start('reset', {'phone': body['phone']})
        self.store.db.execute('UPDATE web_challenges SET expires=0 WHERE id=?', (challenge['challengeId'],))
        with self.assertRaises(AuthError):
            self.store.web.verify('reset', {'challengeId': challenge['challengeId'],
                'code': self.store.web.code(challenge['challengeId'])})

    def test_sender_uses_evolution_and_never_returns_code_in_http_response(self):
        self.store.web.configured = True
        self.store.web.base_url = 'https://evolution.example'
        self.store.web.api_key = 'fixture-key'
        self.store.web.instance = 'Nutrição'
        response = self.store.web.start('reset', {'phone': '5511999999999'})
        self.assertEqual(self.store.db.execute('SELECT delivery FROM web_challenges').fetchone()[0], 'unavailable')
        self.store.db.execute('DELETE FROM web_auth_attempts')
        body, _, _ = self.signup()
        self.store.db.execute('DELETE FROM web_auth_attempts')
        response = self.store.web.start('reset', {'phone': body['phone']})
        class ProviderResponse:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, *_): return b'{"key":{"id":"fixture-message-id"}}'
        with patch('web_accounts.urlopen', return_value=ProviderResponse()) as send:
            self.store.web.deliver_once()
        request = send.call_args.args[0]
        self.assertIn('/message/sendText/Nutri%C3%A7%C3%A3o', request.full_url)
        text = json.loads(request.data)['text']
        self.assertIn(self.store.web.code(response['challengeId']), text)
        self.assertNotIn(body['password'], text)
        self.assertEqual(self.store.db.execute('SELECT delivery FROM web_challenges WHERE id=?', (response['challengeId'],)).fetchone()[0], 'sent')

    def test_sessions_survive_reopen(self):
        _, _, session = self.signup()
        owner = self.store.web.patient(session)['id']
        self.store.db.close()
        self.store = Store(self.temp.name + '/db.sqlite3')
        self.assertEqual(self.store.web.patient(session)['id'], owner)

    def test_delivery_error_reports_status_without_secrets(self):
        body, _, _ = self.signup()
        self.store.db.execute('DELETE FROM web_auth_attempts')
        self.store.web.base_url = 'https://evolution.example'
        self.store.web.api_key = 'private-fixture-key'
        challenge = self.store.web.start('reset', {'phone': body['phone']})
        with patch('web_accounts.urlopen', side_effect=HTTPError('https://evolution.example', 401, 'Unauthorized', {}, None)), patch('builtins.print') as log:
            self.store.web.deliver_once()
        message = log.call_args.args[0]
        self.assertIn('HTTP 401', message)
        for secret in (body['phone'], body['password'], self.store.web.api_key, self.store.web.code(challenge['challengeId'])):
            self.assertNotIn(secret, message)

    def test_http_cookie_origin_and_static_isolation(self):
        body, _, _ = self.signup()
        server = make_server(self.store, 'service-test-token', port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        def request(path, payload=None, cookie=None, source=None):
            headers = {'Origin': source or origin, 'Content-Type': 'application/json'}
            if cookie: headers['Cookie'] = cookie
            req = Request(origin+path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
            return urlopen(req)
        try:
            with request('/') as response:
                self.assertIn(b'GarfoFala', response.read())
            with request('/web-api/login', {'phone': body['phone'], 'password': body['password']}) as response:
                header = response.headers['Set-Cookie']
                self.assertIn('HttpOnly', header)
                self.assertIn('Secure', header)
                cookie = SimpleCookie(header).output(header='').strip().split(';')[0]
            with request('/web-api/me', cookie=cookie) as response:
                self.assertEqual(json.load(response)['phone'], body['phone'])
            with self.assertRaises(HTTPError) as error:
                request('/web-api/logout', {}, cookie, 'https://other.example')
            self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError):
                request('/server/web_accounts.py')
            self.store.web.logout(cookie.split('=', 1)[1])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
