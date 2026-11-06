import time
import unittest
from concurrent.futures import ThreadPoolExecutor
import test_app as fixtures
from messaging import split_message

class MessagingTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp
    tearDown = fixtures.BridgeTests.tearDown
    event = fixtures.BridgeTests.event
    verify = fixtures.BridgeTests.verify
    reserve = fixtures.BridgeTests.reserve

    def ready(self):
        self.verify()
        self.store.allow_ai = True
        self.store.messaging.quiet_seconds = .08

    def test_burst_joins_messages_once_and_retries_are_ignored(self):
        self.ready()
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.store.messaging.collect, self.event('Comi pão', 'burst-message-1'), 'nutri')
            time.sleep(.02)
            second = pool.submit(self.store.messaging.collect, self.event('50 gramas no café', 'burst-message-2'), 'nutri')
            self.assertEqual(first.result()['action'], 'ignore')
            job = second.result()
        self.assertEqual(job['message'], 'Comi pão\n50 gramas no café')
        self.assertEqual(job['eventId'], 'burst-message-2')
        self.assertEqual(self.store.messaging.collect(self.event('50 gramas no café', 'burst-message-2'), 'nutri')['action'], 'ignore')

    def test_stop_interrupts_pending_burst_without_asking_model(self):
        self.ready()
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.store.messaging.collect, self.event('Comi arroz', 'pending-message-1'), 'nutri')
            time.sleep(.02)
            result = self.store.messaging.collect(self.event('SAIR', 'stop-burst-message'), 'nutri')
            self.assertFalse(result['consentActive'])
            self.assertEqual(future.result()['action'], 'ignore')

    def test_patients_never_share_a_buffer(self):
        self.ready()
        second = self.store.enroll({'phone': '5521999999999', 'consent': {'granted': True, 'version': 'test'}})
        with self.store.db:
            self.store.db.execute('UPDATE patients SET verified=1 WHERE id=?', (second['userId'],))
            self.store.coaching.start(second['userId'])
            self.store.db.execute("UPDATE coaching SET stage='done' WHERE patient_id=?", (second['userId'],))
        other = {**self.event('Outra pessoa', 'other-person-message'), 'phone': '5521999999999'}
        with ThreadPoolExecutor(2) as pool:
            one = pool.submit(self.store.messaging.collect, self.event('Meu almoço', 'own-person-message'), 'nutri')
            two = pool.submit(self.store.messaging.collect, other, 'nutri')
            self.assertEqual(one.result()['message'], 'Meu almoço')
            self.assertEqual(two.result()['message'], 'Outra pessoa')

    def test_parts_are_ordered_authorized_once_and_stop_blocks_rest(self):
        self.ready()
        job = self.store.ingest(self.event('Oi', 'multipart-message-1'), 'nutri')
        dispatch = self.store.reserve({'eventId': job['eventId'], 'userId': job['userId'], 'phone': job['phone'], 'candidate': 'Uma frase natural. ' * 70}, 'nutri')
        self.assertGreater(len(dispatch['parts']), 1)
        first, second = dispatch['parts'][:2]
        self.assertFalse(self.store.messaging.authorize(second, 'nutri')['approved'])
        part = self.store.messaging.authorize(first, 'nutri')
        self.assertTrue(part['approved'])
        self.assertLessEqual(len(part['text']), 700)
        self.assertFalse(self.store.messaging.authorize(first, 'nutri')['approved'])
        self.assertTrue(self.store.messaging.receipt({'partId': part['partId'], 'status': 'accepted'})['continue'])
        self.store.ingest(self.event('SAIR', 'stop-before-second-part'), 'nutri')
        self.assertFalse(self.store.messaging.authorize(second, 'nutri')['approved'])

    def test_uncertain_part_prevents_sending_remaining_parts(self):
        self.ready()
        job = self.store.ingest(self.event('Oi', 'multipart-message-2'), 'nutri')
        dispatch = self.store.reserve({'eventId': job['eventId'], 'userId': job['userId'], 'phone': job['phone'], 'candidate': 'Uma frase. ' * 130}, 'nutri')
        part = self.store.messaging.authorize(dispatch['parts'][0], 'nutri')
        self.assertFalse(self.store.messaging.receipt({'partId': part['partId'], 'status': 'uncertain'})['continue'])
        self.assertFalse(self.store.messaging.authorize(dispatch['parts'][1], 'nutri')['approved'])

    def test_split_preserves_order_and_does_not_break_words(self):
        text = 'Primeira refeição.\n\n' + ('Outro alimento e quantidade. ' * 60)
        parts = split_message(text)
        self.assertTrue(all(0 < len(part) <= 700 for part in parts))
        self.assertEqual(' '.join(text.split()), ' '.join(' '.join(parts).split()))
