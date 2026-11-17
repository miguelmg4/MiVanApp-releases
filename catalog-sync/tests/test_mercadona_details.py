import tempfile
import unittest
from pathlib import Path

from sync.health.cache import read_gz_json, write_gz_json
from sync.http import FetchError
from sync.stores import mercadona
from tests.util import FakeHttp, load


def url(product_id: str) -> str:
    return mercadona.PRODUCT.format(id=product_id)


class MercadonaDetailsTest(unittest.TestCase):
    def test_parse_detail(self):
        detail = mercadona.parse_detail(load("mercadona_product_4241.json"))
        self.assertEqual(detail["ean"], "8402001027482")
        self.assertTrue(detail["ingredients"].startswith("<p>Ingredientes:"))
        self.assertIsNone(mercadona.parse_detail(None))

    def test_fetch_uses_cache_on_failure(self):
        http = FakeHttp({url("1"): {"ean": "111", "nutrition_information": {"ingredients": "Garbanzos"}},
                         url("2"): FetchError("caído")})
        cache = {"2": {"ean": "222", "ingredients": "Lentejas"}, "9": {"ean": "999", "ingredients": "x"}}
        details, failures = mercadona.fetch_details(http, ["1", "2"], cache)
        self.assertEqual(details, {"1": {"ean": "111", "ingredients": "Garbanzos"},
                                   "2": {"ean": "222", "ingredients": "Lentejas"}})
        self.assertEqual(failures, 1)

    def test_fetch_without_cache_skips_failed(self):
        http = FakeHttp({url("3"): None})
        details, failures = mercadona.fetch_details(http, ["3"], {})
        self.assertEqual((details, failures), ({}, 1))

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "details" / "x.json.gz"
            self.assertIsNone(read_gz_json(path))
            write_gz_json(path, {"a": "ñ"})
            self.assertEqual(read_gz_json(path), {"a": "ñ"})
