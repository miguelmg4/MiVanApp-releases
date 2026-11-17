import gzip
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sync.model import Product
from sync.publish import publish_store, read_index, write_index

NOW = datetime(2026, 11, 16, 21, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)


def items(n):
    return [Product(id=str(i), name=f"Producto {i}", price=1.0 + i) for i in range(n)]


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, products, now=NOW):
        entry = publish_store(self.out, "mercadona", "Mercadona", products, now)
        write_index(self.out, {"mercadona": entry} if entry else {})
        return entry

    def test_primera_publicacion_escribe_fichero_e_indice(self):
        entry = self.publish(items(3))
        raw = (self.out / "mercadona.json.gz").read_bytes()
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
        self.assertEqual((data["schema"], data["store"], data["syncedAt"]), (1, "mercadona", "2026-11-16T21:00:00Z"))
        self.assertEqual(len(data["products"]), 3)
        self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
        index = read_index(self.out)
        self.assertEqual(index["schema"], 1)
        self.assertEqual(index["stores"]["mercadona"], {
            "name": "Mercadona", "file": "mercadona.json.gz", "count": 3,
            "syncedAt": "2026-11-16T21:00:00Z", "sha256": entry["sha256"], "stale": False,
        })

    def test_fallo_conserva_fichero_anterior_y_marca_stale(self):
        first = self.publish(items(10))
        before = (self.out / "mercadona.json.gz").read_bytes()
        entry = self.publish(None, LATER)
        self.assertEqual((self.out / "mercadona.json.gz").read_bytes(), before)
        self.assertEqual(entry, {**first, "stale": True})

    def test_caida_brusca_de_productos_se_trata_como_fallo(self):
        self.publish(items(100))
        entry = self.publish(items(40), LATER)
        self.assertTrue(entry["stale"])
        self.assertEqual((entry["count"], entry["syncedAt"]), (100, "2026-11-16T21:00:00Z"))

    def test_bajada_moderada_se_publica(self):
        self.publish(items(100))
        entry = self.publish(items(60), LATER)
        self.assertEqual((entry["count"], entry["stale"]), (60, False))

    def test_fallo_sin_anterior_no_crea_entrada(self):
        self.assertIsNone(self.publish(None))
        self.assertFalse((self.out / "mercadona.json.gz").exists())
        self.assertEqual(read_index(self.out)["stores"], {})

    def test_cadena_recuperada_deja_de_estar_stale(self):
        self.publish(items(10))
        self.publish(None, LATER)
        entry = self.publish(items(10), LATER)
        self.assertEqual((entry["stale"], entry["syncedAt"]), (False, "2026-11-23T21:00:00Z"))

    def test_lista_vacia_es_un_fallo(self):
        self.assertIsNone(self.publish([]))


class AttributionTest(unittest.TestCase):
    def test_index_has_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_index(Path(tmp), {})
            index = read_index(Path(tmp))
        self.assertEqual(index["attribution"], "Datos nutricionales: Open Food Facts (ODbL)")
