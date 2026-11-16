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
    rows = db.execute(
        "SELECT event_id,payload FROM records WHERE patient_id=? AND status='confirmed'",
        (patient_id,),
    )
    records = []
    closes_day = False
    for row in rows:
        record = json.loads(row['payload'])
        when = datetime.fromisoformat(record['occurredAt']).astimezone(BRASILIA)
        if when.date() != today:
            continue
        records.append(record)
        if row['event_id'].startswith(event_id + '#') and record['kind'] == 'meal':
            closes_day |= record.get('mealType') == 'dinner' or bool(FINAL_MEAL.search(plain(message)))
    if not closes_day:
        return None

    totals = dict.fromkeys((key for key, _, _ in METRICS), 0.0)
    missing = set()
    estimated = False
    for record in records:
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
    return render_card(today, totals, profile.get('dailyGoals', {}), missing, estimated)


def render_card(day, totals, goals, missing, estimated):
    from PIL import Image, ImageDraw, ImageFont
    from reportlab import __file__ as reportlab_file

    font_dir = Path(reportlab_file).parent / 'fonts'
    def font(size, bold=False):
        return ImageFont.truetype(str(font_dir / ('VeraBd.ttf' if bold else 'Vera.ttf')), size)
    def number(value):
        return f'{value:,.0f}'.replace(',', '.')

    image = Image.new('RGB', (720, 930), '#F6F5F0')
    draw = ImageDraw.Draw(image)
    green, ink, muted = '#16453A', '#173C33', '#49635A'
    draw.rectangle((0, 0, 720, 220), fill=green)
    draw.text((48, 42), 'NUTRI ACOMPANHAMENTO', font=font(20, True), fill='#D0E8DC')
    draw.text((46, 91), 'Seu progresso de hoje', font=font(43, True), fill='white')
    draw.text((48, 160), day.strftime('%d/%m/%Y') + '  •  Diário alimentar', font=font(23), fill='#D0E8DC')

    for index, (key, label, unit) in enumerate(METRICS):
        y = 250 + index * 111
        draw.rounded_rectangle((42, y, 678, y + 98), radius=18, fill='white')
        draw.text((63, y + 13), label, font=font(22, True), fill=ink)
        goal = goals.get(key)
        value = totals[key]
        display = f'{number(value)} {unit}'+ ('*' if key in missing else '')
        if key in missing and value == 0:
            display = 'Sem cálculo*'
        draw.text((653, y + 13), display, font=font(24, True), fill=green, anchor='ra')
        if goal and goal > 0:
            draw.rounded_rectangle((63, y + 50, 653, y + 60), radius=5, fill='#E2EBE6')
            length = round(590 * min(value / goal, 1))
            if length:
                draw.rounded_rectangle((63, y + 50, 63 + length, y + 60), radius=5, fill='#348567')
            draw.text((63, y + 70), f'Meta do app: {number(goal)} {unit}', font=font(16), fill=muted)
        else:
            draw.text((63, y + 58), 'Meta não definida no app', font=font(16), fill=muted)

    draw.text((47, 826), 'Dados do dia disponíveis no acompanhamento.', font=font(19), fill=muted)
    if missing:
        draw.text((47, 854), '* Alguns alimentos ficaram sem cálculo nutricional.', font=font(17), fill=muted)
    if estimated:
        draw.text((47, 882), 'Inclui estimativas de porções ou alimentos.', font=font(17), fill=muted)
    output = BytesIO()
    image.save(output, format='PNG', optimize=True)
    return output.getvalue()
