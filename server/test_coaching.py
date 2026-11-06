import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import test_app as fixtures

class CoachingTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp
    tearDown = fixtures.BridgeTests.tearDown
    event = fixtures.BridgeTests.event
    verify = fixtures.BridgeTests.verify
    reserve = fixtures.BridgeTests.reserve
    def enter(self, text, index):
        return self.store.ingest(self.event(text, f'coaching-message-{index}'), 'nutri')

    def test_onboarding_name_and_explicit_reminder_consent_are_persistent(self):
        job = self.store.ingest(self.event(self.enrollment['pairingCode']), 'nutri')
        self.assertIn('Como você gostaria', job['text'])
        self.assertEqual(self.store.coaching.get(self.patient['id'])['reminders'], 0)
        reply = self.enter('Pode me chamar de Luiz', 2)
        self.assertIn('Luiz', reply['text'])
        self.assertIn('09:00', reply['text'])
        self.enter('SIM', 3)
        job = self.enter('Como foi meu dia?', 4)
        self.assertEqual(job['context']['displayName'], 'Luiz')
        self.assertEqual(self.store.coaching.get(self.patient['id'])['reminders'], 1)
        self.store.context(self.enrollment['token'], {'recentDiarySummary': 'Atualização do app'})
        self.assertEqual(self.store.coaching.get(self.patient['id'])['name'], 'Luiz')

    def test_no_reminder_without_opt_in_and_no_duplicates_after_restart(self):
        self.store.ingest(self.event(self.enrollment['pairingCode']), 'nutri')
        self.enter('Luiz', 2)
        now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)  # 09h Brasília
        self.store.coaching.schedule(now)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM reminder_slots').fetchone()[0], 0)
        self.enter('SIM', 3)
        self.store.coaching.schedule(now)
        self.store.coaching.schedule(now)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM reminder_slots').fetchone()[0], 1)
        self.store.db.commit()
        event = json.loads(self.store.db.execute("SELECT body FROM notifications WHERE id LIKE 'reminder:%'").fetchone()[0])
        with patch('coaching.time.time', return_value=now.timestamp()):
            job = self.store.ingest(event, 'nutri')
            self.assertEqual(job['action'], 'reply')
            self.assertIn('Luiz', job['text'])
            self.enter('PARAR LEMBRETES', 4)
            self.assertFalse(self.reserve(job)['approved'])
        self.assertTrue(self.store.me(self.enrollment['token'])['consentActive'])

    def test_custom_schedule_requires_confirmation_and_stop_blocks_queue(self):
        self.store.ingest(self.event(self.enrollment['pairingCode']), 'nutri')
        self.enter('PULAR', 2)
        self.enter('NÃO', 3)
        self.enter('ALTERAR LEMBRETES', 4)
        self.enter('10:00, 16:30', 5)
        self.assertEqual(self.store.coaching.get(self.patient['id'])['reminders'], 0)
        self.enter('SIM', 6)
        self.assertEqual(json.loads(self.store.coaching.get(self.patient['id'])['hours']), ['10:00', '16:30'])
        self.enter('SAIR', 7)
        self.store.coaching.schedule(datetime(2026, 11, 6, 13, 0, tzinfo=timezone.utc))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM reminder_slots').fetchone()[0], 0)

    def test_forged_or_expired_reminder_is_ignored(self):
        self.verify()
        event = {'kind': 'reminder', 'userId': self.patient['id'], 'phone': self.patient['phone'], 'eventId': 'reminder:forged-test'}
        self.assertEqual(self.store.ingest(event, 'nutri')['action'], 'ignore')
        self.store.coaching.schedule(datetime(2026, 11, 6, 12, 8, tzinfo=timezone.utc))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM reminder_slots').fetchone()[0], 0)

