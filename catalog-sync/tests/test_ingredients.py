import unittest

from sync.health.additives import Additive
from sync.health.ingredients import clean_ingredients, estimate_nova

E471 = Additive("E471", "Mono- y diglicéridos de ácidos grasos", "unrated")


class IngredientsTest(unittest.TestCase):
    def test_clean_strips_html_and_prefix(self):
        raw = "<p>Ingredientes: Aceite de oliva refinado y aceite de oliva virgen extra</p>"
        self.assertEqual(clean_ingredients(raw), "Aceite de oliva refinado y aceite de oliva virgen extra")
        self.assertEqual(clean_ingredients("<strong>x99</strong>."), "x99.")
        self.assertEqual(clean_ingredients("Leche &amp; nata"), "Leche & nata")
        self.assertEqual(clean_ingredients(None), "")
        self.assertEqual(clean_ingredients("<p> </p>"), "")

    def test_single_raw_ingredient_is_nova1(self):
        self.assertEqual(estimate_nova("Garbanzos", []), (1, 0))

    def test_culinary_is_nova2(self):
        self.assertEqual(estimate_nova("Aceite de oliva virgen extra", []), (2, 0))

    def test_processed_is_nova3(self):
        self.assertEqual(estimate_nova("Tomate, sal, aceite de oliva", []), (3, 0))

    def test_markers_make_nova4(self):
        text = "Harina de trigo, jarabe de glucosa, aromas, emulgente (E471)"
        self.assertEqual(estimate_nova(text, [E471]), (4, 3))

    def test_commas_inside_brackets_do_not_split(self):
        self.assertEqual(estimate_nova("Garbanzos (cocidos, escurridos)", []), (1, 0))
