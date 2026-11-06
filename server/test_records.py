import unittest
import test_app as fixtures
from records import validate_record


class RecordTests(unittest.TestCase):
    event = fixtures.BridgeTests.event
    verify = fixtures.BridgeTests.verify
    tearDown = fixtures.BridgeTests.tearDown
    def setUp(self):
        fixtures.BridgeTests.setUp(self)
        self.verify()
        self.store.allow_ai = True

    def propose(self, raw, event_id='record-message-10'):
        job = self.store.ingest(self.event('Quero registrar', event_id), 'nutri')
        return self.store.reserve({'eventId': job['eventId'], 'userId': job['userId'],
            'phone': job['phone'], 'candidate': 'Vou conferir.', 'record': raw}, 'nutri')

    def test_only_confirmed_records_are_visible_and_confirmation_is_idempotent(self):
        draft = self.propose({'kind': 'water', 'text': 'Água', 'quantity': .5, 'unit': 'l'})
        self.assertIn('Ainda não salvei', draft['text'])
        self.assertEqual(self.store.records.list(self.patient['id'])['records'], [])
        reply = self.store.ingest(self.event('CONFIRMAR', 'confirm-record-11'), 'nutri')
        self.assertIn('Registro salvo', reply['text'])
        records = self.store.records.list(self.patient['id'])['records']
        self.assertEqual(records[0]['quantity'], 500)
        self.assertEqual(records[0]['unit'], 'ml')
        self.store.ingest(self.event('CONFIRMAR', 'confirm-record-11'), 'nutri')
        self.assertEqual(len(self.store.records.list(self.patient['id'])['records']), 1)

    def test_cancel_record_is_not_an_optout_and_does_not_save(self):
        self.propose({'kind': 'weight', 'text': 'Peso corporal', 'quantity': 80, 'unit': 'kg'})
        reply = self.store.ingest(self.event('CANCELAR REGISTRO', 'reject-record-12'), 'nutri')
        self.assertIn('descartado', reply['text'])
        self.assertTrue(reply['consentActive'])
        self.assertEqual(self.store.records.list(self.patient['id'])['records'], [])

    def test_records_are_isolated_and_saIr_prevents_confirmation(self):
        self.propose({'kind': 'observation', 'text': 'Hoje senti mais fome à tarde'})
        self.store.ingest(self.event('SAIR', 'stop-before-confirm-13'), 'nutri')
        self.store.ingest(self.event('CONFIRMAR', 'confirm-after-stop-14'), 'nutri')
        self.assertEqual(self.store.records.list(self.patient['id'])['records'], [])
        self.assertEqual(self.store.records.list('another-patient')['records'], [])

    def test_food_values_come_only_from_taco_not_the_model(self):
        self.propose({'kind': 'meal', 'text': 'Arroz, tipo 1, cozido', 'quantity': 100,
                      'unit': 'g', 'energyKcal': 99999})
        self.store.ingest(self.event('CONFIRMAR', 'confirm-meal-15'), 'nutri')
        record = self.store.records.list(self.patient['id'])['records'][0]
        self.assertEqual(record['foodCode'], 'taco:3')
        self.assertEqual(record['nutrientsPer100g']['energy_kcal_100'], 128.258486)
        self.assertNotIn('energyKcal', record)

    def test_unknown_food_is_not_a_zero_calorie_food(self):
        draft = self.propose({'kind': 'meal', 'text': 'Receita desconhecida', 'quantity': 100, 'unit': 'g'})
        self.assertIn('Sem cálculo nutricional', draft['text'])
        self.store.ingest(self.event('CONFIRMAR', 'confirm-unknown-16'), 'nutri')
        record = self.store.records.list(self.patient['id'])['records'][0]
        self.assertNotIn('nutrientsPer100g', record)

    def test_mussarela_synonym_uses_taco_and_discloses_match_before_confirmation(self):
        draft = self.propose({'kind': 'meal', 'text': 'mussarela', 'quantity': 7, 'unit': 'g'})
        self.assertIn('TACO: Queijo, mozarela', draft['text'])
        self.store.ingest(self.event('CONFIRMAR', 'confirm-cheese-19'), 'nutri')
        record = self.store.records.list(self.patient['id'])['records'][0]
        self.assertEqual(record['foodCode'], 'taco:463')
        self.assertEqual(record['quantity'], 7)

    def test_meal_nutrients_are_scaled_by_grams_and_category_is_preserved(self):
        draft = self.propose({'kind': 'meal', 'text': 'Arroz, tipo 1, cozido', 'quantity': 50, 'unit': 'g', 'mealType': 'breakfast'})
        self.assertIn('Café da manhã', draft['text'])
        self.assertIn('64,1 kcal', draft['text'])
        self.assertIn('Total estimado', draft['text'])
        self.store.ingest(self.event('CONFIRMAR', 'confirm-nutrition-22'), 'nutri')
        record = self.store.records.list(self.patient['id'])['records'][0]
        self.assertAlmostEqual(record['nutrition']['energyKcal'], 128.258486 / 2, places=3)
        self.assertEqual(record['mealType'], 'breakfast')
        self.assertGreater(record['nutrition']['carbsG'], 0)

    def test_unknown_ingredients_produce_only_an_explicit_partial_total(self):
        draft = self.propose([
            {'kind': 'meal', 'text': 'pão de forma comum', 'quantity': 50, 'unit': 'g', 'mealType': 'breakfast'},
            {'kind': 'meal', 'text': 'mussarela', 'quantity': 7, 'unit': 'g', 'mealType': 'breakfast'},
            {'kind': 'meal', 'text': 'presunto', 'quantity': 8, 'unit': 'g', 'mealType': 'breakfast'},
        ])
        self.assertIn('refeição incompleta', draft['text'])
        self.assertNotIn('Total estimado:', draft['text'])
        self.assertIn('sódio', draft['text'])
        self.assertLessEqual(len(draft['text']), 1800)

    def test_ambiguous_ham_and_common_bread_are_not_guessed(self):
        self.propose([{'kind': 'meal', 'text': 'presunto', 'quantity': 8, 'unit': 'g'},
                      {'kind': 'meal', 'text': 'pão de forma comum', 'quantity': 50, 'unit': 'g'}])
        self.store.ingest(self.event('CONFIRMAR', 'confirm-ambiguous-20'), 'nutri')
        for record in self.store.records.list(self.patient['id'])['records']:
            self.assertNotIn('foodCode', record)

    def test_candidates_use_synonyms_short_food_words_and_previous_user_context(self):
        candidates = self.store.records.candidates('pão mussarela presunto')
        self.assertIn({'name': 'Queijo, mozarela'}, candidates)
        self.assertTrue(any('Pão,' in r['name'] for r in candidates))
        self.propose({'kind': 'observation', 'text': 'Comi mussarela'})
        # Simulate the quantity arriving after a previous user message.
        self.store.db.execute('INSERT INTO history(patient_id,role,content,created) VALUES(?,?,?,?)',
            (self.patient['id'], 'user', 'Comi mussarela', 0))
        self.store.db.commit()
        job = self.store.ingest(self.event('7 gramas', 'quantity-next-message-21'), 'nutri')
        self.assertIn({'name': 'Queijo, mozarela'}, job['catalogueCandidates'])

    def test_units_dates_and_quantities_fail_closed(self):
        for raw in [{'kind': 'meal', 'text': 'Arroz', 'quantity': 1, 'unit': 'prato'},
                    {'kind': 'water', 'text': 'Água', 'quantity': True, 'unit': 'ml'},
                    {'kind': 'weight', 'text': 'Peso', 'quantity': -1, 'unit': 'kg'},
                    {'kind': 'observation', 'text': 'Nota', 'occurredAt': '2099-01-01T00:00:00Z'}]:
            with self.assertRaises((ValueError, TypeError)):
                validate_record(raw)

    def test_idempotent_enrollment_does_not_send_duplicate_welcome(self):
        body = {'phone': '5521999999999', 'appToken': 'a' * 64, 'pairingCode': '234567',
                'consent': {'granted': True, 'version': 'test-v2'}}
        first, second = self.store.enroll(body), self.store.enroll(body)
        self.assertEqual(first['userId'], second['userId'])
        self.assertEqual(second['pairingCode'], '234567')
        count = self.store.db.execute('SELECT count(*) FROM notifications').fetchone()[0]
        self.assertEqual(count, 2)  # One fixture enrollment, one new idempotent enrollment.

    def test_meal_with_multiple_items_is_confirmed_as_one_batch(self):
        self.propose([{'kind':'meal','text':'Arroz, tipo 1, cozido','quantity':100,'unit':'g'},
                      {'kind':'water','text':'Água','quantity':300,'unit':'ml'}])
        self.assertEqual(self.store.records.list(self.patient['id'])['records'], [])
        self.store.ingest(self.event('CONFIRMAR','confirm-batch-17'),'nutri')
        self.assertEqual(len(self.store.records.list(self.patient['id'])['records']),2)

    def test_oversized_confirmation_preserves_the_previous_pending_record(self):
        self.propose({'kind': 'water', 'text': 'Água', 'quantity': 300, 'unit': 'ml'})
        # Reject a batch too long to present for confirmation before changing pending data.
        batch = [{'kind': 'meal', 'text': 'x' * 220, 'quantity': 100, 'unit': 'g'} for _ in range(5)]
        with self.assertRaises(ValueError):
            self.store.records.propose(self.patient['id'], 'oversized-batch', batch)
        self.store.ingest(self.event('CONFIRMAR', 'confirm-preserved-18'), 'nutri')
        records = self.store.records.list(self.patient['id'])['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['kind'], 'water')


if __name__ == '__main__':
    unittest.main()
