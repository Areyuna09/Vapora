"""Dobles de prueba y constructores de datos compartidos por los tests."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import aiohttp
from PIL import Image

from vapora.steam import ItemKind, ItemRef, Price, StoreItem

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)  # type: ignore[arg-type]

    async def json(self, **_: object) -> Any:
        return self._payload

    async def text(self) -> str:
        return str(self._payload)

    async def read(self) -> bytes:
        return self._payload if isinstance(self._payload, bytes) else str(self._payload).encode()

    @property
    def content_length(self) -> int | None:
        return len(self._payload) if isinstance(self._payload, bytes) else None


def make_gif(size: tuple[int, int] = (160, 160), frames: int = 3, duration: int = 80) -> bytes:
    """GIF animado de prueba: cada cuadro de un color distinto."""
    images = [Image.new("RGB", size, (60 * i % 256, 120, 200)) for i in range(frames)]
    out = io.BytesIO()
    images[0].save(out, format="GIF", save_all=True, append_images=images[1:], duration=duration, loop=0)
    return out.getvalue()


class FakeSession:
    """Reemplazo de `aiohttp.ClientSession`: responde según el fragmento de URL que coincida.

    Cada respuesta puede ser el contenido (JSON o texto), una excepción a lanzar, o una
    función que recibe los parámetros del pedido y devuelve el contenido.
    """

    def __init__(self, routes: dict[str, Any] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, Any]] = []

    def get(self, url: str, params: Any = None) -> FakeResponse:
        """`params` puede ser un dict o una lista de pares (para parámetros repetidos)."""
        return self._respond(url, params or {})

    def post(self, url: str, data: dict[str, str] | None = None) -> FakeResponse:
        return self._respond(url, data or {})

    def _respond(self, url: str, params: Any) -> FakeResponse:
        self.calls.append((url, params))
        for fragment, payload in self.routes.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                if callable(payload):
                    payload = payload(params)
                return FakeResponse(payload)
        return FakeResponse({}, status=404)

    def count(self, fragment: str) -> int:
        return sum(1 for url, _ in self.calls if fragment in url)


def make_item(
    app_id: int = 1,
    name: str = "Juego",
    *,
    kind: ItemKind = ItemKind.APP,
    price_cents: int | None = 999,
    discount: int = 0,
    initial_cents: int | None = None,
    **fields: Any,
) -> StoreItem:
    """Arma un `StoreItem` de prueba; por defecto, un juego de USD 9,99 sin descuento."""
    price = None
    if price_cents is not None:
        price = Price(
            price_cents, initial_cents if initial_cents is not None else price_cents, discount, "USD"
        )
    return StoreItem(ref=ItemRef(kind, app_id), name=name, price=price, **fields)
