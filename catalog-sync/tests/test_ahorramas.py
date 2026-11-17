import unittest
from sync.stores import ahorramas
from tests.util import FakeHttp, load


class AhorramasTest(unittest.TestCase):
    def test_parse_categories_lee_el_menu_y_omite_ofertas(self):
        self.assertEqual(
            ahorramas.parse_categories(load("ahorramas_home.html")),
            [("frescos", "Frescos", 0), ("alimentacion", "Alimentación", 1)],
        )

    def test_parse_grid_extrae_los_datos_de_cada_ficha(self):
        products = ahorramas.parse_grid(load("ahorramas_grid.html"), "Lácteos", 3)
        self.assertEqual([p.id for p in products], ["70865", "70864"])
        p = products[0]
        self.assertEqual(
            (p.name, p.price, p.brand, p.unitPrice, p.unitLabel, p.cat, p.sub, p.catOrder),
            ("Leche semidesnatada Alipende 1L", 0.83, "Alipende", 0.83, "l", "Lácteos", "Leche", 3),
        )
        self.assertTrue(p.image.startswith("https://www.ahorramas.com/dw/image/"))
        self.assertNotIn("&amp;", p.image)

    def test_fetch_pagina_hasta_una_pagina_incompleta(self):
        # El botón «Más resultados» de la web apunta siempre a start=48, así que no sirve para
        # paginar: se avanza de página en página hasta que llega una con menos fichas que el tamaño.
        tile = '<div class="product" data-pid="{0}"><div data-gtm-layer="%7B%22name%22%3A%22P{0}%22%2C%22price%22%3A%221.00%22%7D"></div></div>'
        full = "".join(tile.format(i) for i in range(ahorramas.PAGE)) + '<div class="show-more"><button data-url="x?start=48&amp;sz=20"></button></div>'
        full2 = full.replace('data-pid="', 'data-pid="b')
        short = tile.format("z1") + tile.format("z2")
        http = FakeHttp({
            ahorramas.HOME: load("ahorramas_home.html"),
            ahorramas.grid_url("frescos", 0): full,
            ahorramas.grid_url("frescos", ahorramas.PAGE): full2,
            ahorramas.grid_url("frescos", ahorramas.PAGE * 2): short,
        })
        products = ahorramas.fetch(http, limit=1)
        self.assertEqual(len(http.urls), 4)
        self.assertEqual(len(products), ahorramas.PAGE * 2 + 2)

    def test_number_admite_miles_y_decimales_en_cualquier_formato(self):
        self.assertEqual(ahorramas.number("0,83"), 0.83)
        self.assertEqual(ahorramas.number("0.83"), 0.83)
        self.assertEqual(ahorramas.number("1.670,00"), 1670.0)
        self.assertEqual(ahorramas.number("1.670.00"), 1670.0)
        self.assertEqual(ahorramas.number("1,670.00"), 1670.0)
        self.assertIsNone(ahorramas.number("gratis"))
        self.assertIsNone(ahorramas.number(None))

    def test_una_ficha_con_precio_ilegible_no_rompe_la_rejilla(self):
        tile = '<div class="product" data-pid="{}"><div data-gtm-layer="%7B%22name%22%3A%22P%22%2C%22price%22%3A%22{}%22%7D"></div></div>'
        products = ahorramas.parse_grid(tile.format("1", "1.670.00") + tile.format("2", "x") + tile.format("3", "2.50"), "C", 0)
        self.assertEqual([(p.id, p.price) for p in products], [("1", 1670.0), ("2", 0), ("3", 2.5)])

    def test_la_imagen_es_la_foto_de_la_ficha_y_no_un_icono_anterior(self):
        tile = ('<div class="product" data-pid="1"><img class="weight-icon" src="/on/demandware.static/images/weight.svg" />'
                '<div data-gtm-layer="%7B%22name%22%3A%22P%22%2C%22price%22%3A%221.00%22%7D"></div>'
                '<img class="tile-image"\n src="https://www.ahorramas.com/dw/image/foto.jpg?sw=260&amp;sh=260" alt="P" /></div>')
        self.assertEqual(ahorramas.parse_grid(tile, "C", 0)[0].image, "https://www.ahorramas.com/dw/image/foto.jpg?sw=260&sh=260")

    def test_sin_foto_absoluta_la_imagen_queda_vacia(self):
        tile = ('<div class="product" data-pid="1"><img src="/icono.svg" />'
                '<div data-gtm-layer="%7B%22name%22%3A%22P%22%2C%22price%22%3A%221.00%22%7D"></div></div>')
        self.assertIsNone(ahorramas.parse_grid(tile, "C", 0)[0].image)

    def test_fetch_se_detiene_si_una_pagina_no_trae_fichas(self):
        http = FakeHttp({ahorramas.HOME: load("ahorramas_home.html"), ahorramas.grid_url("frescos", 0): "<div></div>"})
        self.assertEqual(ahorramas.fetch(http, limit=1), [])
