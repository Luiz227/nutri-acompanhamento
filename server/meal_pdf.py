"""Private, bounded meal-suggestion PDFs. No model-supplied nutrient totals."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from datetime import datetime, timezone, timedelta
from patient_profile import GOALS, age_of
from coaching import plain
import math

MENU_REQUEST_TEXT = 'Quero sugestões gerais e flexíveis de refeições em um PDF personalizado, usando o objetivo, as restrições e as preferências que informei.'

LABELS = {'breakfast': 'Café da manhã', 'morningSnack': 'Lanche da manhã', 'lunch': 'Almoço', 'snack': 'Lanche da tarde', 'dinner': 'Jantar'}


def eligible(profile, app, message=''):
    if not profile or profile.get('stage') != 'ready':
        return False
    age = age_of(app)
    if (age is not None and age < 18) or (age is None and profile.get('adult') is not True):
        return False
    import re
    health = plain(str(profile.get('restrictionsAndHealth', '')) + ' ' + message)
    return not re.search(r'\b(diabet\w*|renal|rins|gestante|gravida|amament\w*|anorexia|bulimia|insulina|cancer|oncolog\w*)\b', health)


def validate_plan(raw):
    if not isinstance(raw, dict):
        raise ValueError('Sugestões incompletas.')
    def text(value, limit):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
            raise ValueError('Texto de sugestão inválido.')
        value = value.strip()
        # Documents are general food ideas, never new calorie prescriptions.
        import re
        if re.search(r'\b\d+(?:[.,]\d+)?\s*(?:kcal|calorias?|mg|mcg|ui)\b|https?://', value, re.I):
            raise ValueError('Não inclua metas ou doses inventadas nas sugestões.')
        return value
    meals = raw.get('meals')
    if not isinstance(meals, list) or len(meals) not in (4, 5):
        raise ValueError('Organize as refeições do dia.')
    result = {'meals': []}
    for meal in meals:
        if not isinstance(meal, dict) or meal.get('mealType') not in LABELS:
            raise ValueError('Refeição inválida.')
        result['meals'].append({'mealType': meal['mealType'], 'suggestion': text(meal.get('suggestion'), 240),
                                'alternative': text(meal.get('alternative'), 180)})
        if 'foods' in meal:
            foods = meal['foods']
            if not isinstance(foods, list) or not 1 <= len(foods) <= 8:
                raise ValueError('Informe os alimentos de cada refeição.')
            result['meals'][-1]['foods'] = []
            for food in foods:
                if not isinstance(food, dict):
                    raise ValueError('Alimento inválido.')
                grams = food.get('grams')
                if isinstance(grams, bool) or not isinstance(grams, (int, float)) or not math.isfinite(grams) or not 1 <= grams <= 1000:
                    raise ValueError('Porção inválida.')
                item = {'name': text(food.get('name'), 100), 'grams': grams}
                if food.get('catalogueQuery'):
                    item['catalogueQuery'] = text(food['catalogueQuery'], 180)
                result['meals'][-1]['foods'].append(item)
    if len({m['mealType'] for m in result['meals']}) != len(meals) or not {'breakfast','lunch','snack','dinner'}.issubset({m['mealType'] for m in result['meals']}):
        raise ValueError('Não repita refeições.')
    for key, maximum, size in [('shopping', 30, 65), ('tips', 3, 160)]:
        values = raw.get(key)
        if not isinstance(values, list) or not 1 <= len(values) <= maximum:
            raise ValueError('Lista de sugestões inválida.')
        result[key] = [text(v, size) for v in values]
    return result


def calculate_portions(plan, app, resolve):
    """Fit a suggested menu to the existing app energy goal using catalogue data."""
    target = app.get('dailyGoals', {}).get('energyKcal')
    if target is None:
        return None
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or not 0 < target < 12000:
        raise ValueError('Meta calórica inválida.')
    if not resolve or any(not meal.get('foods') for meal in plan['meals']):
        raise ValueError('O cardápio precisa de alimentos e porções calculáveis.')
    meals = []
    for meal in plan['meals']:
        records = [{'kind': 'meal', 'text': food['name'], 'quantity': food['grams'],
                    'catalogueQuery': food.get('catalogueQuery')} for food in meal['foods']]
        resolve(records, auto_save=True)
        if any(not record.get('nutrition') or any(record['nutrition'].get(key) is None
               for key in ('energyKcal', 'proteinG', 'carbsG', 'fatG')) for record in records):
            raise ValueError('Faltam referências nutricionais para o cardápio.')
        meals.append({'mealType': meal['mealType'], 'records': records})
    base_energy = sum(record['nutrition']['energyKcal'] for meal in meals for record in meal['records'])
    if base_energy <= 0:
        raise ValueError('Cardápio sem energia calculável.')
    factor = target / base_energy
    if not .5 <= factor <= 2:
        raise ValueError('Reorganize o cardápio para aproximá-lo da meta do aplicativo.')
    totals = dict.fromkeys(('energyKcal', 'proteinG', 'carbsG', 'fatG'), 0)
    for meal in meals:
        meal['totals'] = dict.fromkeys(totals, 0)
        for record in meal['records']:
            record['quantity'] = round(record['quantity'] * factor)
            if not 1 <= record['quantity'] <= 1000:
                raise ValueError('Revise as porções do cardápio.')
            for key, column in (('energyKcal', 'energy_kcal_100'), ('proteinG', 'proteins_100'),
                                ('carbsG', 'carbohydrates_100'), ('fatG', 'fat_100')):
                value = record['nutrientsPer100g'][column] * record['quantity'] / 100
                record['nutrition'][key] = value
                meal['totals'][key] += value
                totals[key] += value
    if abs(totals['energyKcal'] - target) > max(10, target * .01):
        raise ValueError('O arredondamento das porções se afastou da meta.')
    return {'meals': meals, 'totals': totals, 'target': target}


def make_pdf(plan, name, app, preferences, demo=False, resolve=None):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.lib.pagesizes import A4
    plan = validate_plan(plan)
    if preferences:
        import re
        health=plain(str(preferences.get('restrictionsAndHealth','')))
        stated=plain(' '.join(str(preferences.get(key,'')) for key in
                              ('foodPreferences','routineAndPreferences','latestRequest','preferenceUpdate')))
        foods_to_avoid = re.findall(
            r'\b(?:nao (?:como|gosto de|quero)|evito|sem)\s+(?:de\s+)?([a-z]+(?:-[a-z]+)?)', stated
        )
        foods=plain(' '.join(m['suggestion']+' '+m['alternative']+' '+' '.join(f['name'] for f in m.get('foods', [])) for m in plan['meals'])+' '+' '.join(plan['shopping']+plan['tips']))
        for food in foods_to_avoid:
            if food not in {'arroz','feijao','frango','banana','queijo','peixe','ovo','ovos','carne','leite','trigo','amendoim','iogurte','pao','tomate','aveia','camarao','porco'}:
                continue
            if re.search(r'\b'+re.escape(food.rstrip('s'))+r's?\b',foods):
                raise ValueError('O guia inclui um alimento que a pessoa pediu para evitar.')
        for trigger, ingredients in [
            (r'leite|lactose', r'leite|queijo|iogurte|requeijao|manteiga'),
            (r'amendoim',r'amendoim'), (r'ovo',r'ovo|ovos|omelete|maionese'),
            (r'gluten|celiac',r'pao|trigo|macarrao|aveia'),
        ]:
            if re.search(trigger,health) and re.search(r'\b(?:'+ingredients+r')\b',foods):
                raise ValueError('As sugestões precisam respeitar a restrição informada.')
    calculated = calculate_portions(plan, app, resolve) if resolve else None
    if calculated:
        for meal in plan['meals']:
            selected = next(value for value in calculated['meals'] if value['mealType'] == meal['mealType'])
            meal['suggestion'] = ', '.join(
                f"{record['quantity']:.0f} g de {record['text']}" for record in selected['records'])
    from reportlab.pdfgen import canvas as pdfcanvas
    green, accent, gold, ink, muted, cream, pale = [colors.HexColor(v) for v in
        ('#103B2C','#236447','#DCEE71','#24413B','#687D76','#F8F7F3','#EDF3ED')]
    w,h=A4
    shopping_pages = []
    shopping_text = 'Para as compras: ' + ', '.join(plan['shopping']) + '.'
    tips_text = ' '.join(plan['tips'])
    shopping_top = 328 + 55 * len(plan['meals'])
    small_style = ParagraphStyle('shopping-fit', fontName='Helvetica', fontSize=7.2, leading=9.2)
    needed = sum(Paragraph(escape(value), small_style).wrap(w-86, 1000)[1]
                 for value in (shopping_text, tips_text))
    if shopping_top + 31 + needed > 737:
        entries, top = [], 215
        for item in plan['shopping']:
            item_height = Paragraph(escape(item), ParagraphStyle(
                'shopping-item', fontName='Helvetica', fontSize=10, leading=14)).wrap(w-112, 1000)[1] + 14
            if top + item_height > 730:
                shopping_pages.append(entries)
                entries, top = [], 215
            entries.append((item, item_height))
            top += item_height
        if entries:
            shopping_pages.append(entries)
    detail_pages = []
    if calculated:
        cards = []
        top = 246
        for meal in sorted(calculated['meals'], key=lambda m: list(LABELS).index(m['mealType'])):
            foods = ' • '.join(f"{record['quantity']:.0f} g de {record['text']}" for record in meal['records'])
            style = ParagraphStyle('detail-fit', fontName='Helvetica', fontSize=9, leading=12)
            height = Paragraph(escape(foods), style).wrap(w-110, 1000)[1] + 60
            if top + height > 723:
                detail_pages.append(cards)
                cards, top = [], 246
            cards.append((meal, foods, height))
            top += height + 9
        if cards:
            detail_pages.append(cards)
    out=BytesIO()
    c=pdfcanvas.Canvas(out,pagesize=A4)
    c.setTitle('Seu plano alimentar | GarfoFala')
    c.setAuthor('GarfoFala')
    name=str(name or 'Você').strip()[:55]
    date=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y')
    def paragraph(value,x,top,width,size=10,leading=14,color=ink,bold=False):
        st=ParagraphStyle('text',fontName='Helvetica-Bold' if bold else 'Helvetica',fontSize=size,leading=leading,textColor=color)
        p=Paragraph(escape(str(value)),st)
        _,height=p.wrap(width,1000)
        p.drawOn(c,x,h-top-height)
        return height
    def box(x,top,width,height,fill=colors.white):
        c.setFillColor(fill);c.roundRect(x,h-top-height,width,height,13,stroke=0,fill=1)
    logo = Path(__file__).resolve().parent.parent / 'assets/icon/garfofala-symbol.png'
    if not logo.exists():
        logo = Path(__file__).with_name('garfofala-symbol.png')
    def header(kicker,title,subtitle):
        c.setFillColor(cream);c.rect(0,0,w,h,stroke=0,fill=1)
        c.saveState()
        path=c.beginPath();path.rect(0,h-175,w,175);c.clipPath(path,stroke=0)
        c.setFillColor(green);c.rect(0,h-175,w,175,stroke=0,fill=1)
        c.setFillColor(gold);c.circle(w-38,h-52,84,stroke=0,fill=1)
        c.setFillColor(accent);c.circle(w-13,h-146,88,stroke=0,fill=1)
        c.restoreState()
        if logo.exists():
            c.drawImage(str(logo),w-109,h-114,width=64,height=64,mask='auto')
        paragraph(kicker,43,39,420,9,12,colors.HexColor('#CBDFD2'),True)
        paragraph(title,43,68,440,27,33,colors.white,True)
        paragraph(subtitle,43,112,420,10,14,colors.HexColor('#D8E8DE'))
    def footer(number):
        c.setStrokeColor(colors.HexColor('#DEE5DE'));c.line(42,52,w-42,52)
        paragraph('GARFOFALA  /  SUGESTÕES PERSONALIZADAS',42,h-43,450,7,10,muted)
        c.setFillColor(accent);c.setFont('Helvetica-Bold',8);c.drawRightString(w-42,34,f'{number:02d} / {2 + len(detail_pages) + len(shopping_pages):02d}')
    header('BEM-ESTAR  /  NUTRIÇÃO','Seu plano alimentar','Equilíbrio, variedade e escolhas possíveis no dia a dia.')
    box(42,187,w-84,42)
    paragraph('NOME: '+name,57,201,350,9,12)
    paragraph('DATA: '+date,440,201,100,9,12)
    objective=GOALS.get(app.get('goal'),'organizar a alimentação')
    paragraph('UM DIA COM POSSIBILIDADES',43,245,490,12,16,green,True)
    summary='Seu objetivo: '+objective+'. Sugestões flexíveis para sua rotina.'
    energy=app.get('dailyGoals',{}).get('energyKcal')
    if isinstance(energy,(int,float)) and not isinstance(energy,bool) and 0<energy<12000:
        summary=f'Seu objetivo: {objective}. Meta do aplicativo: {energy:g} kcal/dia.'
    paragraph(summary,43,267,490,9,12,muted)
    meals=sorted(plan['meals'],key=lambda m:list(LABELS).index(m['mealType']))
    # Bounded content is fitted inside each card; never clips longer valid plans.
    count=len(meals);gap=11;card_h=min(96,(487-(count-1)*gap)/count)
    top=292
    for index,meal in enumerate(meals,1):
        box(42,top,w-84,card_h)
        box(55,top+13,38,32,pale)
        paragraph(f'{index:02d}',64,top+22,28,13,16,accent,True)
        paragraph(LABELS[meal['mealType']].upper(),108,top+14,w-165,10,13,green,True)
        if meal['mealType']=='morningSnack':
            suggestion='Se fizer sentido para sua fome: '+meal['suggestion']
        else:
            suggestion=meal['suggestion']
        if calculated and len(suggestion) > 220:
            suggestion='Refeição com ' + str(len(meal.get('foods', []))) + ' alimentos. Veja os pesos e valores de cada refeição nas páginas de porções e nutrientes.'
        alternative='Alternativa: '+meal['alternative']
        text_width=w-165
        size=9.2
        while size>=7.2:
            def measure(text):
                p=Paragraph(escape(text),ParagraphStyle('fit',fontName='Helvetica',fontSize=size,leading=size+2.3))
                return p.wrap(text_width,1000)[1]
            a,b=measure(suggestion),measure(alternative)
            if a+b+39<=card_h:break
            size-=.2
        if a+b+39>card_h:raise ValueError('Sugestão longa demais para o cartão do PDF.')
        paragraph(suggestion,108,top+32,text_width,size,size+2.3)
        paragraph(alternative,108,top+35+a,text_width,size,size+2.3,muted)
        top+=card_h+gap
    footer(1);c.showPage()
    header('ESCOLHAS INTELIGENTES','Varie com liberdade','Ideias escolhidas a partir das suas preferências e rotina.')
    paragraph('TROCAS PARA O DIA A DIA',43,207,480,12,16,green,True)
    top=233
    for meal in meals:
        box(42,top,w-84,48)
        c.setFillColor(accent);c.roundRect(42,h-top-48,5,48,2,stroke=0,fill=1)
        paragraph(LABELS[meal['mealType']].upper(),59,top+10,w-118,9,12,green,True)
        paragraph(meal['alternative'],59,top+24,w-118,8.3,10.5,muted)
        top+=55
    top+=10
    box(42,top,w-84,70,pale)
    paragraph('HIDRATAÇÃO E ROTINA',59,top+15,450,11,14,green,True)
    water=app.get('dailyGoals',{}).get('waterMl')
    hydration='Mantenha água por perto ao longo do dia. Respeite sua sede e as orientações de quem acompanha você.'
    if isinstance(water,(int,float)) and not isinstance(water,bool) and 0<water<=20000:
        hydration=f'Meta de água já definida no aplicativo: {water:g} ml/dia. Distribua o consumo pela rotina e respeite as orientações do seu profissional.'
    paragraph(hydration,59,top+37,w-118,9.3,13)
    top+=85
    paragraph('PARA FACILITAR SUAS ESCOLHAS',43,top,480,11,14,green,True)
    # The shopping list is generated for this person, never generic allergen swaps.
    shopping='Sua lista completa de compras está nas páginas seguintes.' if shopping_pages else shopping_text
    tips=' '.join(plan['tips'])
    size=8.8
    while size>=7.2:
        st=ParagraphStyle('fit2',fontSize=size,leading=size+2,fontName='Helvetica')
        needed=sum(Paragraph(escape(t),st).wrap(w-86,1000)[1] for t in (shopping,tips))
        if top+23+needed+8<=737:break
        size-=.2
    if top+23+needed+8>737:raise ValueError('Conteúdo longo demais para a segunda página.')
    used=paragraph(shopping,43,top+23,w-86,size,size+2,muted)
    paragraph(tips,43,top+27+used,w-86,size,size+2,muted)
    box(42,746,w-84,37)
    note=('EXEMPLO COM DADOS FICTÍCIOS. ' if demo else '')+'Sugestões educativas, não uma prescrição clínica. Respeite suas alergias e restrições; necessidades específicas pedem acompanhamento nutricional.'
    paragraph(note,53,754,w-106,7.3,9.5,muted)
    footer(2);c.showPage()
    for page_number, cards in enumerate(detail_pages, 3):
        header('SEU CARDÁPIO DO DIA','Porções e nutrientes','Quantidades sugeridas para a meta já definida no aplicativo.')
        totals = calculated['totals']
        paragraph(f"Meta do aplicativo: {calculated['target']:.0f} kcal | Cardápio: {totals['energyKcal']:.0f} kcal",43,190,500,11,15,green,True)
        paragraph(f"Proteínas: {totals['proteinG']:.1f} g   Carboidratos: {totals['carbsG']:.1f} g   Gorduras: {totals['fatG']:.1f} g",43,213,500,10,14)
        top = 246
        for meal, foods, height in cards:
            box(42,top,w-84,height)
            paragraph(LABELS[meal['mealType']].upper(),55,top+9,w-110,10,13,green,True)
            paragraph(foods,55,top+27,w-110,9,12)
            values = meal['totals']
            paragraph(f"{values['energyKcal']:.0f} kcal | Proteínas {values['proteinG']:.1f} g | Carboidratos {values['carbsG']:.1f} g | Gorduras {values['fatG']:.1f} g",
                      55,top+height-18,w-110,8,10,muted)
            top += height + 9
        paragraph('Pesos da parte comestível, no preparo descrito. Valores estimados pelas tabelas nutricionais. As alternativas das páginas anteriores precisam de novo cálculo antes de substituir estas porções.',
                  43,top+3,w-86,8,11,muted)
        footer(page_number);c.showPage()
    for page_number, entries in enumerate(shopping_pages, 3 + len(detail_pages)):
        header('PARA SUA ROTINA','Lista de compras','Ingredientes das sugestões escolhidas para você.')
        top = 215
        for item, height in entries:
            box(42,top,w-84,height-4)
            paragraph(item,56,top+5,w-112,10,14)
            top += height
        footer(page_number);c.showPage()
    c.save()
    data=out.getvalue()
    if len(data)>500000:raise ValueError('Documento muito grande.')
    return data
