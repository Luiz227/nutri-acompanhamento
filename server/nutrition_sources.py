"""Additional nutrition sources. External requests contain only a barcode, no patient data."""
import json
import math
import re
import time
from urllib.request import Request, urlopen

class ProductSource:
    def __init__(self, db, fetch=None):
        self.db = db
        self.fetch = fetch or self._fetch
        self.requests = []
        db.execute('CREATE TABLE IF NOT EXISTS nutrition_products (code TEXT PRIMARY KEY,payload TEXT NOT NULL,updated REAL NOT NULL)')

    @staticmethod
    def _fetch(code):
        req = Request('https://world.openfoodfacts.org/api/v2/product/' + code + '.json?fields=code,product_name,brands,nutriments,nutrition_data_per',
                      headers={'User-Agent': 'NutriAcompanhamento/0.4 (https://github.com/Luiz227/nutri-acompanhamento)'})
        with urlopen(req, timeout=5) as response:
            return json.loads(response.read(250000))

    def product(self, code):
        if not isinstance(code, str) or not re.fullmatch(r'\d{8,14}', code):
            return None
        cached = self.db.execute('SELECT * FROM nutrition_products WHERE code=?', (code,)).fetchone()
        if cached and cached['updated'] > time.time() - 86400:
            return json.loads(cached['payload'])
        self.requests = [t for t in self.requests if t > time.time() - 60]
        if len(self.requests) >= 10:
            return None
        self.requests.append(time.time())
        try:
            raw = self.fetch(code)
            p = raw.get('product') or {}
            n = p.get('nutriments') or {}
            if raw.get('status') != 1 or not isinstance(p.get('product_name'), str) or not p['product_name'].strip():
                return None
            def number(key, limit, factor=1):
                value = n.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value * factor <= limit:
                    return None
                return value * factor
            nutrients = {'energy_kcal_100': number('energy-kcal_100g', 950), 'proteins_100': number('proteins_100g', 100),
                         'carbohydrates_100': number('carbohydrates_100g', 100), 'fat_100': number('fat_100g', 100),
                         'fiber_100': number('fiber_100g', 100), 'sodium_100': number('sodium_100g', 100000, 1000)}
            if sum(nutrients[k] or 0 for k in ('proteins_100', 'carbohydrates_100', 'fat_100')) > 110:
                return None
            if any(nutrients[k] is None for k in ('energy_kcal_100', 'proteins_100', 'carbohydrates_100', 'fat_100')):
                return None
            product = {'code': 'off:' + code, 'name': p['product_name'].strip()[:180], 'brands': str(p.get('brands') or '')[:120],
                       'nutrients': nutrients, 'source': 'Open Food Facts (ODbL)', 'url': 'https://world.openfoodfacts.org/product/' + code}
            self.db.execute('INSERT OR REPLACE INTO nutrition_products(code,payload,updated) VALUES(?,?,?)', (code, json.dumps(product), time.time()))
            return product
        except (OSError, ValueError, TypeError, AttributeError):
            return None
