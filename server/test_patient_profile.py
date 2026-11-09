import unittest
import test_app as fixtures
from patient_profile import validate_profile

class ProfileTests(unittest.TestCase):
    setUp=fixtures.BridgeTests.setUp
    tearDown=fixtures.BridgeTests.tearDown
    event=fixtures.BridgeTests.event
    verify=fixtures.BridgeTests.verify

    def update(self, **changes):
        profile={'gender':'male','birthday':'1995-01-10','goal':'gainWeight','activityLevel':'active','heightCm':180,'weightKg':75,
                 'targetWeightKg':80,'dailyGoals':{'energyKcal':2500,'proteinG':150,'carbsG':300,'fatG':70,'waterMl':2200}}
        profile.update(changes)
        return self.store.context(self.enrollment['token'],{'profile':profile})

    def test_app_goal_gender_and_daily_targets_reach_model_context(self):
        self.verify()
        self.store.allow_ai=True
        self.update()
        job=self.store.ingest(self.event('Qual é minha meta?','profile-goal-query'),'nutri')
        self.assertEqual(job['context']['appProfile']['goal'],'gainWeight')
        self.assertEqual(job['context']['appProfile']['gender'],'male')
        self.assertEqual(job['context']['appProfile']['dailyGoals']['energyKcal'],2500)
        self.assertNotIn('approvedPlanSummary',job['context'])

    def test_known_adult_goal_and_activity_skip_redundant_questions_for_male(self):
        self.verify()
        self.update()
        self.store.menu.offer(self.patient['id'])
        reply=self.store.menu.handle(self.patient['id'],'sim')
        self.assertIn('ganhar peso',reply)
        self.assertNotIn('18 anos',reply)
        self.assertNotIn('atividade física',reply)
        self.assertNotIn('amamenta',reply.lower())
        self.assertNotIn('gesta',reply.lower())
        self.assertEqual(self.store.menu.get(self.patient['id'])['stage'],'health')

    def test_female_question_considers_reported_profile_and_missing_activity_only_is_asked(self):
        self.verify()
        self.update(gender='female')
        self.store.menu.offer(self.patient['id'])
        reply=self.store.menu.handle(self.patient['id'],'sim')
        self.assertIn('gestação',reply)
        self.update(activityLevel=None)
        self.store.menu.save(self.patient['id'],'offer',{})
        reply=self.store.menu.handle(self.patient['id'],'sim')
        self.assertIn('atividade física',reply)
        self.assertIn('ganhar peso',reply)
        self.assertNotIn('qual é seu objetivo',reply.lower())

    def test_updating_profile_replaces_targets_without_erasing_other_context_or_name(self):
        self.verify()
        self.store.context(self.enrollment['token'],{'recentDiarySummary':'Diário do app'})
        self.update()
        self.update(goal='maintainWeight',targetWeightKg=None,dailyGoals={'energyKcal':2200})
        context=self.store.me(self.enrollment['token'])['context']
        self.assertEqual(context['recentDiarySummary'],'Diário do app')
        self.assertEqual(context['appProfile']['dailyGoals']['energyKcal'],2200)
        self.assertNotIn('targetWeightKg',context['appProfile'])
        self.assertEqual(context['appProfile']['goal'],'maintainWeight')

    def test_irrelevant_health_answer_does_not_become_absence_of_allergies(self):
        self.verify()
        self.update()
        self.store.menu.offer(self.patient['id'])
        self.store.menu.handle(self.patient['id'],'sim')
        reply=self.store.menu.handle(self.patient['id'],'como de tudo')
        self.assertIn('alergias',reply)
        self.assertEqual(self.store.menu.get(self.patient['id'])['stage'],'health')

    def test_invalid_targets_and_gender_are_rejected(self):
        for profile in ({'gender':'invalid'},{'dailyGoals':{'energyKcal':float('nan')}},{'birthday':'2099-01-01'},{'dailyGoals':{'proteinG':True}}):
            with self.assertRaises((ValueError,TypeError)):
                validate_profile(profile)
