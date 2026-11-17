import unittest

from sync.health.additives import Additive, AdditiveTable
from tests.util import load


def table() -> AdditiveTable:
    return AdditiveTable.from_taxonomy(load("additives_mini.json"))


def codes(additives):
    return [a.code for a in additives]


class AdditivesTest(unittest.TestCase):
    def test_risk_levels(self):
        t = table()
        self.assertEqual(t.from_tags(["en:e250"]), [Additive("E250", "Nitrito sódico", "high")])
        self.assertEqual(t.from_tags(["en:e133"])[0].risk, "moderate")
        self.assertEqual(t.from_tags(["en:e330"])[0].risk, "unrated")

    def test_from_tags(self):
        self.assertEqual(codes(table().from_tags(["en:e330", "en:e250", "en:e330"])), ["E330", "E250"])

    def test_unknown_code_is_unrated(self):
        self.assertEqual(table().from_tags(["en:e999"]), [Additive("E999", "E999", "unrated")])

    def test_find_codes_variants(self):
        text = "acidulante (E-330), colorante E 150d, e621 y lote 12345E"
        self.assertEqual(codes(table().find_in_text(text)), ["E330", "E150D", "E621"])

    def test_name_match_whole_words(self):
        t = table()
        self.assertEqual(codes(t.find_in_text("colorante: cochinilla")), ["E120"])
        self.assertEqual(codes(t.find_in_text("tricochinillas")), [])
        self.assertEqual(codes(t.find_in_text("potenciador del sabor (glutamato monosodico)")), ["E621"])

    def test_code_and_name_not_duplicated(self):
        self.assertEqual(codes(table().find_in_text("nitrito sódico (E250)")), ["E250"])

    def test_food_names_are_not_additives(self):
        t = table()
        for text in ["Azafrán en hebra", "relleno sabor caramelo", "copos de amaranto", "gelatina de vacuno"]:
            self.assertEqual(codes(t.find_in_text(text)), [], text)
        self.assertEqual(codes(t.find_in_text("colorante (E150)")), ["E150"])
