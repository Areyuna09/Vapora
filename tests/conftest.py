import pytest

import config


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    """Cada test usa su propia base de datos temporal (nunca data/ de verdad)."""
    monkeypatch.setattr(config, "DATABASE_FILE", str(tmp_path / "vapora.db"))
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    return tmp_path
