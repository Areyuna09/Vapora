"""Detección de links de la tienda de Steam dentro de un texto."""

from __future__ import annotations

import re

from vapora.steam.models import ItemKind, ItemRef

# Juegos y DLC (/app/), paquetes (/sub/) y bundles (/bundle/).
STORE_LINK_RE = re.compile(
    r"https?://(?:store\.)?steampowered\.com/(app|sub|bundle)/(\d+)(?:/[^\s<>]*)?",
    re.IGNORECASE,
)


def extract_item_refs(text: str) -> list[ItemRef]:
    """Devuelve lo que enlaza el texto, sin repetir y en el orden en que aparece."""
    refs = (ItemRef(ItemKind(kind.lower()), int(item_id)) for kind, item_id in STORE_LINK_RE.findall(text))
    return list(dict.fromkeys(refs))
