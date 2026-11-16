import base64
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image
import test_app as fixtures
from daily_progress import render_card


class ProgressTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp
    tearDown = fixtures.BridgeTests.tearDown
    event = fixtures.BridgeTests.event
    verify = fixtures.BridgeTests.verify

    def save(self, event_id, message, record):
        job = self.store.ingest(self.event(message, event_id), 'nutri')
        return self.store.reserve(dict(eventId=event_id, userId=job['userId'], phone=job['phone'],
                                       candidate='Anotei.', record=record), 'nutri')

    def test_progress_uses_todays_confirmed_records_and_sends_after_receipt(self):
        self.verify()
        self.store.allow_ai = True
        self.store.context(self.enrollment['token'], {'profile': {'dailyGoals': {'waterMl': 2000}}})
        water = {'kind': 'water', 'text': 'Água', 'quantity': 500, 'unit': 'ml'}
        self.save('progress-water', 'Bebi água', water)
        meal = {'kind': 'meal', 'text': 'Arroz, tipo 1, cozido', 'quantity': 100, 'unit': 'g', 'mealType': 'lunch'}
        with patch('daily_progress.render_card', wraps=render_card) as render:
            self.save('progress-lunch', 'Almocei arroz', meal)
            render.assert_not_called()
            dinner = self.save('progress-dinner', 'Jantei arroz', {**meal, 'mealType': 'dinner'})
            _, totals, goals, missing, _ = render.call_args.args
            self.assertEqual(totals['waterMl'], 500)
            self.assertGreater(totals['energyKcal'], 200)
            self.assertEqual(goals['waterMl'], 2000)
            self.assertFalse(missing)
        parts = dinner['parts']
        self.assertFalse(self.store.messaging.authorize(parts[-1], 'nutri')['approved'])
        for part in parts[:-1]:
            auth = self.store.messaging.authorize(part, 'nutri')
            self.store.messaging.receipt({'partId': auth['partId'], 'status': 'accepted'})
        image = self.store.messaging.authorize(parts[-1], 'nutri')
        self.assertEqual(image['mediaType'], 'image')
        with Image.open(BytesIO(base64.b64decode(image['media']))) as png:
            self.assertEqual(png.format, 'PNG')
            self.assertEqual(png.size, (720, 930))
        self.assertFalse(self.store.messaging.authorize(parts[-1], 'nutri')['approved'])

    def test_explicit_last_meal_before_dinner(self):
        self.verify()
        self.store.allow_ai = True
        self.save('progress-final-lunch', 'Almocei arroz, minha última refeição do dia', {
            'kind': 'meal', 'text': 'Arroz, tipo 1, cozido', 'quantity': 100, 'unit': 'g', 'mealType': 'lunch'})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM dispatch_documents').fetchone()[0], 1)


    def test_corrections_keep_ids_and_reach_only_revision_aware_sync(self):
        self.verify()
        self.store.allow_ai = True
        patient = self.patient['id']
        meal = {'kind': 'meal', 'text': 'batata frita', 'quantity': 100, 'unit': 'g', 'mealType': 'lunch'}
        self.save('initial-potato', 'Almocei batata frita', meal)
        before = self.store.records.list(patient)['records'][0]
        command = self.event('Comi só metade', 'correction-half')
        self.assertIn('Corrigi', self.store.ingest(command, 'nutri')['text'])
        self.store.ingest(command, 'nutri')
        after = self.store.records.list(patient, before['seq'], revisions=True)['records'][0]
        self.assertEqual(after['id'], before['id'])
        self.assertEqual(after['quantity'], 50)
        self.assertAlmostEqual(after['nutrition']['energyKcal'], before['nutrition']['energyKcal'] / 2, places=3)
        self.assertEqual(self.store.records.list(patient, before['seq'])['records'], [])
        migrated = self.store.records.list(patient, revisions=True, legacy_after=after['seq'] + 10)['records']
        self.assertEqual([record['id'] for record in migrated], [before['id']])
        swap = self.store.ingest(self.event('Era mandioca, não batata', 'correction-swap'), 'nutri')
        self.assertIn('Corrigi', swap['text'])
        records = self.store.records.list(patient, revisions=True)['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['id'], before['id'])
        self.assertIn('mandioca', records[0]['foodName'].lower())
        self.assertEqual(records[0]['quantity'], 50)
        self.assertTrue(records[0]['estimated'])
        self.assertEqual(records[0]['mealType'], 'lunch')
