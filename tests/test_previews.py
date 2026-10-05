import io

import aiohttp
import pytest
from helpers import FakeSession, make_gif
from PIL import Image, ImageSequence

from vapora import previews as previews_module
from vapora.previews import TARGET_SIDE, PreviewEnlarger, enlarge_gif


def _frames(data: bytes) -> tuple[tuple[int, int], int, list[int], int]:
    """Tamaño, cantidad de cuadros, duración de cada uno y repeticiones de un GIF."""
    with Image.open(io.BytesIO(data)) as gif:
        durations = [frame.info.get("duration", 0) for frame in ImageSequence.Iterator(gif)]
        return gif.size, len(durations), durations, gif.info.get("loop", -1)


# ── enlarge_gif ───────────────────────────────────────────────────────────────


def test_enlarged_gif_keeps_the_animation():
    original = make_gif((160, 160), frames=5, duration=80)
    enlarged = enlarge_gif(original)
    assert enlarged is not None
    size, count, durations, loop = _frames(enlarged)
    assert size == (TARGET_SIDE, TARGET_SIDE)
    assert count == 5  # todos los cuadros
    assert durations == [80] * 5  # con su velocidad original
    assert loop == 0  # se repite para siempre


def test_enlarged_gif_keeps_its_proportions():
    enlarged = enlarge_gif(make_gif((240, 120)))
    assert enlarged is not None
    assert _frames(enlarged)[0] == (480, 240)


def test_big_gifs_are_left_as_they_are():
    assert enlarge_gif(make_gif((400, 400))) is None  # ya se ve grande: no vale la pena


def test_only_gifs_are_enlarged():
    jpeg = io.BytesIO()
    Image.new("RGB", (160, 160)).save(jpeg, format="JPEG")
    assert enlarge_gif(jpeg.getvalue()) is None


def test_broken_gif_is_not_enlarged():
    assert enlarge_gif(b"GIF89a esto no es una imagen") is None


def test_gifs_with_too_many_frames_are_skipped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(previews_module, "MAX_FRAMES", 2)
    assert enlarge_gif(make_gif(frames=3)) is None


def test_results_too_big_for_discord_are_dropped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(previews_module, "MAX_OUTPUT_BYTES", 100)
    assert enlarge_gif(make_gif()) is None


# ── PreviewEnlarger ───────────────────────────────────────────────────────────

URL = "https://images.steamusercontent.com/ugc/1/preview/"


async def test_downloads_enlarges_and_caches():
    session = FakeSession({"steamusercontent": make_gif()})
    enlarger = PreviewEnlarger(session)  # type: ignore[arg-type]
    first = await enlarger.enlarged(URL)
    assert first is not None and _frames(first)[0] == (TARGET_SIDE, TARGET_SIDE)
    assert await enlarger.enlarged(URL) == first
    assert session.count("steamusercontent") == 1


async def test_no_preview_or_failed_download_gives_none():
    enlarger = PreviewEnlarger(FakeSession({"steamusercontent": aiohttp.ClientError()}))  # type: ignore[arg-type]
    assert await enlarger.enlarged(None) is None
    assert await enlarger.enlarged(URL) is None


async def test_huge_downloads_are_skipped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(previews_module, "MAX_INPUT_BYTES", 10)
    enlarger = PreviewEnlarger(FakeSession({"steamusercontent": make_gif()}))  # type: ignore[arg-type]
    assert await enlarger.enlarged(URL) is None
