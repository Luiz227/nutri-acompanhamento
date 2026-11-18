"""Verified food choices for generated menus, with exact catalogue resolution."""
from food_composition import FIELDS, normalized, additional_food
from pof import pof_food

# A compact set keeps the PDF prompt useful without sending the entire catalogue.
STAPLES = (
    'Arroz, tipo 1, cozido', 'Arroz, integral, cozido', 'Aveia, flocos, crua',
    'Pão, trigo, forma, integral', 'Pão, trigo, francês', 'Pão, de queijo, assado',
    'Batata, doce, cozida', 'Batata, inglesa, cozida', 'Mandioca, cozida',
    'Feijão, carioca, cozido', 'Feijão, preto, cozido', 'Lentilha, cozida',
    'Abobrinha, italiana, cozida', 'Abobrinha, italiana, refogada',
    'Alface, crespa, crua', 'Tomate, com semente, cru', 'Brócolis, cozido',
    'Cenoura, cozida', 'Cenoura, crua', 'Pepino, cru',
    'Banana, prata, crua', 'Banana, nanica, crua', 'Maçã, Argentina, com casca, crua',
    'Laranja, pêra, crua', 'Mamão, Papaia, cru', 'Abacate, cru',
    'Frango, peito, sem pele, cozido', 'Frango, peito, sem pele, grelhado',
    'Carne, bovina, patinho, sem gordura, grelhado', 'Tilápia, filé, grelhado',
    'Ovo, de galinha, inteiro, cozido/10minutos', 'Omelete, de queijo',
    'Queijo, minas, frescal', 'Iogurte, natural', 'Café, infusão 10%',
    'Amendoim, torrado, salgado', 'Castanha-de-caju, torrada, salgada',
    'Castanha-do-Brasil, crua',
)


def menu_options(foods):
    names = set(STAPLES)
    return [{'name': food['name'], 'energyKcalPer100g': round(food['nutrients']['energy_kcal_100'], 1)}
            for food in foods if food['name'] in names
            and all(isinstance(food['nutrients'].get(key), (int, float)) for key in FIELDS[:4])]


def resolve_menu(records, foods):
    """Never substitute an ingredient by a fuzzy match while planning a menu."""
    index = {normalized(food['name']): food for food in foods}
    columns = dict(zip(('energyKcal', 'proteinG', 'carbsG', 'fatG'), FIELDS[:4], strict=True))
    for record in records:
        food = (index.get(normalized(record['text'])) or pof_food(record['text'])
                or additional_food(record['text'], record.get('catalogueQuery')))
        if not food or not all(isinstance(food['nutrients'].get(column), (int, float))
                               for column in columns.values()):
            raise ValueError('Escolha os alimentos pelo nome completo do catálogo do cardápio.')
        record.update(foodName=food['name'], source=food.get('source', 'TACO/NEPA/UNICAMP (2011)'),
                      nutrientsPer100g=food['nutrients'],
                      nutrition={key: food['nutrients'][column] * record['quantity'] / 100
                                 for key, column in columns.items()})
