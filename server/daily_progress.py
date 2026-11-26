"""Daily progress from confirmed server diary records."""
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from coaching import BRASILIA, plain

METRICS = (
    ('energyKcal', 'Energia', 'kcal'),
    ('proteinG', 'Proteína', 'g'),
    ('carbsG', 'Carboidratos', 'g'),
    ('fatG', 'Gorduras', 'g'),
    ('waterMl', 'Água', 'ml'),
)
FINAL_MEAL = re.compile(r'\b(?:ultima refeicao(?: do dia)?|nao vou comer mais hoje)\b')


def progress_card(db, patient_id, event_id, message, profile, now=None):
    today = (now or datetime.now(BRASILIA)).astimezone(BRASILIA).date()
    rows = diary_rows(db, patient_id, today)
    closes_day = any(
        row_event.startswith(event_id + '#') and record['kind'] == 'meal'
        and (record.get('mealType') == 'dinner' or FINAL_MEAL.search(plain(message)))
        for row_event, record in rows
    )
    if not closes_day:
        return None
    totals, missing, estimated = summarize(record for _, record in rows)
    return render_card(today, totals, profile.get('dailyGoals', {}), missing, estimated, profile=profile)


def energy_balance(day, totals, profile, missing):
    """Estimate maintenance with the app's IOM 2005 equation, never from a diet goal."""
    from datetime import date
    from math import isfinite
    factors = {'sedentary': (1, 1), 'lowActive': (1.12, 1.14),
               'active': (1.27, 1.27), 'veryActive': (1.54, 1.45)}
    try:
        birthday = date.fromisoformat(profile['birthday'])
        age = day.year-birthday.year-((day.month, day.day) < (birthday.month, birthday.day))
        weight, height = profile['weightKg'], profile['heightCm']
        if not 19 <= age <= 129 or any(isinstance(v, bool) or not isinstance(v, (int,float)) or not isfinite(v) or v <= 0 for v in (weight,height)):
            return None
        male_factor, female_factor = factors[profile['activityLevel']]
        male = 864 - 9.72*age + male_factor*(14.2*weight + 503*height/100)
        female = 387 - 7.31*age + female_factor*(10.9*weight + 660.7*height/100)
        gender = profile['gender']
        if gender not in ('male', 'female', 'nonBinary'):
            return None
        expenditure = male if gender == 'male' else female if gender == 'female' else (male+female)/2
        if expenditure <= 0:
            return None
        intake = totals.get('energyKcal')
        delta = None if 'energyKcal' in missing or isinstance(intake,bool) or not isinstance(intake,(int,float)) or not isfinite(intake) else expenditure-intake
        return {'expenditureKcal': expenditure, 'balanceKcal': delta}
    except (KeyError, ValueError, TypeError):
        return None


def diary_rows(db, patient_id, day):
    from datetime import time, timedelta, timezone
    start = datetime.combine(day, time.min, BRASILIA)
    end = start + timedelta(days=1)
    rows = db.execute(
        "SELECT event_id,payload FROM records WHERE patient_id=? AND status='confirmed' "
        "AND json_extract(payload,'$.occurredAt')>=? AND json_extract(payload,'$.occurredAt')<?",
        (patient_id, start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()),
    )
    return [(row['event_id'], json.loads(row['payload'])) for row in rows]


def summarize(records):
    totals = dict.fromkeys((key for key, _, _ in METRICS), 0.0)
    missing = set()
    estimated = False
    for record in records:
        if record.get('estimateSource') == 'photo' and record.get('visualConfidence') == 'low':
            missing.update(key for key, _, _ in METRICS[:-1])
        if record['kind'] == 'water':
            totals['waterMl'] += record['quantity']
        if record['kind'] != 'meal':
            continue
        estimated |= bool(record.get('estimated'))
        nutrients = record.get('nutrition', {})
        for key, _, _ in METRICS[:-1]:
            value = nutrients.get(key)
            if value is None:
                missing.add(key)
            else:
                totals[key] += value
    return totals, missing, estimated


