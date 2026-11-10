"""Private, bounded meal-suggestion PDFs. No model-supplied nutrient totals."""
from io import BytesIO
from xml.sax.saxutils import escape
from datetime import datetime, timezone, timedelta
from patient_profile import GOALS, age_of
from coaching import plain

MENU_REQUEST_TEXT = 'Quero sugestões gerais e flexíveis de refeições em um PDF personalizado, usando o objetivo, as restrições e as preferências que informei.'

LABELS = {'breakfast': 'Café da manhã', 'lunch': 'Almoço', 'snack': 'Lanche', 'dinner': 'Jantar'}


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
    if not isinstance(meals, list) or len(meals) != 4:
        raise ValueError('Organize as quatro refeições.')
    result = {'meals': []}
    for meal in meals:
        if not isinstance(meal, dict) or meal.get('mealType') not in LABELS:
            raise ValueError('Refeição inválida.')
        result['meals'].append({'mealType': meal['mealType'], 'suggestion': text(meal.get('suggestion'), 240),
                                'alternative': text(meal.get('alternative'), 180)})
    if {m['mealType'] for m in result['meals']} != set(LABELS):
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
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
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
    green, ink, muted, cream = [colors.HexColor(v) for v in ('#19634D', '#21392F', '#64756A', '#F7F5ED')]
    w, h = A4
    width = w-88
    def style(name, size=11, leading=16, color=ink, font='Helvetica', **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading, textColor=color, alignment=TA_LEFT, **kw)
    styles = {'title': style('title',34,39,green,'Helvetica-Bold'), 'section': style('section',21,26,green,'Helvetica-Bold'),
              'label': style('label',10,14,green,'Helvetica-Bold'), 'body': style('body',11,16),
              'small': style('small',9,12,muted), 'compact': style('compact',10,13), 'page2title': style('page2title',28,33,green,'Helvetica-Bold'), 'name':style('name',14,19,green,'Helvetica-Bold')}
    def para(text, key='body'):
        return Paragraph(escape(str(text)),styles[key])
    def card(content, background=colors.white):
        table=Table([[content]],colWidths=[width])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),background),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#DDE6DE')),
                                  ('LEFTPADDING',(0,0),(-1,-1),16),('RIGHTPADDING',(0,0),(-1,-1),16),
                                  ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
        return table
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=72,bottomMargin=60,
                         title='Seu guia de alimentação | Nutri Acompanhamento',author='Nutri Acompanhamento')
    date=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y')
    def page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(cream);canvas.rect(0,0,w,h,fill=1,stroke=0)
        canvas.setFillColor(green);canvas.circle(49,h-37,7,fill=1,stroke=0)
        canvas.setFont('Helvetica-Bold',10);canvas.drawString(64,h-41,'NUTRI ACOMPANHAMENTO')
        canvas.setFillColor(muted);canvas.setFont('Helvetica',8)
        canvas.drawRightString(w-44,h-41,'EXEMPLO • DADOS FICTÍCIOS' if demo else date)
        canvas.setStrokeColor(colors.HexColor('#D6DED4'));canvas.line(44,43,w-44,43)
        canvas.drawString(44,29,'Sugestões gerais de alimentação • Use conforme sua rotina')
        canvas.drawRightString(w-44,29,f'{document.page} / 2')
        canvas.restoreState()
    name=str(name or 'Você').strip()[:55]
    story=[para('Comer bem, do seu jeito.','title'),Spacer(1,12),para(f'Um guia preparado para {name}.','name'),Spacer(1,7),
           para('Ideias simples para variar suas refeições, respeitando o que você contou sobre sua rotina. As sugestões são flexíveis: escolha o que faz sentido para você.'),Spacer(1,16)]
    objective=GOALS.get(app.get('goal'),'organizar a alimentação')
    facts=[para('SEU OBJETIVO','label'),para(objective.capitalize())]
    energy=app.get('dailyGoals',{}).get('energyKcal')
    if isinstance(energy,(float,int)) and not isinstance(energy,bool) and 0 < energy < 12000:
        facts += [Spacer(1,5),para(f'Meta já definida no aplicativo: {energy:g} kcal/dia. Este guia não recalcula nem altera essa meta.','small')]
    story += [card(facts,colors.HexColor('#EBF1E9')),Spacer(1,17),para('Um dia com possibilidades','section'),Spacer(1,12)]
    for kind in LABELS:
        meal=next(m for m in plan['meals'] if m['mealType']==kind)
        story += [KeepTogether([card([para(LABELS[kind].upper(),'label'),Spacer(1,4),para(meal['suggestion'])]),Spacer(1,9)])]
    story += [PageBreak(),para('Variedade sem complicar.','page2title'),Spacer(1,12),para('Trocas para a sua rotina','section'),Spacer(1,10)]
    for kind in LABELS:
        meal=next(m for m in plan['meals'] if m['mealType']==kind)
        story += [para(LABELS[kind],'label'),para(meal['alternative'],'compact'),Spacer(1,6)]
    story += [Spacer(1,6),para('Uma lista para facilitar','section'),Spacer(1,9)]
    rows=[]
    items=plan['shopping']
    for i in range(0,len(items),2):
        rows.append([para('• '+items[i],'compact'),para('• '+items[i+1],'compact') if i+1<len(items) else ''])
    shopping=Table(rows,colWidths=[width/2,width/2]);shopping.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story += [shopping,Spacer(1,12)]
    for tip in plan['tips']:
        story += [para(tip,'small'),Spacer(1,4)]
    story += [Spacer(1,8),card([para('Para lembrar','label'),para('Este é um exemplo de alimentação, não uma prescrição clínica. Confira os rótulos e respeite suas alergias e restrições. Para adaptar quantidades ou tratar uma condição de saúde, converse com seu nutricionista.','small')],colors.HexColor('#EBF1E9'))]
    doc.build(story,onFirstPage=page,onLaterPages=page)
    if doc.page != 2:
        raise ValueError('O conteúdo excede o limite visual do PDF. Encurte as sugestões.')
    data=out.getvalue()
    if len(data)>500000:
        raise ValueError('Documento muito grande.')
    return data
