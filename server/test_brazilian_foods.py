import unittest
from unittest.mock import patch
import test_app as fixtures
from records import validate_record
from pof import exact_entry, pof_food
from daily_progress import summarize, energy_balance
from photo_meals import prepare
from datetime import date


class BrazilianFoodTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp
    tearDown = fixtures.BridgeTests.tearDown

    def test_ready_cuscuz_and_carreteiro_use_specific_references(self):
        for text, expected in [('Cuscuz nordestino',533),('Cuscuz de milho',533),
                               ('Cuscuz paulista',534),('Feijão à tropeira',539),('Arroz de carreteiro',526)]:
            record = validate_record({'kind':'meal','text':text,'quantity':100,'unit':'g','mealType':'lunch'})
            self.store.records.enrich_meals([record],auto_save=True)
            self.assertEqual(record['foodCode'],f'taco:{expected}',text)
            self.assertGreater(record['nutrition']['energyKcal'],0)
        self.assertNotEqual(self.store.records.closest('arroz branco cru')['id'],526)
        self.assertNotIn('cru',self.store.records.closest('arroz')['name'].lower())

    def test_ibge_aliases_preserve_recipe_and_preparation(self):
        reference=(8503501,99,'BAIAO DE DOIS',[120,4,15,3,2,200])
        moqueca=(8506401,99,'MOQUECA BAIANA',[140,12,3,8,1,300])
        with patch('pof.catalogue',return_value=({'baiao de dois':[reference],'moqueca baiana':[moqueca]},{})):
            self.assertEqual(pof_food('baião de 2')['code'],'pof:8503501:99')
            self.assertEqual(pof_food('moqueca de peixe baiana')['code'],'pof:8506401:99')
            self.assertEqual(exact_entry('dois de baião'),reference)
            self.assertIsNone(pof_food('moqueca capixaba'))
            self.assertIsNone(pof_food('moqueca de frango baiana'))
            self.assertIsNone(pof_food('baião de dois vegano'))

    def test_unresolved_photo_component_marks_daily_totals_incomplete(self):
        raw=prepare([{'usable':True,'items':[{'food':'farofa ou cuscuz','grams':None,'confidence':'low'}]}],'meu almoço')
        record=validate_record(raw[0])
        totals,missing,_=summarize([record])
        self.assertIn('energyKcal',missing)
        profile=dict(birthday='1990-01-01',heightCm=170,weightKg=79,gender='male',activityLevel='active')
        self.assertIsNone(energy_balance(date(2026,11,26),totals,profile,missing)['balanceKcal'])
