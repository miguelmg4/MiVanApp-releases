import unittest
from sync.stores import mercadona
from tests.util import FakeHttp, load


class MercadonaTest(unittest.TestCase):
    def test_parse_tree_devuelve_subcategorias_con_orden_del_padre(self):
        tree = mercadona.parse_tree(load("mercadona_categories.json"))
        self.assertEqual(tree, [
            (112, "Aceite, especias y salsas", 7),
            (115, "Aceite, especias y salsas", 7),
            (156, "Agua y refrescos", 8),
            (163, "Agua y refrescos", 8),
        ])

    def test_parse_category_extrae_precio_y_formato(self):
        products = mercadona.parse_category(load("mercadona_category_112.json"), "Aceite, especias y salsas", 7)
        p = products[0]
        self.assertEqual(
            (p.id, p.name, p.price, p.unitPrice, p.unitLabel, p.sub, p.cat, p.catOrder),
            ("4241", "Aceite de oliva 0,4º Hacendado", 16.75, 3.35, "l", "Aceite de oliva", "Aceite, especias y salsas", 7),
        )
        self.assertEqual(p.size, "Garrafa 5 l")
        self.assertTrue(p.image.startswith("https://prod-mercadona.imgix.net/"))
        self.assertEqual(len(products), 4)

    def test_fetch_recorre_el_arbol_del_almacen_de_cuenca(self):
        base = "https://tienda.mercadona.es/api/categories/"
        http = FakeHttp({
            base + "?lang=es&wh=4606": load("mercadona_categories.json"),
            base + "112/?lang=es&wh=4606": load("mercadona_category_112.json"),
        })
        products = mercadona.fetch(http, limit=1)
        self.assertEqual(len(http.urls), 2)
        self.assertEqual(len(products), 4)
