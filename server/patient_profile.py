"""Validated, self-reported app profile; never a clinician-approved plan."""
import math
import json
from datetime import date, datetime, timedelta, timezone

GOALS={'loseWeight':'perder peso','maintainWeight':'manter peso','gainWeight':'ganhar peso'}
ACTIVITY={'sedentary':'sedentário','lowActive':'pouco ativo','active':'ativo','veryActive':'muito ativo'}
GENDERS={'male':'masculino','female':'feminino','nonBinary':'não binário'}

def validate_profile(raw):
    if not isinstance(raw, dict):
        raise ValueError('Perfil inválido.')
    result={}
    for field, allowed in (('gender',GENDERS),('goal',GOALS),('activityLevel',ACTIVITY)):
        if raw.get(field) in allowed:
            result[field]=raw[field]
        elif field in raw and raw[field] is not None:
            raise ValueError('Opção de perfil inválida: '+field)
    if raw.get('birthday') is not None:
        birthday=date.fromisoformat(raw['birthday'])
        today=datetime.now(timezone(timedelta(hours=-3))).date()
        if not 0 <= (today-birthday).days <= 130*366:
            raise ValueError('Data de nascimento inválida.')
        result['birthday']=birthday.isoformat()
    def number(source, field, minimum, maximum):
        value=source.get(field)
        if value is None:
            return None
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError('Valor de perfil inválido: '+field)
        return value
    for field, low, high in [('heightCm',30,300),('weightKg',1,600),('targetWeightKg',1,600),('weeklyWeightGoalKg',-5,5)]:
        value=number(raw,field,low,high)
        if value is not None:
            result[field]=value
    if raw.get('dailyGoals') is not None:
        if not isinstance(raw['dailyGoals'],dict):
            raise ValueError('Metas inválidas.')
        result['dailyGoals']={}
        for field,low,high in [('energyKcal',1,20000),('proteinG',0,2000),('carbsG',0,3000),('fatG',0,2000),('waterMl',0,20000)]:
            value=number(raw['dailyGoals'],field,low,high)
            if value is not None:
                result['dailyGoals'][field]=value
        result['dailyGoals']['origin']='configuração/estimativa do aplicativo, não prescrição profissional'
    return result

def profile_context(profile):
    labels={**profile}
    if profile.get('goal') in GOALS:
        labels['goalDescription']=GOALS[profile['goal']]
    if profile.get('gender') in GENDERS:
        labels['genderDescription']=GENDERS[profile['gender']]
    if profile.get('activityLevel') in ACTIVITY:
        labels['activityDescription']=ACTIVITY[profile['activityLevel']]
    return {'appProfile':profile,'profileSummary':'Perfil atual sincronizado do aplicativo (dados informados e metas do app, não prescrição): '+json.dumps(labels,ensure_ascii=False)}

def read_profile(db, patient_id):
    row=db.execute('SELECT context FROM patients WHERE id=?',(patient_id,)).fetchone()
    if not row:
        return {}
    context=json.loads(row['context'])
    return context.get('appProfile') or {}

def age_of(profile):
    if not profile.get('birthday'):
        return None
    birthday=date.fromisoformat(profile['birthday'])
    today=datetime.now(timezone(timedelta(hours=-3))).date()
    return today.year-birthday.year-((today.month,today.day)<(birthday.month,birthday.day))
