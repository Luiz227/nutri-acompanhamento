import json
import unittest
from concurrent.futures import ThreadPoolExecutor
import time
import test_app as fixtures
from messaging import split_message
from photo_meals import prepare, validate_analysis
from datetime import datetime, timezone, timedelta

PLATE={'usable':True,'items':[
    {'food':'arroz branco','grams':175,'confidence':'high'},
    {'food':'bife bovino grelhado em tiras/fatiado','grams':215,'confidence':'medium'},
    {'food':'batatas fritas','grams':125,'confidence':'high'},
    {'food':'cenoura cozida','grams':30,'confidence':'medium'},
    {'food':'feijão branco cozido','grams':25,'confidence':'medium'},
    {'food':'molho escuro não identificado','grams':None,'confidence':'low'},
]}


class PhotoPipelineTests(unittest.TestCase):
    setUp=fixtures.BridgeTests.setUp
    tearDown=fixtures.BridgeTests.tearDown
    verify=fixtures.BridgeTests.verify
    event=fixtures.BridgeTests.event

    def ready(self):
        self.verify();self.store.allow_ai=True
        self.store.messaging.quiet_seconds=.02

    def photo(self, caption='Meu almoço', identifier='photo-plate-0001'):
        event={**self.event('Foto da refeição',identifier),'mediaType':'image','caption':caption}
        claim=self.store.messaging.begin_media(event,'nutri')
        self.assertTrue(claim['approved'])
        job=self.store.messaging.finish_media({'event':event,'mediaToken':claim['mediaToken'],'photo':PLATE},'nutri')
        return job,event

    def save(self, job):
        return self.store.reserve({'eventId':job['eventId'],'userId':job['userId'],'phone':job['phone'],
          'candidate':'Quer confirmar?','record':{'kind':'water','text':'injetado','quantity':9000,'unit':'ml'}},'nutri')

    def test_photo_alone_registers_plate_without_conversation_model_or_confirmation(self):
        self.ready()
        job,event=self.photo()
        self.assertEqual(job['action'],'reply', 'recognized photo bypasses conversational generation')
        result=self.save(job)
        records=self.store.records.list(self.patient['id'])['records']
        meals=[r for r in records if r['kind']=='meal']
        self.assertEqual(len(meals),5)
        self.assertTrue(all(r['mealType']=='lunch' for r in meals))
        rice=next(r for r in meals if r['text']=='arroz branco')
        self.assertEqual(rice['foodCode'],'taco:3')
        self.assertAlmostEqual(rice['nutrition']['energyKcal'],224.4523505,places=3)
        self.assertLess(rice['nutrition']['proteinG'],5)
        self.assertLess(rice['nutrition']['fatG'],1)
        beef=next(r for r in meals if 'bife' in r['text'])
        self.assertEqual(beef['foodCode'],'taco-estimate:beef-grilled')
        self.assertGreater(len(beef['referenceIds']),1)
        potato=next(r for r in meals if 'batatas' in r['text'])
        self.assertEqual(potato['foodCode'],'taco:93')
        self.assertTrue(all('nutrition' in r for r in meals))
        self.assertEqual(records[-1]['kind'],'observation')
        self.assertNotIn('código de barras',result['text'])
        self.assertNotIn('confirmar',result['text'].lower())
        self.assertNotIn('Pela foto, anotei',result['text'])
        self.assertEqual(result['text'].count('estimados pela foto'),1)
        self.assertIn('Subtotal estimado',result['text'])
        self.assertTrue(all(len(p)<=420 for p in split_message(result['text'])))
        self.assertFalse(self.save(job)['approved'])

    def test_plain_rice_never_matches_carreteiro_and_special_diets_do_not_match_beef(self):
        self.ready()
        self.assertEqual(self.store.records.closest('arroz branco')['id'],3)
        self.assertEqual(self.store.records.closest('batatas fritas')['id'],93)
        self.assertIsNone(self.store.records.reviewed('bife de soja grelhado'))
        self.assertIsNone(self.store.records.reviewed('bife de frango grelhado'))

    def test_explicit_breakfast_wins_over_current_time_and_only_half_scales_portions(self):
        records=prepare([PLATE],'Meu café da manhã, comi metade',datetime(2026,11,10,20,tzinfo=timezone(timedelta(hours=-3))))
        meals=[r for r in records if r['kind']=='meal']
        self.assertTrue(all(r['mealType']=='breakfast' for r in meals))
        self.assertEqual(meals[0]['quantity'],87.5)
        inferred=prepare([PLATE],'',datetime(2026,11,10,13,tzinfo=timezone(timedelta(hours=-3))))
        self.assertEqual(inferred[0]['mealType'],'lunch')
        self.assertEqual(inferred[0]['mealTypeSource'],'time')

    def test_explicit_non_consumption_never_creates_records(self):
        self.ready()
        job,_=self.photo('Foto de exemplo, não comi isso','photo-not-consumed')
        self.assertEqual(job['action'],'assistant')
        self.save(job)
        self.assertEqual(self.store.records.list(self.patient['id'])['records'],[])

    def test_text_after_photo_preserves_explicit_category_and_registration_is_once(self):
        self.ready()
        event={**self.event('Foto','photo-before-text'),'mediaType':'image','caption':''}
        claim=self.store.messaging.begin_media(event,'nutri')
        with ThreadPoolExecutor(max_workers=2) as pool:
            waiter=pool.submit(self.store.messaging.collect,self.event('Foi meu café da manhã','photo-category-followup'),'nutri')
            time.sleep(.05)
            older=self.store.messaging.finish_media({'event':event,'mediaToken':claim['mediaToken'],'photo':PLATE},'nutri')
            job=waiter.result(timeout=3)
        self.assertEqual(older['action'],'ignore')
        self.save(job)
        self.assertTrue(all(r['mealType']=='breakfast' for r in self.store.records.list(self.patient['id'])['records'] if r['kind']=='meal'))

    def test_another_patient_cannot_reuse_photo_source_and_stop_prevents_saving(self):
        self.ready()
        job,event=self.photo()
        photo=self.store.messaging.photo_context({'_photoSources':[event['eventId']]},'another-patient')
        self.assertIsNone(photo)
        self.store.ingest(self.event('SAIR','stop-before-photo-save'),'nutri')
        self.assertFalse(self.save(job)['approved'])
        self.assertEqual(self.store.records.list(self.patient['id'])['records'],[])

    def test_invalid_model_portions_are_rejected_and_no_nutrients_are_accepted(self):
        with self.assertRaises(ValueError):validate_analysis({'usable':True,'items':[{'food':'arroz','grams':-100,'confidence':'high'}]})
        value=validate_analysis({'usable':True,'items':[{'food':'arroz','grams':100,'confidence':'high','calories':9000,'userId':'forged'}]})
        self.assertNotIn('calories',value['items'][0])
        self.assertNotIn('userId',value['items'][0])

    def test_unreadable_photo_requests_another_photo_without_asking_for_written_grams(self):
        self.ready()
        event={**self.event('Não foi possível ler a foto','photo-unreadable'),'mediaType':'image','caption':''}
        claim=self.store.messaging.begin_media(event,'nutri')
        job=self.store.messaging.finish_media({'event':event,'mediaToken':claim['mediaToken'],'photo':None},'nutri')
        self.assertEqual(job['action'],'reply')
        result=self.save(job)
        self.assertIn('outra foto',result['text'])
        self.assertNotIn('gramas',result['text'])
        self.assertEqual(self.store.records.list(self.patient['id'])['records'],[])


if __name__=='__main__':unittest.main()
