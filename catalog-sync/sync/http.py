"""Cliente HTTP mínimo: pausa entre peticiones y reintentos."""
import json
import time
import urllib.request
from typing import Any, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class FetchError(Exception):
    """La petición falló después de agotar los reintentos."""


class Http:
    def __init__(self, delay: float = 0.4, retries: int = 3, opener=None, sleep=time.sleep):
        self.delay = delay
        self.retries = retries
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep

    def get_text(self, url: str, headers: Optional[dict] = None) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        last: Optional[Exception] = None
        for attempt in range(self.retries):
            self.sleep(self.delay * (attempt + 1))
            try:
                with self.opener.open(request, timeout=30) as response:
                    return response.read().decode("utf-8", errors="replace")
            except OSError as error:  # URLError, HTTPError y timeouts heredan de OSError
                last = error
        raise FetchError(f"{url}: {last}")

    def get_json(self, url: str, headers: Optional[dict] = None) -> Any:
        """Devuelve None si la respuesta viene vacía (p. ej. un 204)."""
        text = self.get_text(url, {"Accept": "application/json", **(headers or {})})
        if not text.strip():
            return None
        try:
            return json.loads(text)
        except ValueError as error:
            raise FetchError(f"{url}: respuesta no es JSON ({error})")
