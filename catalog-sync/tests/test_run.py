import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import run
from sync.http import FetchError
from sync.model import Product
from sync.publish import read_index

NOW = datetime(2026, 11, 16, 21, 0, tzinfo=timezone.utc)


def ok(http, limit=None):
    return [Product(id="1", name="Leche", price=1.0)]


def broken(http, limit=None):
    raise FetchError("sin red")


def crash(http, limit=None):
    raise KeyError("la web cambió de formato")


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_una_cadena_rota_no_impide_publicar_las_demas(self):
        code = run.sync(self.out, {"a": ("A", broken), "b": ("B", ok), "c": ("C", crash)}, http=None, now=NOW)
        self.assertEqual(code, 0)
        self.assertEqual(list(read_index(self.out)["stores"]), ["b"])

    def test_todas_rotas_devuelve_error(self):
        self.assertEqual(run.sync(self.out, {"a": ("A", broken)}, http=None, now=NOW), 1)

    def test_sincronizar_una_sola_cadena_conserva_las_otras_en_el_indice(self):
        run.sync(self.out, {"a": ("A", ok), "b": ("B", ok)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", ok)}, http=None, now=NOW)
        self.assertEqual(sorted(read_index(self.out)["stores"]), ["a", "b"])

    def test_el_informe_dice_que_cadenas_fallaron(self):
        report = self.out / "informe.json"
        run.sync(self.out, {"a": ("A", ok), "b": ("B", ok)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", broken), "b": ("B", ok), "c": ("C", crash)}, http=None, now=NOW, report_path=report)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")), {"a": "stale", "b": "ok", "c": "missing"})

    def test_check_report_falla_si_alguna_cadena_no_esta_al_dia(self):
        report = self.out / "informe.json"
        report.write_text(json.dumps({"a": "ok", "b": "stale"}), encoding="utf-8")
        self.assertEqual(run.check_report(report), (1, ["b"]))
        report.write_text(json.dumps({"a": "ok", "b": "ok"}), encoding="utf-8")
        self.assertEqual(run.check_report(report), (0, []))

    def test_una_caida_que_sigue_se_marca_como_ya_avisada(self):
        report = self.out / "informe.json"
        run.sync(self.out, {"a": ("A", ok)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", broken)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", broken)}, http=None, now=NOW, report_path=report)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")), {"a": "stale-known"})

    def test_check_report_solo_avisa_de_caidas_nuevas(self):
        # una caída que ya se avisó no vuelve a mandar correo cada semana mientras dure
        report = self.out / "informe.json"
        report.write_text(json.dumps({"a": "ok", "b": "stale-known"}), encoding="utf-8")
        self.assertEqual(run.check_report(report), (0, []))

    def test_tras_recuperarse_una_nueva_caida_vuelve_a_avisar(self):
        report = self.out / "informe.json"
        run.sync(self.out, {"a": ("A", ok)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", broken)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", ok)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", broken)}, http=None, now=NOW, report_path=report)
        self.assertEqual(run.check_report(report), (1, ["a"]))

    def test_stale_stores_lista_las_que_no_estan_al_dia(self):
        run.sync(self.out, {"a": ("A", ok), "b": ("B", ok)}, http=None, now=NOW)
        run.sync(self.out, {"a": ("A", broken), "b": ("B", ok)}, http=None, now=NOW)
        self.assertEqual(run.stale_stores(self.out, ["a", "b", "c"]), ["a", "c"])

    def test_solo_desactualizadas_sin_ninguna_no_descarga(self):
        run.sync(self.out, {"mercadona": ("M", ok), "ahorramas": ("A", ok), "lidl": ("L", ok)}, http=None, now=NOW)
        self.assertEqual(run.main(["--out", str(self.out), "--stale-only"]), 0)

    def test_reintento_fallido_no_acaba_en_error(self):
        # un error haría que GitHub mandase un correo cada día; el aviso ya lo da la ejecución del lunes
        from unittest import mock
        run.sync(self.out, {"lidl": ("L", broken)}, http=None, now=NOW)
        with mock.patch.dict(run.STORES, {"lidl": ("Lidl", broken)}):
            self.assertEqual(run.main(["--out", str(self.out), "--stores", "lidl", "--stale-only"]), 0)

    def test_cadenas_registradas(self):
        self.assertEqual(sorted(run.STORES), ["ahorramas", "lidl", "mercadona"])


class NotasTest(unittest.TestCase):
    def test_report_includes_notas(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, report = Path(tmp) / "out", Path(tmp) / "informe.json"
            calls = []

            def enrich(products, http, out_dir):
                calls.append(len(products))
                return products, "missing"

            run.sync(out, {"mercadona": ("Mercadona", ok), "b": ("B", ok)}, http=None, now=NOW,
                     report_path=report, enrich={"mercadona": enrich})
            self.assertEqual(json.loads(report.read_text())["notas"], "missing")
            self.assertEqual(calls, [1])
            self.assertEqual(run.check_report(report), (1, ["notas"]))