def achieved_goals(db, patient_id, event_id, profile, day=None):
    day = day or datetime.now(BRASILIA).date()
    goals = profile.get('dailyGoals', {})
    if not goals:
        return ''
    rows = diary_rows(db, patient_id, day)
    if not any(key.startswith(event_id + '#') for key, _ in rows):
        return ''
    before, _, _ = summarize(record for key, record in rows if not key.startswith(event_id + '#'))
    after, _, _ = summarize(record for _, record in rows)
    labels = {'waterMl': 'de água', 'proteinG': 'de proteína', 'carbsG': 'de carboidratos',
              'fatG': 'de gorduras', 'energyKcal': 'de energia'}
    hit = []
    for key, label in labels.items():
        goal = goals.get(key)
        if not goal or not before[key] < goal <= after[key]:
            continue
        inserted = db.execute(
            'INSERT OR IGNORE INTO daily_goal_notices(patient_id, day, metric) VALUES(?,?,?)',
            (patient_id, day.isoformat(), key),
        ).rowcount
        if inserted:
            hit.append(label)
    if not hit:
        return ''
    if hit == ['de água']:
        return 'Boa! Você bateu sua meta diária de água. 💧'
    if len(hit) == 1:
        return f'Boa! Você bateu sua meta diária {hit[0]}.'
    return 'Boa! Você bateu suas metas de hoje ' + ', '.join(hit[:-1]) + ' e ' + hit[-1] + '.'


def water_goal_reached(db, patient_id, day):
    from patient_profile import read_profile
    goal = read_profile(db, patient_id).get('dailyGoals', {}).get('waterMl')
    if not goal:
        return False
    return sum(record['quantity'] for _, record in diary_rows(db, patient_id, day)
               if record['kind'] == 'water') >= goal


