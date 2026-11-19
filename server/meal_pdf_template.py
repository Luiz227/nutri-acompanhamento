"""Weekly meal plan laid out to match the supplied A4 reference document."""
from io import BytesIO
from math import cos, sin, radians
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from food_composition import normalized
from portions import portion

GREEN = colors.HexColor('#014214')
INK = colors.HexColor('#014214')
CREAM = colors.HexColor('#FCF6EF')
LIME = colors.HexColor('#CFE724')
PALE = colors.HexColor('#E8F1DF')
MUTED = colors.HexColor('#52664F')
W, H = A4
DAY_NAMES = ('Segunda-Feira', 'Terça-Feira', 'Quarta-Feira', 'Quinta-Feira', 'Sexta-Feira', 'Sábado', 'Domingo')
LABELS = {'breakfast': 'Café da manhã', 'morningSnack': 'Colação',
          'lunch': 'Almoço', 'snack': 'Lanche da tarde', 'dinner': 'Jantar'}
GROUPS = {'carbs': 'Carboidratos', 'protein': 'Proteínas', 'fat': 'Gorduras',
          'fruit': 'Frutas', 'vegetable': 'Verduras e legumes', 'legume': 'Leguminosas'}


def food_group(record):
    name = normalized(record['foodName'])
    if name.startswith(('banana', 'maca', 'mamao', 'laranja', 'abacaxi', 'morango', 'uva', 'pera')):
        return 'fruit'
    if name.startswith(('alface', 'tomate', 'brocolis', 'cenoura', 'abobrinha', 'pepino')):
        return 'vegetable'
    if name.startswith(('feijao', 'lentilha', 'grao de bico')):
        return 'legume'
    if name.startswith(('amendoim', 'castanha', 'abacate', 'azeite')):
        return 'fat'
    if name.startswith(('frango', 'carne', 'ovo', 'omelete', 'queijo', 'iogurte', 'peixe', 'tilapia', 'leite')):
        return 'protein'
    return 'carbs'


def household(record):
    grams = record['quantity']
    name = record['text']
    for unit, singular, plural in (('unit', 'unidade', 'unidades'), ('slice', 'fatia', 'fatias'),
                                   ('tablespoon', 'colher de sopa', 'colheres de sopa')):
        measure = portion(name, unit)
        if measure:
            count = grams / measure['grams']
            label = singular if count <= 1 else plural
            amount = f'{count:.1f}'.replace('.', ',')
            return f'Aprox. {amount} {label} de {name} — ({grams:.0f} g)'
    return f'{name} — ({grams:.0f} g)'


