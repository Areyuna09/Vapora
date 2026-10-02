"""Modelos de la tienda de Steam que usa el resto del bot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

STORE_URL = "https://store.steampowered.com"


class ItemKind(StrEnum):
    """Tipos de link de la tienda. El valor es el segmento de la URL."""

    APP = "app"  # juegos y DLC
    PACKAGE = "sub"
    BUNDLE = "bundle"


@dataclass(frozen=True, slots=True)
class ItemRef:
    """Identifica algo de la tienda: el tipo de link y su número."""

    kind: ItemKind
    id: int

    @classmethod
    def app(cls, app_id: int) -> ItemRef:
        return cls(ItemKind.APP, app_id)

    @property
    def url(self) -> str:
        return f"{STORE_URL}/{self.kind}/{self.id}/"


@dataclass(frozen=True, slots=True)
class Price:
    """Precio en centavos, como lo informa Steam."""

    final_cents: int
    initial_cents: int | None = None
    discount_percent: int = 0
    currency: str | None = None

    @property
    def on_sale(self) -> bool:
        return self.discount_percent > 0

    @property
    def is_usd(self) -> bool:
        return self.currency == "USD"


@dataclass(frozen=True, slots=True)
class Reviews:
    description: str | None
    total: int
    positive_percent: int


@dataclass(frozen=True, slots=True)
class StoreItem:
    """Un juego, DLC, paquete o bundle, con lo necesario para armar su tarjeta."""

    ref: ItemRef
    name: str
    description: str | None = None
    image_url: str | None = None
    is_free: bool = False
    price: Price | None = None
    release_date: str | None = None
    coming_soon: bool = False
    genres: tuple[str, ...] = ()
    developers: tuple[str, ...] = ()
    dlc_of: str | None = None  # nombre del juego base, si es un DLC
    included: tuple[str, ...] = ()  # nombres de lo que trae un paquete
    included_count: int = 0  # cantidad de productos de un paquete o bundle
    reviews: Reviews | None = None
    argentine: bool = False

    @property
    def is_wishable(self) -> bool:
        """Se puede seguir como deseado: juegos y DLC con precio (no gratis ni paquetes/bundles)."""
        return self.ref.kind is ItemKind.APP and self.price is not None


@dataclass(frozen=True, slots=True)
class Deal:
    """Una oferta destacada de la portada de Steam."""

    ref: ItemRef
    name: str
    price: Price
    image_url: str | None = None
    expires_at: int | None = None  # segundos desde epoch


@dataclass(frozen=True, slots=True)
class SearchResult:
    app_id: int
    name: str
