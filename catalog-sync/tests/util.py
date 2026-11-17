import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


class FakeHttp:
    """Sirve respuestas por URL; una URL desconocida es un fallo del test."""

    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def get_json(self, url, headers=None):
        self.urls.append(url)
        self.headers = headers
        response = self.routes[url]
        if isinstance(response, Exception):
            raise response
        return response

    get_text = get_json
