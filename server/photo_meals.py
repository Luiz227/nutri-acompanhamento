"""Validated visual observations; identity/consent are always enforced elsewhere."""
import re
import math
from datetime import datetime, timezone, timedelta
from coaching import plain


def validate_analysis(raw):
    if not isinstance(raw, dict) or raw.get('usable') is not True:
        raise ValueError('Imagem não utilizável.')
    items=raw.get('items')
    if not isinstance(items,list) or not 1 <= len(items) <= 10:
        raise ValueError('Alimentos não identificados.')
    result=[]
    for item in items:
        if not isinstance(item,dict): raise ValueError('Item inválido.')
        name=item.get('food'); grams=item.get('grams'); confidence=item.get('confidence')
        if not isinstance(name,str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError('Nome inválido.')
        if confidence=='low' and grams is None:
            result.append({'food':name.strip(),'grams':None,'confidence':'low'})
            continue
        if isinstance(grams,bool) or not isinstance(grams,(int,float)) or not math.isfinite(grams) or not 0 < grams <= 2000:
            raise ValueError('Porção inválida.')
        if confidence not in ('high','medium','low'): raise ValueError('Confiança inválida.')
        result.append({'food':name.strip(),'grams':round(grams,1),'confidence':confidence})
    return {'usable':True,'items':result}


def prepare(analyses, user_text, now=None):
    text=plain(user_text)
    # A recipe, example, or question is not a statement of consumption.
    if re.search(r'\b(nao comi|nao e meu|so um exemplo|foto de exemplo|so uma receita|ainda vou comer|vou comer|pretendo comer|quantas calorias|qual a quantidade de calorias|pdf|sugestao|cardapio|receita|ideia de)\b',text):
        return None
    now=now or datetime.now(timezone(timedelta(hours=-3)))
    category=None
    for pattern, kind in [(r'cafe da manha|desjejum','breakfast'),(r'almoco','lunch'),(r'jantar|janta\b','dinner'),(r'lanche|cafe da tarde','snack')]:
        if re.search(pattern,text): category=kind;break
    inferred=category is None
    if inferred:
        category='breakfast' if 5 <= now.hour < 11 else 'lunch' if 11 <= now.hour < 15 else 'snack' if 15 <= now.hour < 19 else 'dinner'
    items=[]
    for analysis in analyses:
        items.extend(validate_analysis(analysis)['items'])
    if len(items)>10: return None
    # Low-confidence components remain explicitly unresolved, not fabricated.
    records=[({'kind':'observation','text':item['food'],'estimateSource':'photo','visualConfidence':'low'} if item['confidence']=='low' else {'kind':'meal','text':item['food'],'quantity':item['grams'],'unit':'g',
              'mealType':category,'mealTypeSource':'time' if inferred else 'explicit',
              'estimateSource':'photo','visualConfidence':item['confidence']}) for item in items]
    if re.search(r'\b(?:comi|consumi|so|apenas)\s+(?:a\s+)?metade\b',text):
        for record in records:
            if record['kind']=='meal':record['quantity']=round(record['quantity']/2,1)
    return records


def clean_food_name(text):
    name=plain(text)
    name=re.sub(r'\b(em tiras|em cubos|fatiado|fatiada|picado|picada|fatiado fatiada|aproximadamente)\b',' ',name)
    for a,b in [('batatas','batata'),('fritas','frita'),('fritos','frito'),('cozidas','cozida'),('grelhadas','grelhada')]:
        name=re.sub(r'\b'+a+r'\b',b,name)
    return re.sub(r'[^a-z0-9]+',' ',name).strip()
