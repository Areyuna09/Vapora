import json
import sqlite3

import config
import storage


def test_channels_per_guild():
    storage.set_channel(1, "ofertas", 100)
    storage.set_channel(1, "rebajas", 200)
    storage.set_channel(2, "rebajas", 300)
    assert storage.get_guild_settings(1) == {"deals_channel": 100, "sales_channel": 200}
    assert storage.all_guild_settings() == {
        1: {"deals_channel": 100, "sales_channel": 200},
        2: {"sales_channel": 300},
    }


def test_changing_channel_replaces_it():
    storage.set_channel(1, "ofertas", 100)
    storage.set_channel(1, "ofertas", 999)
    assert storage.get_guild_settings(1) == {"deals_channel": 999}


def test_disable_channel_removes_empty_guild():
    storage.set_channel(1, "ofertas", 100)
    storage.set_channel(1, "ofertas", None)
    assert storage.get_guild_settings(1) == {}
    assert storage.all_guild_settings() == {}


def test_wishlist_channel():
    storage.set_channel(1, "deseados", 400)
    assert storage.get_guild_settings(1) == {"wishlist_channel": 400}


def test_invalid_feature_is_rejected_by_database():
    try:
        storage.set_channel(1, "ofertass", 100)  # typo
    except (KeyError, sqlite3.IntegrityError):
        pass
    else:
        raise AssertionError("debería rechazar un tipo de aviso inválido")
    assert storage.get_guild_settings(1) == {}


def test_sent_announcements_per_guild():
    assert storage.sent_announcements(1) == set()
    storage.mark_sent(1, "Rebajas de Otoño-2026-10-01", "7d")
    storage.mark_sent(1, "Rebajas de Otoño-2026-10-01", "7d")  # repetido: no falla
    storage.set_channel(1, "rebajas", 200)  # guardar canales no borra los avisos
    assert storage.sent_announcements(1) == {"Rebajas de Otoño-2026-10-01:7d"}
    assert storage.sent_announcements(2) == set()


def test_imports_legacy_json_once(temp_database):
    legacy = temp_database / "state.json"
    legacy.write_text(json.dumps({
        "guilds": {"10": {"deals_channel": 100, "sales_channel": 200, "wishlist_channel": 300}},
        "sent": ["10:Rebajas de Otoño-2026-10-01:7d"],
        "wishlist": {"5": {"367520": {"name": "Hollow Knight", "guild_id": 10, "notified_final": None},
                           "1057090": {"name": "Ori", "guild_id": 10, "notified_final": 299}}},
    }), encoding="utf-8")

    assert storage.get_guild_settings(10) == {"deals_channel": 100, "sales_channel": 200, "wishlist_channel": 300}
    assert storage.sent_announcements(10) == {"Rebajas de Otoño-2026-10-01:7d"}
    assert storage.get_wishlist(5) == {
        367520: {"name": "Hollow Knight", "guild_id": 10, "notified_final": None},
        1057090: {"name": "Ori", "guild_id": 10, "notified_final": 299},
    }
    assert not legacy.exists()
    assert (temp_database / "state.json.migrado").exists()


def test_corrupt_legacy_json_starts_empty(temp_database):
    (temp_database / "state.json").write_text("{no es json", encoding="utf-8")
    assert storage.all_guild_settings() == {}
    assert storage.sent_announcements(1) == set()


def test_schema_version_is_recorded():
    storage.all_guild_settings()
    with sqlite3.connect(config.DATABASE_FILE) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(storage.MIGRATIONS)


def test_help_shows_admin_section_only_to_admins():
    from bot import build_help_embed
    admin = [f.name for f in build_help_embed(is_admin=True).fields]
    member = [f.name for f in build_help_embed(is_admin=False).fields]
    assert "⚙️ Administración" in admin
    assert "⚙️ Administración" not in member
    assert "🎮 Comandos" in member
