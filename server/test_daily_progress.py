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

    def test_goals_are_announced_once_and_pending_water_reminder_is_suppressed(self):
        from datetime import datetime
        from daily_progress import BRASILIA
        self.verify()
        self.store.allow_ai = True
        patient = self.patient['id']
        self.store.context(self.enrollment['token'], {'profile': {'dailyGoals': {'waterMl': 1000, 'proteinG': 2}}})
        self.store.db.execute("UPDATE coaching SET reminders=1,stage='done' WHERE patient_id=?", (patient,))
        due = datetime.now(BRASILIA).replace(hour=9, minute=1, second=0, microsecond=0)
        self.store.coaching.schedule(due)
        reminder = self.store.db.execute('SELECT event_id FROM reminder_slots').fetchone()[0]
        self.assertIsNotNone(self.store.coaching.reminder(reminder, patient, due.timestamp()))
        water = {'kind': 'water', 'text': 'Água', 'quantity': 500, 'unit': 'ml'}
        self.assertNotIn('bateu', self.save('goal-water-1', 'Bebi água', water)['text'])
        self.assertIn('meta diária de água', self.save('goal-water-2', 'Bebi água', water)['text'])
        self.assertNotIn('bateu', self.save('goal-water-3', 'Bebi água', water)['text'])
        self.assertIsNone(self.store.coaching.reminder(reminder, patient, due.timestamp()))
        self.store.coaching.schedule(due.replace(hour=12))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM reminder_slots').fetchone()[0], 1)
        meal = {'kind': 'meal', 'text': 'Arroz, tipo 1, cozido', 'quantity': 100, 'unit': 'g', 'mealType': 'lunch'}
        self.assertIn('meta diária de proteína', self.save('goal-protein-1', 'Almocei arroz', meal)['text'])
        self.assertNotIn('bateu', self.save('goal-protein-2', 'Mais arroz', meal)['text'])

    def test_sandwich_uses_three_reference_portions_even_if_ai_groups_it(self):
        self.verify()
        self.store.allow_ai = True
        job = self.save('sandwich-portions',
            'Comi um pão francês com uma fatia de presunto e uma fatia de queijo esse foi o meu café da manhã',
            {'kind':'meal','text':'Pão francês com presunto e queijo','unit':'unit','quantity':1,'mealType':'breakfast'})
        self.assertIn('total da refeição',job['text'])
        rows = self.store.records.list(self.patient['id'])['records']
        self.assertEqual([r['quantity'] for r in rows],[50,20,20])
        self.assertTrue(all(r['nutrition']['energyKcal'] > 0 for r in rows))
        self.assertIsNone(self.store.records.correct_meal(self.patient['id'],
            'foi um pão com presunto e queijo não sei a quantidade em g'))

    def test_feijoada_replaces_photo_components_and_keeps_side_dishes(self):
        self.verify()
        self.store.allow_ai = True
        patient = self.patient['id']
        dishes = [{'kind':'meal','text':food,'unit':'g','quantity':grams,'mealType':'lunch',
                   'estimateSource':'photo'} for food, grams in [
                       ('arroz branco cozido',180),('carne bovina cozida',170),('linguiça frita',50),('farofa',30)]]
        self.save('photo-before-feijoada','Meu almoço',dishes)
        before = self.store.records.list(patient)
        correction = self.store.ingest(self.event('Era uma feijoada','photo-feijoada-correction'),'nutri')
        self.assertIn('mantive os acompanhamentos',correction['text'])
        rows = self.store.records.list(patient,revisions=True)['records']
        self.assertEqual({r['text'] for r in rows},{'arroz branco cozido','Feijoada','farofa'})
        meal = next(r for r in rows if r['text']=='Feijoada')
        self.assertEqual(meal['quantity'],220)
        self.assertGreater(meal['nutrition']['energyKcal'],0)
        updates=self.store.records.list(patient,before['nextCursor'],revisions=True,removals=True)['records']
        self.assertEqual(sum(r.get('removed',False) for r in updates),1)
        self.assertEqual(len(updates),2)
        self.assertIn('já está',self.store.ingest(self.event('Pode corrigir essa','photo-feijoada-ack'),'nutri')['text'])
