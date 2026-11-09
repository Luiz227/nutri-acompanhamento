import unittest
import test_app as fixtures
from menu_coach import MENU_READY
from messaging import split_message

class NaturalTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp
    tearDown = fixtures.BridgeTests.tearDown
    event = fixtures.BridgeTests.event
    verify = fixtures.BridgeTests.verify

    def set_ready(self):
        self.verify()
        self.store.allow_ai = True

    def automatic(self, record, event_id='auto-record-event'):
        self.set_ready()
        job = self.store.ingest(self.event('Registro pelo WhatsApp',event_id), 'nutri')
        return self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'candidate':'Ok','record':record},'nutri')

    def test_water_saves_immediately_without_confirmation_or_timezone(self):
        result=self.automatic({'kind':'water','text':'Água','quantity':500,'unit':'ml'})
        self.assertNotIn('CONFIRMAR',result['text'])
        self.assertNotIn('Brasília',result['text'])
        self.assertNotIn('CANCELAR',result['text'])
        self.assertIn('500 ml',result['text'])
        saved=self.store.records.list(self.patient['id'])['records']
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]['quantity'],500)

    def test_meal_saves_and_returns_macros_in_separate_natural_bubbles(self):
        result=self.automatic({'kind':'meal','text':'Arroz, tipo 1, cozido','quantity':100,'unit':'g','mealType':'lunch'})
        for label in ('kcal','proteína','carboidratos','gordura'):
            self.assertIn(label,result['text'])
        self.assertNotIn(' — ',result['text'])
        self.assertNotIn('CONFIRMAR',result['text'])
        self.assertGreaterEqual(len(split_message(result['text'])),2)
        self.assertTrue(all(len(p)<=420 for p in split_message(result['text'])))
        self.assertEqual(self.store.records.list(self.patient['id'])['records'][0]['mealType'],'lunch')
        self.assertEqual(self.store.ingest(self.event('Registro pelo WhatsApp','auto-record-event'),'nutri')['action'],'ignore')

    def test_compatible_approximation_is_identified_and_preserves_original_food(self):
        result=self.automatic({'kind':'meal','text':'pão de forma comum','quantity':50,'unit':'g','mealType':'breakfast'})
        self.assertIn('estimativa',result['text'])
        record=self.store.records.list(self.patient['id'])['records'][0]
        self.assertTrue(record['estimated'])
        self.assertEqual(record['text'],'pão de forma comum')
        self.assertNotIn('integral',record['foodName'].lower())
        self.assertGreater(record['nutrition']['energyKcal'],0)
        self.assertIsNone(self.store.records.closest('frango sem preparo informado'))

    def test_open_food_facts_product_uses_server_values_not_model_values(self):
        self.store.records.products.fetch=lambda code:{'status':1,'product':{'product_name':'Produto exemplo','nutriments':{'energy-kcal_100g':250,'proteins_100g':10,'carbohydrates_100g':30,'fat_100g':10,'sodium_100g':.5}}}
        result=self.automatic({'kind':'meal','text':'Produto exemplo','quantity':40,'unit':'g','mealType':'snack','barcode':'12345678','nutrition':{'energyKcal':9999}})
        record=self.store.records.list(self.patient['id'])['records'][0]
        self.assertEqual(record['foodCode'],'off:12345678')
        self.assertEqual(record['nutrition']['energyKcal'],100)
        self.assertEqual(record['nutrientsPer100g']['sodium_100'],500)
        self.assertIn('Open Food Facts',result['text'])
        self.assertIsNone(self.store.records.products.product('https://example.com'))

    def test_menu_requires_permission_collects_preferences_and_does_not_repeat_offer(self):
        self.set_ready()
        self.assertTrue(self.store.menu.offer(self.patient['id']))
        self.assertEqual(self.store.menu.offer(self.patient['id']),'')
        self.store.menu.handle(self.patient['id'],'sim')
        self.store.menu.handle(self.patient['id'],'sim')
        self.store.menu.handle(self.patient['id'],'Organizar a rotina, caminho três vezes por semana')
        self.store.menu.handle(self.patient['id'],'Não')
        self.assertEqual(self.store.menu.handle(self.patient['id'],'Vegetariano, refeições às 8h, 12h e 19h, orçamento limitado'),MENU_READY)
        profile=self.store.menu.get(self.patient['id'])
        self.assertEqual(profile['stage'],'ready')
        self.assertIn('Vegetariano',profile['routineAndPreferences'])
        self.assertEqual(self.store.menu.offer(self.patient['id']),'')

    def test_menu_does_not_create_therapeutic_diet_for_diabetes(self):
        self.set_ready()
        self.store.menu.offer(self.patient['id'])
        for reply in ('sim','sim','Melhorar alimentação','Tenho diabetes'):
            result=self.store.menu.handle(self.patient['id'],reply)
        self.assertIn('nutricionista',result)
        self.assertEqual(self.store.menu.get(self.patient['id'])['stage'],'clinical')

    def test_menu_ready_reaches_the_model_with_preferences_instead_of_clinical_fallback(self):
        self.set_ready()
        self.store.menu.save(self.patient['id'], 'routine', {'adult':True,'goalAndActivity':'Rotina equilibrada','restrictionsAndHealth':'Nenhuma'})
        job=self.store.ingest(self.event('Vegetariano, pouco tempo para cozinhar','menu-ready-event'),'nutri')
        self.assertEqual(job['action'],'assistant')
        self.assertIn('Vegetariano',job['context']['menuPreferences'])
