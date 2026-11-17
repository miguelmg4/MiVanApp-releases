import unittest
from sync.model import Product, clean


class CleanTest(unittest.TestCase):
    def test_clean_descarta_sin_precio_y_duplicados(self):
        a = Product(id="1", name="Leche", price=1.0)
        out = clean([
            a,
            Product(id="1", name="Leche bis", price=2.0),
            Product(id="2", name="Gratis", price=0),
            Product(id="3", name=" ", price=1),
        ])
        self.assertEqual(out, [a])

    def test_to_dict_incluye_todos_los_campos_del_formato(self):
        d = Product(id="1", name="Leche", price=1.0).to_dict()
        self.assertEqual(
            sorted(d),
            ["brand", "cat", "catOrder", "id", "image", "name", "price", "size", "sub", "unitLabel", "unitPrice"],
        )
        self.assertIsNone(d["brand"])
