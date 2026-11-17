import unittest
from sync.stores import lidl
from tests.util import FakeHttp, load


class LidlTest(unittest.TestCase):
    def test_parse_unit(self):
        self.assertEqual(lidl.parse_unit(["1kg = 6.33", "3Stk."]), (6.33, "kg"))
        self.assertEqual(lidl.parse_unit(["1l = 0.89", "1.5l"]), (0.89, "l"))
        self.assertEqual(lidl.parse_unit(["3Stk."]), (None, None))
        self.assertEqual(lidl.parse_unit([]), (None, None))

    def test_parse_categories(self):
        cats = lidl.parse_categories(load("lidl_categories.json"))
        self.assertEqual([(c["id"], c["name"]) for c in cats], [("1001", "Fruta y verdura"), ("1002", "Carne fresca")])

    def test_parse_products(self):
        products = lidl.parse_products(load("lidl_products.json"), "Fruta y verdura", "Frutas", 0)
        p = products[0]
        self.assertEqual(
            (p.id, p.name, p.price, p.unitPrice, p.unitLabel, p.size, p.cat, p.sub),
            ("8800521561963_ES", "Aguacate ecológico", 2.85, 6.33, "kg", "3 uds", "Fruta y verdura", "Frutas"),
        )
        self.assertTrue(p.image.startswith("https://"))

    def test_producto_a_granel_usa_su_precio_como_precio_por_kilo(self):
        data = {"products": [{"id": "1_ES", "title": "Banana", "brand": None, "imageUrl": None,
                              "price": {"price": 1.29, "annotations": ["1kg"]}}]}
        p = lidl.parse_products(data, "Fruta y verdura", "Frutas", 0)[0]
        self.assertEqual((p.unitPrice, p.unitLabel, p.size), (1.29, "kg", "1 kg"))

    def test_fetch_recorre_categorias_y_subcategorias(self):
        base = lidl.BASE
        http = FakeHttp({
            base + "/categories": load("lidl_categories.json"),
            base + "/categories/1001/categories": load("lidl_subcategories.json"),
            base + "/categories/1001/categories/1001/products": load("lidl_products.json"),
            base + "/categories/1001/categories/1002/products": None,  # 204: sin productos
        })
        products = lidl.fetch(http, limit=1)
        self.assertEqual(len(products), 3)
        self.assertEqual(http.headers, {"Accept-Language": "es"})

    def test_categoria_sin_subcategorias_se_pide_directamente(self):
        base = lidl.BASE
        http = FakeHttp({
            base + "/categories": {"categories": [{"id": "1003", "name": "Pescado y marisco", "hasSubcategories": False}]},
            base + "/categories/1003/products": load("lidl_products.json"),
        })
        products = lidl.fetch(http)
        self.assertEqual(len(products), 3)
        self.assertEqual((products[0].cat, products[0].sub), ("Pescado y marisco", ""))
