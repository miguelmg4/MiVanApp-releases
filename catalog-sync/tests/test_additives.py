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
        self.assertEqual(t.from_tags(["en:e330"])[0].risk, "none")

    def test_sin_limite_legal_es_sin_riesgo(self):
        # Grupo I del Reglamento (CE) 1333/2008: se usan «quantum satis».
        t = table()
        self.assertEqual([a.risk for a in t.from_tags(["en:e330", "en:e471", "en:e420", "en:e14xx"])],
                         ["none"] * 4)

    def test_autorizado_con_limite_es_riesgo_limitado(self):
        t = table()
        self.assertEqual([a.risk for a in t.from_tags(["en:e120", "en:e955", "en:e407"])], ["limited"] * 3)

    def test_glutamato_no_es_grupo_i(self):
        self.assertEqual(table().from_tags(["en:e620"])[0].risk, "limited")

    def test_la_efsa_manda_sobre_el_reglamento(self):
        t = AdditiveTable.from_taxonomy({"en:e330": {"efsa_evaluation_overexposure_risk": {"en": "en:moderate"}}})
        self.assertEqual(t.from_tags(["en:e330"])[0].risk, "moderate")

    def test_variante_hereda_del_aditivo_principal(self):
        t = AdditiveTable.from_taxonomy({
            "en:e250": {"efsa_evaluation_overexposure_risk": {"en": "en:high"}},
            "en:e450iii": {"name": {"es": "E450iii - Difosfato tetrasódico"}, "parents": ["en:e450"]},
            "en:e450": {"efsa_evaluation_overexposure_risk": {"en": "en:moderate"}},
        })
        self.assertEqual([a.risk for a in t.from_tags(["en:e450iii", "en:e250ii", "en:e322i", "en:e160ai"])],
                         ["moderate", "high", "none", "limited"])

    def test_subtipo_con_letra_de_un_autorizado(self):
        self.assertEqual(table().from_tags(["en:e960a"])[0].risk, "limited")

    def test_dioxido_de_titanio_prohibido(self):
        self.assertEqual(table().from_tags(["en:e171"])[0].risk, "high")

    def test_from_tags(self):
        self.assertEqual(codes(table().from_tags(["en:e330", "en:e250", "en:e330"])), ["E330", "E250"])

    def test_unknown_code_is_unrated(self):
        self.assertEqual(table().from_tags(["en:e1999"]), [Additive("E1999", "E1999", "unrated")])

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