def render_card(day, totals, goals, missing, estimated, profile=None):
    from PIL import Image, ImageDraw, ImageFont
    from reportlab import __file__ as reportlab_file
    from math import isfinite

    font_dir = Path(reportlab_file).parent / 'fonts'
    def font(size, bold=False):
        return ImageFont.truetype(str(font_dir / ('VeraBd.ttf' if bold else 'Vera.ttf')), size)

    def number(value, decimals=0):
        return f'{value:,.{decimals}f}'.replace(',', '_').replace('.', ',').replace('_', '.')

    def fitted(value, size, width, bold=False):
        selected = font(size, bold)
        while draw.textlength(value, font=selected) > width and size > 18:
            size -= 1
            selected = font(size, bold)
        return selected

    def target(key):
        value = goals.get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value > 0 else None

    def progress(left, top, width, value, goal, background, fill):
        draw.rounded_rectangle((left, top, left+width, top+12), radius=6, fill=background)
        length = min(width, max(0, round(width*min(value/goal, 1))))
        if length:
            draw.rounded_rectangle((left, top, left+length, top+12), radius=6, fill=fill)

    image = Image.new('RGB', (1080, 1525), '#F6F8F2')
    draw = ImageDraw.Draw(image)
    green, lime, ink, muted = '#014214', '#CFE724', '#143D24', '#52664F'
    draw.rounded_rectangle((0, -55, 1080, 588), radius=48, fill=green)

    logo = Path(__file__).resolve().parent.parent / 'assets/icon/garfofala-symbol.png'
    if not logo.exists():
        logo = Path(__file__).with_name('garfofala-symbol.png')
    if logo.exists():
        with Image.open(logo) as source:
            icon = source.convert('RGBA').resize((76, 76), Image.Resampling.LANCZOS)
            image.paste(icon, (54, 43), icon)
    draw.text((146, 66), 'GARFOFALA', font=font(25, True), fill=lime)
    months = ('JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ')
    date = f'{day.day:02d} {months[day.month-1]} {day.year}'
    draw.rounded_rectangle((793, 53, 1018, 105), radius=26, fill='#19562B')
    draw.text((905, 68), date, anchor='ma', font=font(20, True), fill='#EAF3D9')
    draw.text((59, 155), 'Seu progresso do dia', font=font(59, True), fill='white')

    energy = totals.get('energyKcal', 0)
    energy_goal = target('energyKcal')
    energy_missing = 'energyKcal' in missing
    draw.text((63, 282), 'ENERGIA REGISTRADA', font=font(20, True), fill='#C5D9C6')
    display = 'Sem cálculo' if energy_missing and energy == 0 else number(energy)+('*' if energy_missing else '')
    draw.text((56, 327), display, font=fitted(display, 100, 580, True), fill='white')
    if not (energy_missing and energy == 0):
        draw.text((65, 448), 'kcal', font=font(29), fill=lime)
    energy_caption = f'Meta do aplicativo: {number(energy_goal)} kcal' if energy_goal else 'Meta de energia ainda não definida'
    draw.text((64, 520), energy_caption, font=fitted(energy_caption, 23, 615), fill='#D6E5CD')

    # The arc shows the share of the app goal, capped visually at one turn.
    ring = (731, 281, 1007, 557)
    draw.arc(ring, 0, 360, fill='#286237', width=22)
    if energy_goal:
        percent = energy/energy_goal*100
        if percent > 0:
            draw.arc(ring, -90, -90+min(percent, 100)*3.6, fill=lime, width=22)
        percent_text = number(percent)+'%'
        draw.text((869, 378), percent_text, anchor='ma',
                  font=fitted(percent_text, 48, 205, True), fill='white')
        draw.text((869, 443), 'da meta'+('*' if energy_missing else ''),
                  anchor='ma', font=font(20), fill='#D6E5CD')
    else:
        draw.text((869, 382), 'Meta', anchor='ma', font=font(32, True), fill='white')
        draw.text((869, 432), 'não definida', anchor='ma', font=font(18), fill='#D6E5CD')

    balance = energy_balance(day, totals, profile or {}, missing)
    draw.rounded_rectangle((60, 616, 1020, 766), radius=26, fill='#E7F0DB')
    delta = balance['balanceKcal'] if balance else None
    label = ('Déficit calórico estimado' if delta is not None and delta > .5 else
             'Superávit calórico estimado' if delta is not None and delta < -.5 else
             'Equilíbrio calórico estimado' if delta is not None else 'Saldo calórico estimado')
    draw.text((86, 638), label, font=font(25, True), fill=ink)
    if delta is not None:
        draw.text((86, 683), number(abs(delta))+' kcal', font=font(42, True), fill=green)
        caption = 'Gasto estimado: '+number(balance['expenditureKcal'])+' kcal'
        draw.text((991, 691), caption, anchor='ra', font=fitted(caption, 20, 500), fill=ink)
        draw.text((991, 724), 'Gasto do perfil menos consumo registrado.', anchor='ra', font=font(18), fill=muted)
    else:
        caption = 'Consumo incompleto: não é possível estimar o déficit.' if energy_missing else 'Complete nascimento, peso, altura e atividade no perfil.'
        draw.text((86, 695), caption, font=fitted(caption, 23, 905), fill=muted)

    draw.text((61, 805), 'Seus nutrientes', font=font(29, True), fill=ink)
    for index, (key, label, unit) in enumerate(METRICS[1:4]):
        x = 60 + index*326
        top, width = 863, 308
        draw.rounded_rectangle((x, top+5, x+width, 1084), radius=26, fill='#E8EDE1')
        draw.rounded_rectangle((x, top, x+width, 1079), radius=26, fill='white')
        draw.text((x+23, top+22), label, font=font(24, True), fill=ink)
        value, goal = totals.get(key, 0), target(key)
        display = ('—' if key in missing and value == 0 else
                   number(value, 1).removesuffix(',0')+' g'+('*' if key in missing else ''))
        draw.text((x+22, top+67), display, font=fitted(display, 49, width-44, True), fill=green)
        if goal:
            progress(x+24, top+142, width-48, value, goal, '#E6EEDF', green)
            caption = 'Meta '+number(goal, 1).removesuffix(',0')+' g'
        else:
            caption = 'Meta não definida'
        if key in missing and value == 0:
            caption = 'Sem cálculo completo'
        draw.text((x+24, top+173), caption, font=fitted(caption, 18, width-48), fill=muted)

    water, water_goal = totals.get('waterMl', 0), target('waterMl')
    top = 1123
    draw.rounded_rectangle((60, top, 1020, 1353), radius=30, fill='#E7F0DB')
    draw.text((88, top+27), 'Água ao longo do dia', font=font(28, True), fill=ink)
    water_text = (number(water/1000, 1).removesuffix(',0')+' L' if water >= 1000 else number(water)+' ml')
    draw.text((85, top+80), water_text, font=font(59, True), fill=green)
    if water_goal:
        if water >= water_goal:
            caption = 'Meta de água atingida'
        else:
            caption = number(max(0, water_goal-water))+' ml para sua meta'
        draw.text((987, top+109), caption, anchor='ra',
                  font=fitted(caption, 22, 470, True), fill=green)
        progress(89, top+171, 902, water, water_goal, '#C9DABD', green)
        draw.text((88, top+198), 'Meta do aplicativo: '+number(water_goal)+' ml',
                  font=font(17), fill=muted)
    else:
        draw.text((88, top+171), 'Meta de água ainda não definida no aplicativo',
                  font=font(21), fill=muted)

    note_top = 1407
    if missing:
        draw.text((62, note_top), '* Totais parciais: há alimentos sem cálculo completo.',
                  font=font(20), fill=muted)
        note_top += 34
    if estimated:
        draw.text((62, note_top), 'Inclui estimativas de porções ou alimentos.',
                  font=font(20), fill=muted)
    elif not missing:
        draw.text((62, note_top), 'Calculado a partir dos seus registros de hoje.',
                  font=font(20), fill=muted)
    output = BytesIO()
    image.save(output, format='PNG', optimize=True)
    return output.getvalue()
