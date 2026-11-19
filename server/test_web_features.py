import json
import uuid
import unittest
from datetime import datetime, timedelta

import test_web_accounts as accounts
from web_features import evolution, feature_request
from web_accounts import AuthError
from coaching import BRASILIA


class WebFeatureTests(unittest.TestCase):
    tearDown = accounts.WebAccountTests.tearDown
    signup = accounts.WebAccountTests.signup
    def setUp(self):
        accounts.WebAccountTests.setUp(self)
        _, _, session = self.signup()
        self.owner = self.store.web.patient(session)

    # Do not inherit the account tests; this class exercises the web features.
    def request(self, route, method='GET', body=None, query=None, patient=None):
        with self.store.lock, self.store.db:
            return feature_request(self.store, patient or self.owner, '/web-api/'+route, method, body or {}, query or {})

    def add(self, kind, quantity, unit, **extra):
        return self.request('entry', 'POST', {'record': {'kind':kind, 'text':extra.pop('text',kind),
            'quantity':quantity,'unit':unit,**extra},'requestId':str(uuid.uuid4())})

    def test_bmi_latest_weight_and_no_fabricated_history(self):
        result = self.request('evolution')
        self.assertEqual(result['bmi'], 27.3)
        self.assertEqual(result['weights'], [])
        self.assertEqual(result['trackedDays'], 0)
        earlier = (datetime.now(BRASILIA)-timedelta(days=2)).isoformat()
        self.add('weight', 78, 'kg', occurredAt=earlier)
        self.add('weight', 77, 'kg')
        result = self.request('evolution')
        self.assertEqual(result['currentWeightKg'], 77)
        self.assertEqual(result['changeKg'], -1)
        self.assertEqual(result['bmi'], 26.6)
        self.assertEqual(len(result['weights']), 2)

    def test_entry_idempotence_revision_and_app_cursor(self):
        body = {'requestId':str(uuid.uuid4()), 'record':{'kind':'water','text':'Água','quantity':250,'unit':'ml'}}
        entry = self.request('entry','POST',body)
        self.assertEqual(entry, self.request('entry','POST',body))
        before = self.store.records.list(self.owner['id'], revisions=True)
        self.assertEqual(len(before['records']),1)
        body['id']=entry['id'];body['record']['quantity']=500
        self.request('entry','POST',body)
        changes = self.store.records.list(self.owner['id'], before['nextCursor'], revisions=True)
        self.assertEqual(changes['records'][0]['quantity'],500)
        self.request('remove-entry','POST',{'id':entry['id']})
        removed = self.store.records.list(self.owner['id'],changes['nextCursor'],revisions=True,removals=True)
        self.assertTrue(removed['records'][0]['removed'])
        self.assertEqual(self.request('evolution')['trackedDays'],0)

    def test_other_account_cannot_read_edit_or_delete_records(self):
        entry = self.add('water',400,'ml')
        _,_,session = self.signup('5511977776666')
        other = self.store.web.patient(session)
        self.assertEqual(self.request('export',patient=other)['records'],[])
        for route, body in [('remove-entry',{'id':entry['id']}),('entry',{'id':entry['id'],'record':{'kind':'water','text':'Água','quantity':1,'unit':'ml'}})]:
            with self.assertRaises(AuthError): self.request(route,'POST',body,patient=other)

    def test_profile_goals_preserved_preferences_and_nutrient_resolver(self):
        self.request('profile','POST',{'profile':{'dailyGoals':{'waterMl':2200},'heightCm':180}})
        refreshed = self.store.db.execute('SELECT * FROM patients WHERE id=?',(self.owner['id'],)).fetchone()
        self.assertEqual(json.loads(refreshed['context'])['appProfile']['gender'],'male')
        self.assertEqual(evolution(self.store,refreshed)['bmi'],24.4)
        self.request('preferences','POST',{'name':'Luiz','hours':['09:00','15:00'],'reminders':True})
        self.assertEqual(self.request('preferences')['hours'],['09:00','15:00'])
        with self.assertRaises(AuthError): self.request('preferences','POST',{'name':'Luiz','hours':['99:00'],'reminders':True})
        self.add('meal',100,'g',text='Arroz, tipo 1, cozido',mealType='lunch')
        exported = self.request('export')['records']
        self.assertGreater(exported[0]['nutrition']['energyKcal'],100)

    def test_library_is_private_and_recipe_logs_once(self):
        item = self.request('library','POST',{'name':'Meu almoço','kind':'recipe','foods':[
            {'text':'Arroz, tipo 1, cozido','quantity':100,'unit':'g'},
            {'text':'Feijão, carioca, cozido','quantity':80,'unit':'g'}]})['items'][0]
        body={'id':item['id'],'requestId':str(uuid.uuid4()),'mealType':'lunch', 'occurredAt':datetime.now(BRASILIA).isoformat()}
        self.request('library-log','POST',body)
        self.request('library-log','POST',body)
        self.assertEqual(len(self.request('export')['records']),2)
        self.assertGreater(self.request('evolution')['averages']['energyKcal'],100)
        _,_,session=self.signup('5511977776666')
        other=self.store.web.patient(session)
        self.assertEqual(self.request('library',patient=other)['items'],[])
        with self.assertRaises(AuthError):self.request('library-log','POST',body,patient=other)
        self.request('library-remove','POST',{'id':item['id']})
        self.assertEqual(self.request('library')['items'],[])
        self.assertEqual(len(self.request('export')['records']),2)

    def test_minor_bmi_has_no_adult_label_and_missing_nutrients_not_zero_average(self):
        self.request('profile','POST',{'profile':{'birthday':(datetime.now(BRASILIA).date()-timedelta(days=16*365)).isoformat()}})
        p=self.store.db.execute('SELECT * FROM patients WHERE id=?',(self.owner['id'],)).fetchone()
        self.assertIsNone(evolution(self.store,p)['bmiCategory'])
        self.add('weight',79,'kg')
        self.assertIsNone(self.request('evolution')['averages']['energyKcal'])
        with self.assertRaises(AuthError):self.request('evolution',query={'days':['100000']})


