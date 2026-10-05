"""Vistas previas animadas más grandes para los fondos de Wallpaper Engine.

Las vistas previas animadas del Workshop son GIF chicos (de 160 a 256 px), y Discord no
muestra una imagen más grande que su tamaño real. Acá se agrandan para que se vean bien
en la tarjeta, sin perder la animación. Los JPEG ya vienen grandes (~1024 px) y no se tocan.
"""

from __future__ import annotations

import asyncio
import io
import logging

import aiohttp
from PIL import Image, ImageSequence, UnidentifiedImageError

from vapora.cache import TTLCache

log = logging.getLogger(__name__)

TARGET_SIDE = 480  # lado más largo del GIF agrandado, en píxeles
MIN_SCALE = 1.5  # si no se agranda al menos esto, no vale la pena: queda el original
MAX_INPUT_BYTES = 6 * 1024 * 1024
MAX_FRAMES = 300
MAX_OUTPUT_BYTES = 8 * 1024 * 1024  # Discord acepta adjuntos de hasta 10 MB
CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_ENTRIES = 30  # cada uno pesa unos pocos MB
DEFAULT_FRAME_MS = 100


def enlarge_gif(data: bytes) -> bytes | None:
    """El GIF agrandado y todavía animado, o `None` si no es un GIF o no conviene agrandarlo.

    No conviene si ya es grande, si tiene demasiados cuadros, o si el resultado pesaría
    más de lo que Discord acepta.
    """
    if not data.startswith(b"GIF") or len(data) > MAX_INPUT_BYTES:
        return None
    try:
        with Image.open(io.BytesIO(data)) as gif:
            scale = TARGET_SIDE / max(gif.size)
            if scale < MIN_SCALE or getattr(gif, "n_frames", 1) > MAX_FRAMES:
                return None
            size = (round(gif.width * scale), round(gif.height * scale))
            frames, durations = [], []
            for frame in ImageSequence.Iterator(gif):
                frames.append(frame.convert("RGBA").resize(size, Image.Resampling.LANCZOS))
                durations.append(
                    int(frame.info.get("duration") or gif.info.get("duration") or DEFAULT_FRAME_MS)
                )
            out = io.BytesIO()
            frames[0].save(
                out,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=gif.info.get("loop", 0),
                disposal=2,  # cada cuadro reemplaza al anterior, como en el original
            )
    except (UnidentifiedImageError, OSError, ValueError):
        log.warning("No pude agrandar una vista previa", exc_info=True)
        return None
    enlarged = out.getvalue()
    return enlarged if len(enlarged) <= MAX_OUTPUT_BYTES else None


class PreviewEnlarger:
    """Descarga y agranda vistas previas, con caché por URL."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._cache: TTLCache[str, bytes | None] = TTLCache(CACHE_TTL_SECONDS, max_entries=CACHE_ENTRIES)

    async def enlarged(self, preview_url: str | None) -> bytes | None:
        """La vista previa agrandada, o `None` si no hace falta o no se pudo.

        Nunca lanza: si algo falla, la tarjeta usa la vista previa original.
        """
        if not preview_url:
            return None
        return await self._cache.get_or_fetch(preview_url, lambda: self._enlarge(preview_url))

    async def _enlarge(self, preview_url: str) -> bytes | None:
        try:
            async with self._session.get(preview_url) as response:
                response.raise_for_status()
                if (response.content_length or 0) > MAX_INPUT_BYTES:
                    return None
                data = await response.read()
        except (aiohttp.ClientError, TimeoutError):
            log.warning("No pude descargar la vista previa %s", preview_url, exc_info=True)
            return None
        # Procesar las imágenes usa CPU: en un hilo aparte, para no frenar al bot.
        return await asyncio.to_thread(enlarge_gif, data)
