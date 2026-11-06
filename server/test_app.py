import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Store, Problem, make_server


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name + '/db.sqlite3')
        self.enrollment = self.store.enroll({'phone': '5511999999999',
            'consent': {'granted': True, 'version': 'test-v1'}})
        self.patient = self.store.patient(self.enrollment['token'])

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def event(self, text, event_id='evo:nutri:message-1'):
        return {'kind': 'incoming', 'eventId': event_id, 'phone': self.patient['phone'],
                'instance': 'nutri', 'text': text}

    def verify(self):
        job = self.store.ingest(self.event(self.enrollment['pairingCode']), 'nutri')
        if job.get('verified'):
            # Most tests start after the introductory questions.
            self.store.db.execute("UPDATE coaching SET stage='done' WHERE patient_id=?", (self.patient['id'],))
            self.store.db.commit()
        return job

    def test_accented_instance_verifies_and_reserves_with_exact_name(self):
        event = {**self.event(self.enrollment['pairingCode']),
                 'instance': 'Nutrição', 'eventId': 'evo:Nutrição:accent-1'}
        job = self.store.ingest(event, 'Nutrição')
        self.assertTrue(job['verified'])
        result = self.store.reserve({'eventId': job['eventId'], 'userId': job['userId'],
            'phone': job['phone'], 'candidate': 'Olá'}, 'Nutrição')
        self.assertEqual(result['instance'], 'Nutrição')

    def reserve(self, job):
        return self.store.reserve({'eventId': job['eventId'], 'userId': job['userId'],
            'phone': job['phone'], 'candidate': 'Mensagem da IA'}, 'nutri')

    def test_phone_is_unverified_until_correct_code_and_only_owner_sees_status(self):
        self.assertFalse(self.store.me(self.enrollment['token'])['verified'])
        self.assertEqual(self.store.ingest(self.event('000000'), 'nutri')['action'], 'ignore')
        self.assertTrue(self.verify()['verified'])
        with self.assertRaises(Problem):
            self.store.me('incorrect-token')

    def test_code_attempt_limit(self):
        for i in range(5):
            self.store.ingest(self.event('000000', 'wrong-code-' + str(i)), 'nutri')
        self.assertEqual(self.verify()['action'], 'ignore')

    def test_registration_requires_persisted_id_and_never_shares_unverified_context(self):
        event = {'kind': 'registration', 'eventId': self.patient['registration_id'],
            'userId': self.patient['id'], 'phone': self.patient['phone']}
        job = self.store.ingest(event, 'nutri')
        self.assertEqual(job['action'], 'welcome')
        self.assertEqual(job['context'], {})
        event['userId'] = 'other-patient'
        self.assertEqual(self.store.ingest(event, 'nutri')['action'], 'ignore')

    def test_atomic_reservation_prevents_concurrent_duplicate_sends(self):
        job = self.verify()
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(lambda _: self.reserve(job), range(4)))
        self.assertEqual(sum(r['approved'] for r in results), 1)
        self.assertEqual(self.verify()['action'], 'ignore')

    def test_optout_blocks_old_pending_ai_job_and_is_acknowledged_once(self):
        self.verify()
        ai_job = self.store.ingest(self.event('Olá', 'new-message-2'), 'nutri')
        stop = self.store.ingest(self.event('SAIR', 'stop-message-3'), 'nutri')
        self.assertTrue(stop['optOutPersisted'])
        self.assertFalse(self.reserve(ai_job)['approved'])
        self.assertTrue(self.reserve(stop)['approved'])
        self.assertFalse(self.reserve(stop)['approved'])
        self.assertEqual(self.store.ingest(self.event('Oi', 'after-stop-4'), 'nutri')['action'], 'ignore')

    def test_does_not_accept_foreign_user_phone_or_instance(self):
        job = self.verify()
        with self.assertRaises(Problem):
            self.store.reserve({'eventId': job['eventId'], 'userId': 'other', 'phone': job['phone']}, 'nutri')
        self.assertEqual(self.store.ingest(self.event('oi') | {'instance': 'other'}, 'nutri')['action'], 'ignore')

    def test_reinstall_requires_new_code_before_taking_over_phone(self):
        self.verify()
        second = self.store.enroll({'phone': self.patient['phone'],
            'consent': {'granted': True, 'version': 'test-v1'}})
        self.assertTrue(self.store.me(self.enrollment['token'])['consentActive'])
        job = self.store.ingest(self.event(second['pairingCode'], 'rebind-message-4'), 'nutri')
        self.assertEqual(job['userId'], second['userId'])
        self.assertFalse(self.store.me(self.enrollment['token'])['consentActive'])

    def test_result_is_idempotent_and_accepted_is_not_downgraded(self):
        dispatch = self.reserve(self.verify())
        self.store.result({'dispatchId': dispatch['dispatchId'], 'status': 'accepted', 'providerMessageId': 'out-1'})
        self.store.result({'dispatchId': dispatch['dispatchId'], 'status': 'uncertain'})
        row = self.store.db.execute('SELECT status FROM dispatches').fetchone()
        self.assertEqual(row['status'], 'accepted')

    def test_user_cannot_submit_clinician_approved_diet(self):
        self.store.context(self.enrollment['token'], {'displayName': 'Ana',
            'approvedPlanSummary': 'fake-prescription', 'recentDiarySummary': 'Arroz 100 g'})
        data = self.store.me(self.enrollment['token'])['context']
        self.assertNotIn('approvedPlanSummary', data)

    def test_general_ai_is_explicit_optin_and_clinical_requests_use_fixed_handoff(self):
        self.verify()
        job = self.store.ingest(self.event('Oi', 'general-message-5'), 'nutri')
        self.assertEqual(job['action'], 'reply')  # n8n must skip the AI provider.
        fixed = self.reserve(job)
        self.assertNotEqual(fixed['text'], 'Mensagem da IA')
        self.store.allow_ai = True
        job = self.store.ingest(self.event('Como registro?', 'general-message-6'), 'nutri')
        self.assertEqual(job['action'], 'assistant')
        self.assertEqual(self.reserve(job)['text'], 'Mensagem da IA')
        clinical = self.store.ingest(self.event('Qual medicamento?', 'clinical-message-7'), 'nutri')
        self.assertEqual(clinical['action'], 'reply')
        self.assertIn('profissional de saúde', clinical['text'])

    def test_expired_code_never_releases_patient_context(self):
        with self.store.db:
            self.store.db.execute('UPDATE patients SET code_until=0')
        self.assertEqual(self.verify()['action'], 'ignore')

    def test_reservation_survives_database_reopen(self):
        job = self.verify()
        self.assertTrue(self.reserve(job)['approved'])
        self.store.db.close()
        self.store = Store(self.temp.name + '/db.sqlite3')
        self.assertFalse(self.reserve(job)['approved'])

    def test_http_requires_separate_service_and_patient_tokens(self):
        server = make_server(self.store, 'service-secret-' + 'a' * 32, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with urlopen(base + '/healthz') as response:
                self.assertTrue(json.load(response)['ok'])
            for path in ['/api/v1/me', '/v1/nutri/events/ingest']:
                data = b'{"event":{}}' if '/ingest' in path else None
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + path, data=data))
                self.assertEqual(error.exception.code, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
