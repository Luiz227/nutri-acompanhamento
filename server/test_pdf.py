import base64
import copy
import re
import unittest
from unittest.mock import patch
import test_app as fixtures
from meal_pdf import make_pdf, validate_plan, calculate_portions, DAYS
from example_menu import PLAN


class PdfTests(unittest.TestCase):
    setUp=fixtures.BridgeTests.setUp
    tearDown=fixtures.BridgeTests.tearDown
    verify=fixtures.BridgeTests.verify
    event=fixtures.BridgeTests.event

    def test_weekly_reference_format_has_seven_days_and_twenty_seven_pages(self):
        plan = copy.deepcopy(PLAN)
        names = ['Pão, trigo, forma, integral', 'Banana, prata, crua', 'Arroz, tipo 1, cozido',
                 'Iogurte, natural', 'Frango, peito, sem pele, grelhado']
        for meal, name in zip(plan['meals'], names):
            meal['foods'] = [{'name': name, 'grams': 200}]
        weekly = {'days': [{'day': day, 'meals': copy.deepcopy(plan['meals'])} for day in DAYS],
                  'shopping': plan['shopping'], 'tips': plan['tips']}
        app = {'dailyGoals': {'energyKcal': 2200}}
        pdf = make_pdf(weekly, 'Demonstração', app, {}, demo=True, resolve=self.store.records.enrich_menu)
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b', pdf)), 27)
        self.assertEqual(self.store.records.list(self.patient['id'])['records'], [])
        with self.assertRaises(ValueError):
            make_pdf(weekly, 'Demonstração', app, {'foodPreferences': 'Não como frango'},
                     resolve=self.store.records.enrich_menu)
        weekly['days'][1]['day'] = 'monday'
        with self.assertRaises(ValueError):
            make_pdf(weekly, 'Demonstração', app, {}, resolve=self.store.records.enrich_menu)

    def test_six_ingredient_lunch_and_fifteen_shopping_items_generate_pdf(self):
        plan = copy.deepcopy(PLAN)
        ingredients = [
            [('Pão, trigo, forma, integral',60),('Queijo, minas, frescal',40),('Mamão, Papaia, cru',120)],
            [('Iogurte, natural',170),('Maçã, Argentina, com casca, crua',130)],
            [('Arroz, integral, cozido',140),('Feijão, carioca, cozido',120),
             ('Frango, peito, sem pele, grelhado',140),('Alface, crespa, crua',50),
             ('Tomate, com semente, cru',80),('Brócolis, cozido',80)],
            [('Banana, nanica, crua',90),('Amendoim, torrado, salgado',20)],
            [('Omelete, de queijo',120),('Abobrinha, italiana, refogada',100),('Arroz, integral, cozido',90)],
        ]
        for meal, foods in zip(plan['meals'], ingredients):
            meal['foods'] = [{'name': name, 'grams': grams} for name, grams in foods]
        plan['shopping'] = ['Pão integral','Queijo minas frescal','Mamão','Iogurte natural','Maçã',
                            'Arroz integral','Feijão carioca','Peito de frango','Alface','Tomate',
                            'Brócolis','Banana','Amendoim torrado','Ovos e queijo para omelete','Abobrinha']
        app = {'goal': 'loseWeight', 'dailyGoals': {'energyKcal': 2200}}
        pdf = make_pdf(plan, 'Demonstração', app, {}, demo=True, resolve=self.store.records.enrich_menu)
        self.assertTrue(pdf.startswith(b'%PDF'))
        result = calculate_portions(validate_plan(plan), app, self.store.records.enrich_menu)
        self.assertLess(abs(result['totals']['energyKcal'] - 2200), 22)
        # Longer shopping lists gain pages rather than clipping or rejecting the menu.
        plan['shopping'] = [f'Ingrediente {index}: ' + 'alimentos da estação para a rotina em casa' for index in range(30)]
        expanded = make_pdf(plan, 'Demonstração', app, {}, demo=True, resolve=self.store.records.enrich_menu)
        self.assertGreater(len(re.findall(rb'/Type\s*/Page\b', expanded)),
                           len(re.findall(rb'/Type\s*/Page\b', pdf)))

    def test_menu_catalogue_rejects_ambiguous_recipes_and_wrong_substitutes(self):
        for name in ('ovos mexidos', 'omelete', 'salada de folhas',
                     'salada de alface e tomate', 'sopa de legumes', 'queijo branco'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.records.enrich_menu([{'kind': 'meal', 'text': name, 'quantity': 100}])
        options = self.store.records.menu_options()
        self.assertGreater(len(options), 25)
        for option in options:
            record = {'kind': 'meal', 'text': option['name'], 'quantity': 100}
            self.store.records.enrich_menu([record])
            self.assertEqual(record['foodName'], option['name'])
            self.assertTrue(all(record['nutrition'][key] is not None
                                for key in ('energyKcal', 'proteinG', 'carbsG', 'fatG')))

    def test_verified_options_make_quantified_pdf_and_failure_has_diagnostic(self):
        self.ready()
        profile = self.store.me(self.enrollment['token'])['context']['appProfile']
        self.store.context(self.enrollment['token'], {'profile': {
            **profile, 'dailyGoals': {'energyKcal': 2200}}})
        job = self.store.ingest(self.event('Quero PDF', 'verified-menu-request'), 'nutri')
        self.assertTrue(job['menuFoodOptions'])
        bad = copy.deepcopy(PLAN)
        for meal in bad['meals']:
            meal['foods'] = [{'name': 'sopa de legumes', 'grams': 200}]
        dispatch = self.store.reserve({'eventId': job['eventId'], 'userId': job['userId'],
                                      'phone': job['phone'], 'plan': bad}, 'nutri')
        self.assertIn('catálogo', dispatch['documentError'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM dispatch_documents').fetchone()[0], 0)
        good = copy.deepcopy(PLAN)
        names = ['Pão, trigo, forma, integral', 'Banana, prata, crua', 'Arroz, tipo 1, cozido',
                 'Iogurte, natural', 'Frango, peito, sem pele, grelhado']
        for meal, name in zip(good['meals'], names):
            meal['foods'] = [{'name': name, 'grams': 200}]
        job = self.store.ingest(self.event('pode', 'verified-menu-second-request'), 'nutri')
        self.assertTrue(job['documentRequested'])
        dispatch = self.store.reserve({'eventId': job['eventId'], 'userId': job['userId'],
                                      'phone': job['phone'], 'plan': good}, 'nutri')
        self.assertNotIn('documentError', dispatch)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM dispatch_documents').fetchone()[0], 1)
        self.assertEqual(self.store.records.list(self.patient['id'])['records'], [])

    def test_quantified_menu_uses_catalogue_and_never_records_consumption(self):
        self.ready()
        plan = copy.deepcopy(PLAN)
        foods = [
            [('Pão, trigo, francês', 70), ('Ovo, de galinha, inteiro, cozido/10minutos', 100)],
            [('Banana, prata, crua', 100)],
            [('Arroz, tipo 1, cozido', 200), ('Feijão, carioca, cozido', 150), ('Frango, peito, sem pele, grelhado', 150)],
            [('Banana, prata, crua', 100), ('Aveia, flocos, crua', 50)],
            [('Arroz, tipo 1, cozido', 200), ('Feijão, carioca, cozido', 150), ('Frango, peito, sem pele, grelhado', 150)],
        ]
        for meal, ingredients in zip(plan['meals'], foods):
            meal['foods'] = [{'name': name, 'grams': grams} for name, grams in ingredients]
        app = {'goal': 'maintainWeight', 'dailyGoals': {'energyKcal': 2200}}
        result = calculate_portions(validate_plan(plan), app, self.store.records.enrich_menu)
        self.assertLess(abs(result['totals']['energyKcal'] - 2200), 22)
        self.assertAlmostEqual(result['totals']['proteinG'],
                               sum(m['totals']['proteinG'] for m in result['meals']))
        pdf = make_pdf(plan, 'Exemplo', app, {}, demo=True, resolve=self.store.records.enrich_menu)
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b', pdf)), 3)
        self.assertEqual(self.store.records.list(self.patient['id'])['records'], [])
        plan['meals'][0]['foods'][0]['name'] = 'Alimento inexistente xyz123'
        with self.assertRaises(ValueError):
            calculate_portions(validate_plan(plan), app, self.store.records.enrich_menu)

    def ready(self):
        self.verify()
        self.store.allow_ai=True
        self.store.context(self.enrollment['token'],{'profile':{'birthday':'1995-01-10','goal':'maintainWeight','gender':'male','activityLevel':'active'}})
        self.store.menu.save(self.patient['id'],'ready',{'adult':True,'restrictionsAndHealth':'Não tenho','routineAndPreferences':'Pouco tempo para cozinhar'})

    def test_private_pdf_is_last_part_and_not_a_consumed_meal(self):
        self.ready()
        job=self.store.ingest(self.event('Quero meu PDF','pdf-request-0001'),'nutri')
        self.assertTrue(job['documentRequested'])
        body={'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'candidate':'Aqui está','plan':PLAN}
        dispatch=self.store.reserve(body,'nutri')
        self.assertEqual(len(dispatch['parts']),2)
        self.assertFalse(self.store.messaging.authorize(dispatch['parts'][1],'nutri')['approved'])
        text=self.store.messaging.authorize(dispatch['parts'][0],'nutri')
        self.store.messaging.receipt({'partId':text['partId'],'status':'accepted'})
        document=self.store.messaging.authorize(dispatch['parts'][1],'nutri')
        self.assertEqual(document['mediaType'],'document')
        pdf=base64.b64decode(document['media'])
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',pdf)),2)
        self.assertEqual(self.store.records.list(self.patient['id'])['records'],[])
        self.assertFalse(self.store.reserve(body,'nutri')['approved'])
        self.assertFalse(self.store.messaging.authorize(dispatch['parts'][1],'nutri')['approved'])

    def test_current_request_reaches_pdf_and_conflicting_plan_is_not_sent(self):
        import json
        self.ready()
        job=self.store.ingest(self.event('Quero um PDF sem banana','pdf-with-preference'),'nutri')
        self.assertIn('sem banana',json.loads(job['context']['menuPreferences'])['latestRequest'])
        self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'plan':PLAN},'nutri')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM dispatch_documents').fetchone()[0],0)

    def test_optout_blocks_pdf_even_after_text_was_sent(self):
        self.ready()
        job=self.store.ingest(self.event('Quero um PDF','pdf-optout-request'),'nutri')
        dispatch=self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'plan':PLAN},'nutri')
        first=self.store.messaging.authorize(dispatch['parts'][0],'nutri')
        self.store.messaging.receipt({'partId':first['partId'],'status':'accepted'})
        self.store.ingest(self.event('SAIR','pdf-optout-stop'),'nutri')
        self.assertFalse(self.store.messaging.authorize(dispatch['parts'][1],'nutri')['approved'])

    def test_requires_preferences_and_never_sends_an_unsolicited_plan(self):
        self.verify();self.store.allow_ai=True
        job=self.store.ingest(self.event('Olá','pdf-not-requested'),'nutri')
        dispatch=self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'candidate':'Oi','plan':PLAN},'nutri')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM dispatch_documents').fetchone()[0],0)
        self.assertFalse(job['documentRequested'])
        self.ready()
        self.store.context(self.enrollment['token'],{'profile':{'birthday':'2015-01-10'}})
        job=self.store.ingest(self.event('Quero um PDF','pdf-child-request'),'nutri')
        self.assertFalse(job['documentRequested'])

    def test_rejects_incomplete_plan_and_invented_calorie_targets(self):
        for change in ({'meals':[]},{'shopping':['Meta: 900 kcal']},{'tips':['Use 500 mg de suplemento']}):
            with self.assertRaises(ValueError):validate_plan({**PLAN,**change})
        self.ready()
        job=self.store.ingest(self.event('Quero um PDF','pdf-invalid-request'),'nutri')
        dispatch=self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'candidate':'Segue seu PDF','plan':{}},'nutri')
        self.assertIn('Não consegui',dispatch['text'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM dispatch_documents').fetchone()[0],0)

    def test_photo_meal_receipt_has_server_calories_and_saves_category(self):
        self.ready()
        job=self.store.ingest(self.event('[Foto estimada] arroz cozido no almoço','photo-food-receipt'),'nutri')
        result=self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],
          'record':{'kind':'meal','text':'Arroz, tipo 1, cozido','quantity':120,'unit':'g','mealType':'lunch','estimateSource':'photo','nutrition':{'energyKcal':99999}}},'nutri')
        self.assertIn('kcal',result['text'])
        record=self.store.records.list(self.patient['id'])['records'][0]
        self.assertEqual(record['mealType'],'lunch')
        self.assertTrue(record['estimated'])
        self.assertAlmostEqual(record['nutrition']['energyKcal'],record['nutrientsPer100g']['energy_kcal_100']*1.2,places=3)

    def test_long_content_remains_two_pages(self):
        plan=copy.deepcopy(PLAN)
        for m in plan['meals']:
            m['suggestion']=('Alimentos variados da sua rotina. '*9)[:240]
            m['alternative']=('Uma alternativa simples para variar. '*7)[:180]
        plan['shopping']=[('Legumes e frutas da estação para a sua rotina. '*2)[:65] for _ in range(10)]
        plan['tips']=[('Organize as refeições conforme sua rotina e suas preferências. '*4)[:160] for _ in range(3)]
        pdf=make_pdf(plan,'Nome fictício de demonstração',{'goal':'maintainWeight','dailyGoals':{'energyKcal':2200}},{},demo=True)
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',pdf)),2)

    def test_four_meal_legacy_plan_stays_compatible(self):
        plan=copy.deepcopy(PLAN)
        plan['meals']=[m for m in plan['meals'] if m['mealType']!='morningSnack']
        pdf=make_pdf(plan,'Exemplo',{}, {},demo=True)
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',pdf)),2)

    def test_known_milk_allergy_blocks_incompatible_pdf(self):
        with self.assertRaises(ValueError):
            make_pdf(PLAN,'Exemplo',{}, {'restrictionsAndHealth':'Tenho alergia a leite'})

    def test_declining_pdf_blocks_pending_attachment_without_cancelling_whatsapp(self):
        self.ready()
        job=self.store.ingest(self.event('Quero PDF','pdf-decline-request'),'nutri')
        dispatch=self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'plan':PLAN},'nutri')
        first=self.store.messaging.authorize(dispatch['parts'][0],'nutri')
        self.store.messaging.receipt({'partId':first['partId'],'status':'accepted'})
        with patch.object(self.store.messaging.changed,'wait',side_effect=AssertionError('A recusa do PDF não pode esperar o agrupamento.')):
            decline=self.store.messaging.collect(self.event('Não quero PDF','pdf-decline-command'),'nutri')
        self.assertTrue(decline['consentActive'])
        self.assertFalse(decline['documentRequested'])
        self.assertFalse(self.store.messaging.authorize(dispatch['parts'][1],'nutri')['approved'])


if __name__=='__main__':unittest.main()
