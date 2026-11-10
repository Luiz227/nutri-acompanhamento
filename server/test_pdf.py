import base64
import copy
import re
import unittest
import test_app as fixtures
from meal_pdf import make_pdf, validate_plan
from example_menu import PLAN


class PdfTests(unittest.TestCase):
    setUp=fixtures.BridgeTests.setUp
    tearDown=fixtures.BridgeTests.tearDown
    verify=fixtures.BridgeTests.verify
    event=fixtures.BridgeTests.event

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

    def test_known_milk_allergy_blocks_incompatible_pdf(self):
        with self.assertRaises(ValueError):
            make_pdf(PLAN,'Exemplo',{}, {'restrictionsAndHealth':'Tenho alergia a leite'})

    def test_declining_pdf_blocks_pending_attachment_without_cancelling_whatsapp(self):
        self.ready()
        job=self.store.ingest(self.event('Quero PDF','pdf-decline-request'),'nutri')
        dispatch=self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],'plan':PLAN},'nutri')
        first=self.store.messaging.authorize(dispatch['parts'][0],'nutri')
        self.store.messaging.receipt({'partId':first['partId'],'status':'accepted'})
        decline=self.store.ingest(self.event('Não quero PDF','pdf-decline-command'),'nutri')
        self.assertTrue(decline['consentActive'])
        self.assertFalse(decline['documentRequested'])
        self.assertFalse(self.store.messaging.authorize(dispatch['parts'][1],'nutri')['approved'])


if __name__=='__main__':unittest.main()
