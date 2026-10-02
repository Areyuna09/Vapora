"""Fixtures compartidas."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import FakeSession

from vapora.pricing import ExchangeRates, PesoConverter, Taxes
from vapora.storage import Database


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Base de datos temporal y vacía para cada test."""
    return Database(tmp_path / "vapora.db", tmp_path / "state.json")


@pytest.fixture
def converter() -> PesoConverter:
    return PesoConverter(ExchangeRates(official=1550.0, crypto=1623.44), Taxes())
