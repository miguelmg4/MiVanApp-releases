import unittest

from sync.health.additives import Additive, AdditiveTable
from sync.health.score import (
    OffRow, additive_points, compute, nutrition_points, processing_points,
)
from tests.util import load

TABLE = AdditiveTable.from_taxonomy(load("additives_mini.json"))
MODERATE = Additive("E133", "Azul brillante FCF", "moderate")


def off(grade=None, score=None, nova=None, additives=(), labels=()):
    return OffRow("8480000000000", grade, score, nova, list(additives), list(labels))


class PointsTest(unittest.TestCase):
    def test_nutrition_band_midpoint(self):
        self.assertEqual(nutrition_points("b", None), 70)

    def test_nutrition_band_edges(self):
        self.assertEqual(nutrition_points("a", -17), 100)
        self.assertEqual(nutrition_points("a", 0), 80)
        self.assertEqual(nutrition_points("e", 55), 0)

    def test_additive_points(self):
        self.assertEqual(additive_points([]), 100)
        self.assertEqual(additive_points([MODERATE]), 70)
        self.assertEqual(additive_points([MODERATE] * 4), 0)
        self.assertEqual(additive_points([Additive("E250", "Nitrito sódico", "high")]), 0)
        self.assertEqual(additive_points([Additive("E330", "Ácido cítrico", "unrated")]), 100)

    def test_processing_points(self):
        self.assertEqual([processing_points(n, m) for n, m in [(1, 0), (2, 0), (3, 0), (4, 1), (4, 3), (4, 9)]],
                         [100, 75, 50, 25, 15, 0])


class ComputeTest(unittest.TestCase):
    def test_full_score(self):
        s = compute("Espárrago verde", "Conservas, caldos y cremas", "Conservas verdura", "", off("a"), TABLE)
        self.assertEqual((s["value"], s["kind"], s["nutriscore"]), (84, "full", "a"))

    def test_high_risk_caps_at_49(self):
        s = compute("Chorizo", "Charcutería y quesos", "Chorizo", "", off("a", -17, additives=["en:e250"]), TABLE)
        self.assertEqual(s["value"], 49)
        self.assertEqual(s["additives"], [{"code": "E250", "name": "Nitrito sódico", "risk": "high"}])

    def test_ingredients_score(self):
        s = compute("Tomate frito", "Aceite, especias y salsas", "Tomate frito",
                    "Tomate, sal, aceite de oliva", None, TABLE)
        self.assertEqual((s["value"], s["kind"], s["nova"], s["novaEstimated"]), (60, "ingredients", 3, True))

    def test_off_nova_used_when_present(self):
        s = compute("Tomate frito", "Aceite, especias y salsas", "Tomate frito",
                    "Tomate, sal, aceite de oliva", off(nova=4), TABLE)
        self.assertEqual((s["nova"], s["novaEstimated"], s["value"]), (4, False, 45))

    def test_organic_bonus(self):
        s = compute("Tomate triturado ecológico", "Conservas, caldos y cremas", "Tomate",
                    "Tomate, sal, aceite de oliva", None, TABLE)
        self.assertEqual((s["value"], s["organic"]), (70, True))

    def test_fruta_con_tratamiento_de_superficie_sigue_siendo_fresca(self):
        # Mercadona pone en «ingredientes» el tratamiento de la piel de los cítricos: la fruta no es un ultraprocesado.
        s = compute("Mandarina", "Fruta y verdura", "Cítricos",
                    "Tratado con agentes de recubrimiento (E330) Imazalil.", None, TABLE)
        self.assertEqual((s["nova"], s["value"], s["kind"]), (1, 90, "ingredients"))
        s = compute("Mandarina", "Fruta y verdura", "Cítricos",
                    "Tratado con agentes de recubrimiento (E330, E-250) Imazalil y fludioxonil.", None, TABLE)
        self.assertEqual((s["nova"], s["value"]), (1, 49))  # el aditivo de riesgo alto sigue contando
        self.assertEqual([a["code"] for a in s["additives"]], ["E330", "E250"])

    def test_fresh_without_ingredients(self):
        s = compute("Manzana Golden", "Fruta y verdura", "Manzana y pera", "", None, TABLE)
        self.assertEqual((s["value"], s["nova"], s["kind"]), (90, 1, "ingredients"))

    def test_non_food_and_alcohol(self):
        self.assertIsNone(compute("Lejía", "Limpieza y hogar", "Lejía", "Agua", None, TABLE))
        self.assertIsNone(compute("Cerveza clásica", "Bodega", "Cerveza lata", "Agua, malta", None, TABLE))
        self.assertIsNone(compute("Pañal", "Bebé", "Pañal talla de 0 a 3", "x", None, TABLE))
        self.assertIsNotNone(compute("Cerveza sin alcohol", "Bodega", "Cerveza lata", "Agua, malta", None, TABLE))

    def test_no_data_returns_none(self):
        self.assertIsNone(compute("Salsa", "Aceite, especias y salsas", "Otras salsas", "", None, TABLE))
