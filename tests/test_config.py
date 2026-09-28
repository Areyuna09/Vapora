import config
import storage


def test_channels_per_guild(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    storage.set_channel(1, "ofertas", 100)
    storage.set_channel(1, "rebajas", 200)
    storage.set_channel(2, "rebajas", 300)
    assert storage.get_guild_settings(1) == {"deals_channel": 100, "sales_channel": 200}
    assert storage.all_guild_settings() == {
        1: {"deals_channel": 100, "sales_channel": 200},
        2: {"sales_channel": 300},
    }


def test_disable_channel_removes_empty_guild(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    storage.set_channel(1, "ofertas", 100)
    storage.set_channel(1, "ofertas", None)
    assert storage.get_guild_settings(1) == {}
    assert storage.all_guild_settings() == {}


def test_sent_announcements_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    assert storage.sent_announcements() == set()
    storage.mark_sent("1:Rebajas de Otoño-2026-10-01:7d")
    storage.mark_sent("1:Rebajas de Otoño-2026-10-01:7d")
    storage.set_channel(1, "rebajas", 200)  # guardar canales no borra los avisos
    assert storage.sent_announcements() == {"1:Rebajas de Otoño-2026-10-01:7d"}


def test_corrupt_state_file_starts_empty(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("{no es json", encoding="utf-8")
    monkeypatch.setattr(config, "STATE_FILE", str(path))
    assert storage.all_guild_settings() == {}
    assert storage.sent_announcements() == set()