def render_weekly(days, name, app, preferences, demo=False):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    c.setTitle('Plano alimentar semanal | GarfoFala')
    c.setAuthor('GarfoFala')
    name = str(name or 'Seu cardápio').strip()[:55]
    logo=Path(__file__).with_name('garfofala-symbol.png')
    if not logo.exists():
        logo=Path(__file__).parent.parent/'assets/icon/garfofala-symbol.png'
    records = {}
    for day in days.values():
        for meal in day['calculated']['meals']:
            for record in meal['records']:
                records.setdefault(record['foodName'], record)
    grouped = {key: [record for record in records.values() if food_group(record) == key] for key in GROUPS}

    def text(value, x, top, width, size=13, font='Helvetica', color=colors.black, align=0):
        p = Paragraph(escape(str(value)), ParagraphStyle(
            'copy', fontName=font, fontSize=size, leading=size*1.25, textColor=color, alignment=align))
        _, height = p.wrap(width, 2000)
        p.drawOn(c, x, H-top-height)
        return height

    def leaves():
        c.saveState()
        c.setFillColor(GREEN)
        c.setStrokeColor(GREEN)
        c.setLineWidth(2)
        c.line(8,H,115,H-94)
        for x, top, angle in ((16,19,-28),(39,23,35),(39,44,-40),(64,43,30),
                              (64,69,-40),(88,64,33),(85,93,-35),(108,85,28),(12,67,-45)):
            c.saveState()
            c.translate(x,H-top)
            c.rotate(angle)
            leaf=c.beginPath()
            leaf.moveTo(0,-21)
            leaf.curveTo(-11,-9,-9,12,0,21)
            leaf.curveTo(9,12,11,-9,0,-21)
            c.drawPath(leaf,stroke=0,fill=1)
            c.restoreState()
        c.restoreState()

    def frame(cream=False, branch=True):
        c.setFillColor(CREAM if cream else colors.white)
        c.rect(0,0,W,H,fill=1,stroke=0)
        c.setFillColor(GREEN)
        c.rect(W-18,0,18,H,fill=1,stroke=0)
        if branch:
            leaves()

    def brand():
        if logo.exists():
            c.drawImage(str(logo),W-250,H-799,width=27,height=27,mask='auto')
        text('GarfoFala',W-221,765,180,25,'Times-Italic',GREEN,2)
        text('ACOMPANHAMENTO ALIMENTAR',W-234,798,194,6.5,'Helvetica',MUTED,2)

    def finish():
        brand()
        c.showPage()

    def heading(title, top=43, size=32):
        used=text(title,110,top,W-155,size,'Times-Italic',GREEN,1)
        c.setStrokeColor(GREEN)
        c.setLineWidth(1)
        c.line(180,H-top-used-2,W-115,H-top-used-2)

    def cover_title(value, top, size):
        c.saveState()
        c.setFillColor(GREEN)
        width=W-280
        while c.stringWidth(value,'Helvetica-Bold',size)*.66>width and size>14:
            size-=1
        c.translate(400,H-top-size)
        c.scale(.66,1)
        c.setFont('Helvetica-Bold',size)
        c.drawCentredString(0,0,value)
        c.restoreState()

    def divider(lines):
        frame(True)
        top=253
        for line in lines:
            top += text(line,42,top,W-84,21,'Helvetica',MUTED,1)+12
        c.setFillColor(GREEN)
        path=c.beginPath()
        path.moveTo(W/2-24,H-425);path.lineTo(W/2+24,H-425)
        path.lineTo(W/2+24,H-535);path.lineTo(W/2+43,H-535)
        path.lineTo(W/2,H-591);path.lineTo(W/2-43,H-535)
        path.lineTo(W/2-24,H-535);path.close()
        c.drawPath(path,stroke=0,fill=1)
        finish()

    def measure_meal(meal, description, size):
        values = [LABELS[meal['mealType']]] + [household(r) for r in meal['records']]
        values += ['Opção de substituição', description['alternative']]
        total=14
        for value in values:
            total += Paragraph(escape(value),ParagraphStyle('measure',fontSize=size,leading=size*1.25)).wrap(W-88,2000)[1]+2
        return total

    # Cover uses the same plate placement, cream background, rules and condensed heading.
    frame(True,False)
    asset=Path(__file__).with_name('menu-cover-fruit.jpg')
    if not asset.exists():
        asset=Path(__file__).parent.parent/'assets/data/menu-cover-fruit.jpg'
    if asset.exists():
        c.drawImage(str(asset),0,0,width=234,height=H,mask='auto')
    cover_title(name.upper(),142,40)
    c.setStrokeColor(GREEN);c.setLineWidth(4)
    c.line(258,H-294,W-48,H-294)
    cover_title('PLANO',314,52)
    cover_title('ALIMENTAR',374,52)
    c.line(263,H-462,W-44,H-462)
    if demo:
        text('EXEMPLO COM DADOS FICTÍCIOS',265,510,270,8,'Helvetica',MUTED,1)
    text('GarfoFala',244,737,290,36,'Times-Italic',GREEN,1)
    if logo.exists():
        c.drawImage(str(logo),254,H-783,width=38,height=38,mask='auto')
    text('SEU ACOMPANHAMENTO ALIMENTAR',250,791,280,8,'Helvetica',MUTED,1)
    c.showPage()
    divider(['Abaixo segue sua opção de cardápio', 'SEMANA ALIMENTAR'])

    for day_name, day in zip(DAY_NAMES, days.values(), strict=True):
        meals=sorted(day['calculated']['meals'],key=lambda m:list(LABELS).index(m['mealType']))
        descriptions={meal['mealType']:meal for meal in day['plan']['meals']}
        # Keep two pages per day while fitting longer food descriptions.
        size=14
        split=4 if len(meals)==5 else 3
        while size>=9:
            heights=[measure_meal(meal,descriptions[meal['mealType']],size) for meal in meals]
            possible=[index for index in range(1,len(meals))
                      if sum(heights[:index])<=624 and sum(heights[index:])<=550]
            if possible:
                split=min(possible,key=lambda index:abs(index-split))
                break
            size-=.5
        if size<9:
            raise ValueError('Reduza os textos das refeições para caber no modelo semanal.')
        for segment in (meals[:split],meals[split:]):
            frame()
            heading(day_name)
            top=125
            for meal in segment:
                description=descriptions[meal['mealType']]
                title=LABELS[meal['mealType']]+(' • '+description['time'] if description.get('time') else '')
                top+=text(title,36,top,W-86,size,'Helvetica-Bold')+3
                for record in meal['records']:
                    top+=text(household(record),36,top,W-86,size)+2
                top+=10
                top+=text('Opção de substituição',36,top,W-86,size,'Helvetica-Bold')+2
                top+=text(descriptions[meal['mealType']]['alternative'],36,top,W-86,size)+14
            if segment==meals[split:]:
                totals=day['calculated']['totals']
                top+=text('Resumo do dia',36,top,W-86,12,'Helvetica-Bold',INK)+4
                text(f"{totals['energyKcal']:.0f} kcal | Proteínas {totals['proteinG']:.1f} g | "
                     f"Carboidratos {totals['carbsG']:.1f} g | Gorduras {totals['fatG']:.1f} g",
                     36,top,W-86,10,color=INK)
            finish()

    divider(['Lista de substituição de alimentos',
             'Consulte as opções e quantidades', 'para variar o seu cardápio'])

    frame(True)
    text('Olá!',42,33,400,38,'Times-Italic',INK)
    text('Esta lista reúne alimentos do seu cardápio em grupos, com porções calculadas pelas tabelas nutricionais.',
         46,103,W-104,15,color=INK)
    guidance=[
        ('Entenda os grupos','Identifique carboidratos, proteínas, gorduras, frutas, verduras e leguminosas.'),
        ('Combine os alimentos','Use as refeições dos sete dias como ponto de partida para suas escolhas.'),
        ('Consulte as porções','O peso indicado se refere à parte comestível, no preparo descrito.'),
        ('Varie o cardápio','Escolha opções compatíveis com seus gostos, horários e rotina.'),
        ('Respeite suas restrições','Confira ingredientes e rótulos antes de realizar qualquer troca.'),
        ('Planeje as refeições','Organize suas compras e o preparo dos alimentos ao longo da semana.'),
    ]
    for index,(title,copy) in enumerate(guidance):
        x=45+(index//3)*275;top=200+(index%3)*160
        c.setFillColor(GREEN if index%2==0 else CREAM)
        c.roundRect(x,H-top-135,235,135,12,stroke=0,fill=1)
        color=colors.white if index%2==0 else INK
        text(title,x+14,top+16,207,14,'Helvetica-Bold',color,1)
        text(copy,x+14,top+48,207,12,color=color,align=1)
    text('Porções de mesma energia podem ter nutrientes diferentes. As trocas são aproximações; '
         'para manter os totais do dia, peça o recálculo pelo WhatsApp.',
         50,710,W-118,12,color=INK,align=1)
    finish()

    def wheel(title, keys):
        frame(True, False)
        text('Lista de substituição', 34, 40, 295, 33, 'Times-Italic', INK, 1)
        text(title, 34, 165, 295, 29, 'Times-Italic', INK, 1)
        c.setFillColor(PALE)
        c.setStrokeColor(GREEN)
        c.roundRect(377, H-285, 181, 270, 22, stroke=1, fill=1)
        text('Para variar suas escolhas', 389, 38, 155, 11, 'Helvetica-Bold', INK)
        text('O diagrama ilustra grupos de alimentos. Escolha as opções compatíveis com suas '
             'preferências e restrições nas tabelas personalizadas das próximas páginas. '
             'As trocas aproximam a energia e podem alterar os macronutrientes.',
             389, 81, 155, 11, color=INK)
        asset=Path(__file__).with_name('menu-wheel-breakfast.jpg')
        if not asset.exists():
            asset=Path(__file__).parent.parent/'assets/data/menu-wheel-breakfast.jpg'
        # Reuse only food photographs from the supplied illustration.
        # All diagram backgrounds, headings and rules are drawn in brand colors.
        photos={
            'carbs':[(195,366),(132,411),(91,473)],
            'protein':[(380,362),(485,462),(503,537)],
            'fat':[(72,589),(92,655),(188,759)],
            'fruit':[(370,766)], 'vegetable':[(495,631)], 'legume':[],
        }
        cx,cy,r=296,283,250
        fills=('#E8F1DF','#D9ECC7','#EDF5C2','#CFE724')
        for index,key in enumerate(keys):
            c.setFillColor(colors.HexColor(fills[index]))
            c.wedge(cx-r,cy-r,cx+r,cy+r,index*90,90,stroke=0,fill=1)
            angle=radians(index*90+45)
            x=cx+cos(angle)*143
            top=H-(cy+sin(angle)*143)
            text(GROUPS[key],x-69,top-12,138,15,'Times-Italic',INK,1)
            names=list(dict.fromkeys(record['foodName'].split(',')[0] for record in grouped[key]))[:4]
            text(' • '.join(names) or 'Consulte seu cardápio',x-70,top+20,140,10,color=INK,align=1)
            for photo_index,(source_x,source_top) in enumerate(photos[key]):
                angle=radians(index*90+18+photo_index*27)
                target_x=cx+cos(angle)*213
                target_y=cy+sin(angle)*213
                c.saveState()
                path=c.beginPath()
                path.circle(target_x,target_y,20)
                c.clipPath(path,stroke=0)
                c.drawImage(str(asset),target_x-source_x,target_y-(H-source_top),width=W,height=H)
                c.restoreState()
        c.setFillColor(GREEN);c.circle(cx,cy,82,stroke=0,fill=1)
        text(title,cx-69,H-cy-31,138,23,'Times-Italic',LIME,1)
        c.showPage()

    def table_group(top,key,energy):
        label=GROUPS[key].upper()
        text('GRUPO  —  '+label,32,top,W-80,11,'Helvetica-Bold',INK)
        top+=24
        text(f'Porção de referência de aproximadamente {energy:g} kcal',32,top,W-80,9,color=INK)
        top+=22
        rows=[['Alimento e preparo','Peso estimado','Energia']]
        for record in grouped[key][:16]:
            kcal=record['nutrientsPer100g']['energy_kcal_100']
            if kcal<=0:
                continue
            grams=round(energy*100/kcal)
            if not 1<=grams<=1000:
                continue
            rows.append([record['foodName'],f'{grams} g',f'{kcal*grams/100:.0f} kcal'])
        if len(rows)==1:
            text('As opções deste grupo serão ajustadas conforme suas preferências.',32,top,W-80,10,color=INK)
            return top+45
        style=ParagraphStyle('table',fontName='Helvetica',fontSize=8.5,leading=10,textColor=INK)
        cells=[[Paragraph(escape(value),style) for value in row] for row in rows]
        table=Table(cells,colWidths=[335,100,95])
        table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,-1),PALE),('GRID',(0,0),(-1,-1),.7,GREEN),
            ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ]))
        _,height=table.wrap(W-65,2000)
        if top+height>730:
            raise ValueError('Tabela de substituição extensa demais para o modelo.')
        table.drawOn(c,32,H-top-height)
        return top+height+25

    def tables(title, groups):
        frame(True,False)
        text(title.upper(),130,17,W-260,8,'Helvetica-Bold',INK,1)
        text('Opções de substituição',90,46,W-180,31,'Times-Italic',INK,1)
        top=130
        for key,energy in groups:
            top=table_group(top,key,energy)
        text('Valores calculados pelas referências usadas no cardápio. As equivalências são de energia. '
             'O preparo pode alterar os resultados.',35,735,W-95,8,color=INK)
        finish()

    wheel('Café da Manhã',('carbs','protein','fat','fruit'))
    tables('Café da manhã',(('carbs',70),('protein',90),('fat',90)))
    tables('Frutas e vegetais',(('fruit',70),('vegetable',40)))
    wheel('Lanches Intermediários',('carbs','protein','fat','fruit'))
    tables('Lanches intermediários',(('carbs',70),('protein',90),('fat',90)))
    wheel('Almoço e Jantar',('carbs','protein','legume','vegetable'))
    tables('Almoço e jantar',(('carbs',100),('protein',150),('legume',70)))
    tables('Verduras, legumes e frutas',(('vegetable',40),('fruit',70)))
    frame(True)
    text('Cada dia é uma oportunidade\npara cuidar de você.'.replace('\n',' '),
         70,310,W-150,35,'Helvetica-Bold',GREEN,1)
    text('Sugestões estimadas a partir da meta do aplicativo. '
         'Converse com seu nutricionista para avaliação individual e adaptações clínicas.',
         86,602,W-180,11,color=MUTED,align=1)
    finish()
    c.save()
    pdf=output.getvalue()
    if len(pdf)>500000:
        raise ValueError('Documento semanal muito grande.')
    return pdf
