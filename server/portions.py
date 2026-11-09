"""Reviewed household measures, not model-invented gram weights.

IBGE POF 2008-2009, Tabela de Medidas Referidas (PDF page numbers).
Weights are reference portions, never a measurement of the actual meal.
https://biblioteca.ibge.gov.br/visualizacao/livros/liv50000.pdf
"""
import re
import unicodedata

SOURCE = 'IBGE POF 2008-2009, Tabela de Medidas Referidas'
URL = 'https://biblioteca.ibge.gov.br/visualizacao/livros/liv50000.pdf'
MEASURES = [
    # family, unit, size, grams, PDF page
    ('maca', 'unit', 'medium', 150, 160),
    ('maca', 'unit', 'small', 90, 160),
    ('banana prata', 'unit', 'medium', 75, 153),
    ('laranja', 'unit', 'medium', 180, 156),
    ('laranja', 'unit', 'small', 90, 156),
    ('pao frances', 'unit', 'medium', 50, 393),
    ('caqui', 'unit', 'medium', 110, 160),
    ('caqui', 'unit', 'small', 85, 160),
    ('figo', 'unit', 'medium', 55, 160),
    ('mamao papaia', 'unit', 'medium', 310, 161),
    ('mamao papaia', 'unit', 'small', 270, 161),
    ('maca', 'slice', 'medium', 37.5, 160),
]


def portion(text, unit, size='medium'):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    text = re.sub(r'[^a-z0-9]+', ' ', text).strip()
    text = text.replace('papaya', 'papaia')
    words = set(text.split())
    # A cake/juice/puree containing an apple is not one whole apple.
    if words & {'suco', 'bolo', 'torta', 'pure', 'vitamina', 'doce', 'geleia', 'salada', 'frito', 'frita', 'assada', 'assado', 'cozida', 'cozido'}:
        return None
    for family, measure, reference_size, grams, page in MEASURES:
        if measure == unit and reference_size == size and set(family.split()) <= words:
            return {'grams': grams, 'source': SOURCE, 'url': URL, 'pdfPage': page,
                    'reference': family, 'size': size, 'unit': unit}
    return None
