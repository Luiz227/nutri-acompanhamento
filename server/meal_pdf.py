"""Private, bounded meal-suggestion PDFs. No model-supplied nutrient totals."""
from io import BytesIO
from xml.sax.saxutils import escape
from datetime import datetime, timezone, timedelta
from patient_profile import GOALS, age_of
from coaching import plain

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
    if len({m['mealType'] for m in result['meals']}) != len(meals) or not {'breakfast','lunch','snack','dinner'}.issubset({m['mealType'] for m in result['meals']}):
        raise ValueError('Não repita refeições.')
    for key, maximum, size in [('shopping', 10, 65), ('tips', 3, 160)]:
        values = raw.get(key)
        if not isinstance(values, list) or not 1 <= len(values) <= maximum:
            raise ValueError('Lista de sugestões inválida.')
        result[key] = [text(v, size) for v in values]
    return result


def make_pdf(plan, name, app, preferences, demo=False):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.lib.pagesizes import A4
    plan = validate_plan(plan)
    if preferences:
        import re
        health=plain(str(preferences.get('restrictionsAndHealth','')))
        foods=plain(' '.join(m['suggestion']+' '+m['alternative'] for m in plan['meals'])+' '+' '.join(plan['shopping']))
        for trigger, ingredients in [
            (r'leite|lactose', r'leite|queijo|iogurte|requeijao|manteiga'),
            (r'amendoim',r'amendoim'), (r'ovo',r'ovo|ovos|omelete|maionese'),
            (r'gluten|celiac',r'pao|trigo|macarrao|aveia'),
        ]:
            if re.search(trigger,health) and re.search(r'\b(?:'+ingredients+r')\b',foods):
                raise ValueError('As sugestões precisam respeitar a restrição informada.')
    from reportlab.pdfgen import canvas as pdfcanvas
    green, accent, gold, ink, muted, cream, pale = [colors.HexColor(v) for v in
        ('#173E35','#327760','#D7AD63','#24413B','#687D76','#F8F7F3','#EDF3ED')]
    w,h=A4
    out=BytesIO()
    c=pdfcanvas.Canvas(out,pagesize=A4)
    c.setTitle('Seu plano alimentar | Nutri Acompanhamento')
    c.setAuthor('Nutri Acompanhamento')
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
    def header(kicker,title,subtitle):
        c.setFillColor(cream);c.rect(0,0,w,h,stroke=0,fill=1)
        c.saveState()
        path=c.beginPath();path.rect(0,h-175,w,175);c.clipPath(path,stroke=0)
        c.setFillColor(green);c.rect(0,h-175,w,175,stroke=0,fill=1)
        c.setFillColor(gold);c.circle(w-38,h-52,84,stroke=0,fill=1)
        c.setFillColor(accent);c.circle(w-13,h-146,88,stroke=0,fill=1)
        c.restoreState()
        paragraph(kicker,43,39,420,9,12,colors.HexColor('#CBDFD2'),True)
        paragraph(title,43,68,440,27,33,colors.white,True)
        paragraph(subtitle,43,112,420,10,14,colors.HexColor('#D8E8DE'))
    def footer(number):
        c.setStrokeColor(colors.HexColor('#DEE5DE'));c.line(42,52,w-42,52)
        paragraph('NUTRI ACOMPANHAMENTO  /  SUGESTÕES PERSONALIZADAS',42,h-43,450,7,10,muted)
        c.setFillColor(accent);c.setFont('Helvetica-Bold',8);c.drawRightString(w-42,34,f'{number:02d} / 02')
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
    shopping='Para as compras: '+', '.join(plan['shopping'])+'.'
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
    footer(2);c.showPage();c.save()
    data=out.getvalue()
    if len(data)>500000:raise ValueError('Documento muito grande.')
    return data
