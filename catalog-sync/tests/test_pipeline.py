import tempfile
import unittest
from pathlib import Path

from sync.health import pipeline
from sync.health.cache import read_gz_json, write_gz_json
from sync.health.score import OffRow
from sync.model import Product
from sync.stores import mercadona
from tests.util import FakeHttp, load

FOOD = Product(id="1", name="Tomate frito Hacendado", price=1.0, cat="Aceite, especias y salsas", sub="Tomate frito")
CLEANING = Product(id="2", name="Lejía", price=1.0, cat="Limpieza y hogar", sub="Lejía")


def http():
    return FakeHttp({
        mercadona.PRODUCT.format(id="1"): {"ean": "0841", "nutrition_information":
                                           {"ingredients": "<p>Ingredientes: Tomate, sal, aceite de oliva</p>"}},
        mercadona.PRODUCT.format(id="2"): {"ean": "0842", "nutrition_information": {"ingredients": ""}},
    })


def taxonomy():
    return load("additives_mini.json")


def no_network(*args, **kwargs):
    raise OSError("sin red")


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def enrich(self, fetch_off, fetch_taxonomy=taxonomy):
        return pipeline.enrich_mercadona([FOOD, CLEANING], http(), self.out,
                                         fetch_off=fetch_off, fetch_taxonomy=fetch_taxonomy)

    def test_enrich_adds_scores(self):
        products, status = self.enrich(lambda codes: {"841": OffRow("841", "a", None, 3, [], [])})
        self.assertEqual(status, "ok")
        self.assertEqual((products[0].score["kind"], products[0].score["value"]), ("full", 84))
        self.assertIsNone(products[1].score)

    def test_off_receives_normalized_codes(self):
        seen = {}
        self.enrich(lambda codes: seen.setdefault("codes", codes) and {})
        self.assertEqual(seen["codes"], {"841", "842"})

    def test_off_unavailable_uses_ingredients_only(self):
        products, status = self.enrich(no_network)
        self.assertEqual((products[0].score["kind"], status), ("ingredients", "ok"))

    def test_uses_previous_off_cache(self):
        write_gz_json(self.out / "details" / "off.json.gz", {"841": {"g": "a", "s": None, "n": 3, "a": [], "l": []}})
        products, _ = self.enrich(no_network)
        self.assertEqual(products[0].score["kind"], "full")

    def test_uses_previous_taxonomy_cache(self):
        write_gz_json(self.out / "details" / "additives.json.gz", taxonomy())
        products, status = self.enrich(no_network, fetch_taxonomy=no_network)
        self.assertEqual((products[0].score["kind"], status), ("ingredients", "ok"))

    def test_taxonomy_missing_everywhere(self):
        products, status = self.enrich(no_network, fetch_taxonomy=no_network)
        self.assertEqual(status, "missing")
        self.assertTrue(all(p.score is None for p in products))

    def test_writes_caches_and_licence(self):
        self.enrich(lambda codes: {"841": OffRow("841", "b", 1, 3, [], [])})
        details = read_gz_json(self.out / "details" / "mercadona.json.gz")
        self.assertEqual(set(details), {"1", "2"})
        self.assertEqual(read_gz_json(self.out / "details" / "off.json.gz")["841"]["g"], "b")
        self.assertIsNotNone(read_gz_json(self.out / "details" / "additives.json.gz"))
        self.assertIn("ODbL", (self.out / "LICENCIA-DATOS.md").read_text(encoding="utf-8"))

    def test_unexpected_error_publishes_without_scores(self):
        def explode(codes):
            raise RuntimeError("bug")
        products, status = pipeline.enrich_mercadona([FOOD], None, self.out, fetch_off=explode)
        self.assertEqual((products[0].score, status), (None, "missing"))
