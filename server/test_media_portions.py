import json
import time
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
import test_app as fixtures
from records import validate_record


class MediaPortionTests(unittest.TestCase):
    setUp = fixtures.BridgeTests.setUp
    tearDown = fixtures.BridgeTests.tearDown
    event = fixtures.BridgeTests.event
    verify = fixtures.BridgeTests.verify

    def media(self, identifier='photo-event-0001'):
        return {**self.event('', identifier), 'mediaType': 'image'}

    def test_average_apple_is_150g_and_stores_reference_not_model_calories(self):
        self.verify()
        raw = {'kind':'meal','text':'maçã','quantity':1,'unit':'unit','mealType':'snack'}
        self.store.records.propose(self.patient['id'], 'apple-meal-0001', raw, auto_save=True)
        r = self.store.records.list(self.patient['id'])['records'][0]
        self.assertEqual(r['quantity'],150)
        self.assertTrue(r['estimated'])
        self.assertEqual(r['portionReference']['pdfPage'],160)
        self.assertIn('IBGE', r['portionReference']['source'])
        self.assertGreater(r['nutrition']['energyKcal'],0)
        self.assertAlmostEqual(r['nutrition']['energyKcal'],r['nutrientsPer100g']['energy_kcal_100']*1.5,places=3)
        small=validate_record({**raw,'quantity':2,'portionSize':'small'})
        self.assertEqual(small['quantity'],180)
        for text in ('bolo de maçã','suco de maçã','prato desconhecido'):
            with self.assertRaises(ValueError): validate_record({**raw,'text':text})

    def test_photo_estimate_is_not_presented_as_weighed(self):
        r=validate_record({'kind':'meal','text':'arroz cozido','quantity':120,'unit':'g','mealType':'lunch','estimateSource':'photo'})
        self.assertTrue(r['estimated'])
        self.verify()
        reply=self.store.records.propose(self.patient['id'],'photo-estimate-receipt',r,auto_save=True)
        self.assertIn('estimados pela foto',reply)

    def test_media_requires_verified_owner_and_deduplicates_before_paid_call(self):
        e=self.media()
        self.assertFalse(self.store.messaging.begin_media(e,'nutri')['approved'])
        self.verify()
        self.assertFalse(self.store.messaging.begin_media({**e,'instance':'other'},'nutri')['approved'])
        claim=self.store.messaging.begin_media(e,'nutri')
        self.assertTrue(claim['approved'])
        self.assertFalse(self.store.messaging.begin_media(e,'nutri')['approved'])
        self.assertEqual(self.store.messaging.finish_media({'event':{**e,'text':'maçã'},'mediaToken':'wrong'},'nutri')['action'],'ignore')
        self.store.ingest(self.event('SAIR','stop-event-0001'),'nutri')
        self.assertEqual(self.store.messaging.finish_media({'event':{**e,'text':'maçã'},'mediaToken':claim['mediaToken']},'nutri')['action'],'ignore')

    def test_text_waits_for_photo_and_combines_once_in_arrival_order(self):
        self.verify()
        self.store.allow_ai=True
        self.store.messaging.quiet_seconds=.06
        e=self.media()
        claim=self.store.messaging.begin_media(e,'nutri')
        with ThreadPoolExecutor(max_workers=2) as pool:
            text=pool.submit(self.store.messaging.collect,self.event('foi no almoço','text-after-photo-0001'),'nutri')
            time.sleep(.12)
            self.assertFalse(text.done(), 'text must wait while media is processing')
            older=self.store.messaging.finish_media({'event':{**e,'text':'[Foto estimada] 120 g de arroz'},'mediaToken':claim['mediaToken']},'nutri')
            job=text.result(timeout=3)
        self.assertEqual(older['action'],'ignore')
        self.assertEqual(job['action'],'assistant')
        self.assertIn('120 g de arroz\nfoi no almoço',job['message'])
        self.assertFalse(self.store.messaging.begin_media(e,'nutri')['approved'])

    def test_expired_media_does_not_block_text_forever(self):
        self.verify()
        self.store.allow_ai=True
        self.store.messaging.quiet_seconds=.01
        e=self.media()
        self.store.messaging.begin_media(e,'nutri')
        self.store.db.execute('UPDATE inbox SET created=? WHERE id=?',(time.time()-95,e['eventId']))
        self.store.db.commit()
        job=self.store.messaging.collect(self.event('olá','text-with-expired-photo'),'nutri')
        self.assertIn('Falha ao ler',job['message'])
        self.assertIn('olá',job['message'])


if __name__ == '__main__': unittest.main()
