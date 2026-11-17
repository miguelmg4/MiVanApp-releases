import io
import unittest
from urllib.error import URLError
from sync.http import FetchError, Http


class FakeOpener:
    """Devuelve las respuestas en orden; una excepción en la lista se lanza."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return io.BytesIO(r)


class HttpTest(unittest.TestCase):
    def test_reintenta_y_falla_con_fetcherror(self):
        opener = FakeOpener([URLError("x")] * 3)
        http = Http(delay=0, retries=3, opener=opener, sleep=lambda s: None)
        with self.assertRaises(FetchError):
            http.get_json("https://example.invalid/a")
        self.assertEqual(opener.calls, 3)

    def test_devuelve_json_al_segundo_intento(self):
        opener = FakeOpener([URLError("x"), b'{"ok": true}'])
        http = Http(delay=0, retries=3, opener=opener, sleep=lambda s: None)
        self.assertEqual(http.get_json("https://example.invalid/a"), {"ok": True})

    def test_espera_el_retardo_antes_de_cada_peticion(self):
        waits = []
        http = Http(delay=0.4, retries=1, opener=FakeOpener([b"a", b"b"]), sleep=waits.append)
        http.get_text("https://example.invalid/a")
        http.get_text("https://example.invalid/b")
        self.assertEqual(waits, [0.4, 0.4])
