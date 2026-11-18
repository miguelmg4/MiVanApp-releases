import unittest
from sync.stores import lidl
from tests.util import FakeHttp, load


class LidlTest(unittest.TestCase):
    def test_parse_unit(self):
        self.assertEqual(lidl.parse_unit(["1kg = 6.33", "3Stk."]), (6.33, "kg"))
        self.assertEqual(lidl.parse_unit(["1l = 0.89", "1.5l"]), (0.89, "l"))
        self.assertEqual(lidl.parse_unit(["3Stk."]), (None, None))
        self.assertEqual(lidl.parse_unit([]), (None, None))

    def test_precio_por_100_gramos_o_mililitros_se_pasa_a_kilo_o_litro(self):
        self.assertEqual(lidl.parse_unit(["100g = 2.31", "80g"]), (23.1, "kg"))
        self.assertEqual(lidl.parse_unit(["100ml = 0.65", "200ml"]), (6.5, "l"))
        data = {"products": [{"id": "1_ES", "title": "Magnesio", "brand": None, "imageUrl": None,
                              "price": {"price": 1.85, "annotations": ["100g = 2.31", "80g"]}}]}
        self.assertEqual(lidl.parse_products(data, "Otros", "", 0)[0].size, "80 g")

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


def item(pid, title, price, subtitles=("1kg = 2.00", "500g"), line="Food"):
    return {"id": pid, "title": title, "brand": None, "subtitles": list(subtitles), "price": price,
            "imageUrl": "https://mam.cdn.schwarz/m/1_m.png?t=1&im=Resize%3d(144)", "productLine": line}


def prev(pid, name, cat, sub="", order=0):
    return {"id": pid, "name": name, "price": 9.99, "cat": cat, "sub": sub, "catOrder": order}


class SearchHttp:
    """Imita el buscador de Lidl: sin categorías (204) y como mucho `cap` resultados por búsqueda."""

    def __init__(self, items, cap=40, fail=False):
        self.items, self.cap, self.fail, self.queries = items, cap, fail, []

    def get_json(self, url, headers=None):
        if url == lidl.BASE + "/categories":
            return None
        assert url.startswith(lidl.SEARCH), url
        from urllib.parse import unquote
        query = unquote(url[len(lidl.SEARCH):])
        self.queries.append(query)
        if self.fail:
            from sync.http import FetchError
            raise FetchError("bloqueado")
        words = query.lower().split()
        hits = [i for i in self.items if all(w in i["title"].lower() for w in words)]
        hits.sort(key=lambda i: i["title"].lower() != query.lower())  # la coincidencia exacta primero
        return {"results": hits[:self.cap]}


class LidlSearchTest(unittest.TestCase):
    PREVIOUS = [
        prev("1_ES", "Leche fresca entera", "Quesos, lácteos y huevos", "Leche y nata", 3),
        prev("2_ES", "Manzana Golden", "Fruta y verdura", "Frutas", 0),
        prev("3_ES", "Queso curado oveja", "Quesos, lácteos y huevos", "Quesos", 3),
    ]

    def test_sin_categorias_reconstruye_el_catalogo_buscando(self):
        http = SearchHttp([item("1_ES", "Leche fresca entera", 1.15), item("2_ES", "Manzana Golden", 1.99),
                           item("3_ES", "Queso curado oveja", 4.5)])
        products = {p.id: p for p in lidl.fetch(http, previous=self.PREVIOUS)}
        self.assertEqual(set(products), {"1_ES", "2_ES", "3_ES"})
        leche = products["1_ES"]
        self.assertEqual((leche.price, leche.cat, leche.sub, leche.catOrder), (1.15, "Quesos, lácteos y huevos", "Leche y nata", 3))
        self.assertEqual((leche.unitPrice, leche.unitLabel, leche.size), (2.0, "kg", "500 g"))
        self.assertIn("Resize%3d(384)", leche.image)

    def test_producto_nuevo_toma_la_categoria_del_mas_parecido(self):
        http = SearchHttp([item("1_ES", "Leche fresca entera", 1.15), item("2_ES", "Manzana Golden", 1.99),
                           item("3_ES", "Queso curado oveja", 4.5), item("9_ES", "Queso curado cabra", 5.0),
                           item("8_ES", "Pitaya roja", 3.0, line="FruitsAndVegetables")])
        products = {p.id: p for p in lidl.fetch(http, previous=self.PREVIOUS, extra_terms=["pitaya"])}
        self.assertEqual((products["9_ES"].cat, products["9_ES"].sub), ("Quesos, lácteos y huevos", "Quesos"))
        self.assertEqual(products["8_ES"].cat, "Fruta y verdura")

    def test_nombre_generico_se_recupera_buscando_el_nombre_entero(self):
        previous = [prev("1_ES", "Yogur natural", "Quesos, lácteos y huevos", "Yogures", 3)]
        others = [item(f"{n}_ES", f"Yogur natural sabor {n}", 1.0) for n in range(10, 20)]
        http = SearchHttp(others + [item("1_ES", "Yogur natural", 0.5)], cap=3)
        products = {p.id for p in lidl.fetch(http, previous=previous, extra_terms=[])}
        self.assertIn("1_ES", products)
        self.assertIn("Yogur natural", http.queries)

    def test_busqueda_bloqueada_es_un_fallo(self):
        from sync.http import FetchError
        http = SearchHttp([], fail=True)
        with self.assertRaises(FetchError):
            lidl.fetch(http, previous=self.PREVIOUS)

    def test_sin_catalogo_anterior_usa_terminos_generales(self):
        http = SearchHttp([item("5_ES", "Leche semidesnatada", 1.0)])
        products = lidl.fetch(http, previous=[])
        self.assertEqual([p.id for p in products], ["5_ES"])
        self.assertIn("leche", http.queries)
