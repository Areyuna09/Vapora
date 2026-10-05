import asyncio
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from vapora import storage as storage_module
from vapora.storage import MAX_WISHLIST_SIZE, MIGRATIONS, AddWishResult, Database, Feature, Wish

# ── Canales de /config ────────────────────────────────────────────────────────


async def test_channels_per_guild(db: Database):
    await db.set_channel(1, Feature.DEALS, 100)
    await db.set_channel(1, Feature.SALES, 200)
    await db.set_channel(2, Feature.SALES, 300)
    assert await db.channels(1) == {Feature.DEALS: 100, Feature.SALES: 200}
    assert await db.channels(2) == {Feature.SALES: 300}
    assert await db.channels(3) == {}


async def test_channels_for_a_feature_across_guilds(db: Database):
    await db.set_channel(1, Feature.SALES, 200)
    await db.set_channel(2, Feature.SALES, 300)
    await db.set_channel(2, Feature.DEALS, 999)
    assert await db.channels_for(Feature.SALES) == {1: 200, 2: 300}
    assert await db.channels_for(Feature.WISHLIST) == {}


async def test_setting_a_channel_again_replaces_it(db: Database):
    await db.set_channel(1, Feature.DEALS, 100)
    await db.set_channel(1, Feature.DEALS, 999)
    assert await db.channels(1) == {Feature.DEALS: 999}


async def test_disabling_a_channel(db: Database):
    await db.set_channel(1, Feature.DEALS, 100)
    await db.set_channel(1, Feature.DEALS, None)
    assert await db.channels(1) == {}


async def test_database_rejects_unknown_feature(db: Database):
    with pytest.raises(sqlite3.IntegrityError):
        await db.set_channel(1, "ofertass", 100)  # type: ignore[arg-type]
    assert await db.channels(1) == {}


# ── Avisos de rebajas ─────────────────────────────────────────────────────────


async def test_sent_notices_per_guild(db: Database):
    assert await db.sent_notices(1) == set()
    await db.mark_notice_sent(1, "Rebajas de Otoño-2026-10-01", "7d")
    await db.mark_notice_sent(1, "Rebajas de Otoño-2026-10-01", "7d")  # repetido: no falla
    assert await db.sent_notices(1) == {("Rebajas de Otoño-2026-10-01", "7d")}
    assert await db.sent_notices(2) == set()


# ── Deseados ──────────────────────────────────────────────────────────────────


async def test_wishlist_keeps_insertion_order(db: Database):
    assert await db.add_wish(5, 367520, "Hollow Knight", 10) is AddWishResult.ADDED
    assert await db.add_wish(5, 1057090, "Ori", 10, notified_final_cents=299) is AddWishResult.ADDED
    assert await db.wishlist(5) == [
        Wish(5, 367520, "Hollow Knight", 10, None),
        Wish(5, 1057090, "Ori", 10, 299),
    ]
    assert [wish.on_sale for wish in await db.wishlist(5)] == [False, True]


async def test_same_game_cannot_be_added_twice(db: Database):
    await db.add_wish(5, 367520, "Hollow Knight", 10)
    assert await db.add_wish(5, 367520, "Hollow Knight", 10) is AddWishResult.ALREADY_THERE
    assert len(await db.wishlist(5)) == 1


async def test_wishlist_has_a_size_limit(db: Database):
    for app_id in range(MAX_WISHLIST_SIZE):
        assert await db.add_wish(5, app_id, f"Juego {app_id}", None) is AddWishResult.ADDED
    assert await db.add_wish(5, 999, "Uno más", None) is AddWishResult.LIST_FULL
    assert await db.add_wish(5, 0, "Juego 0", None) is AddWishResult.ALREADY_THERE  # repetido gana a lleno
    assert await db.add_wish(6, 999, "Otra persona", None) is AddWishResult.ADDED


async def test_remove_wish_returns_its_name(db: Database):
    await db.add_wish(5, 367520, "Hollow Knight", 10)
    assert await db.remove_wish(5, 367520) == "Hollow Knight"
    assert await db.remove_wish(5, 367520) is None
    assert await db.wishlist(5) == []


async def test_set_wish_notified(db: Database):
    await db.add_wish(5, 367520, "Hollow Knight", 10)
    await db.set_wish_notified(5, 367520, 249)
    assert (await db.wishlist(5))[0].notified_final_cents == 249
    await db.set_wish_notified(5, 367520, None)
    assert (await db.wishlist(5))[0].notified_final_cents is None


async def test_all_wishes_from_every_user(db: Database):
    await db.add_wish(5, 1, "A", 10)
    await db.add_wish(6, 1, "A", None)
    await db.add_wish(5, 2, "B", 10)
    assert [(wish.user_id, wish.app_id) for wish in await db.all_wishes()] == [(5, 1), (5, 2), (6, 1)]


# ── Esquema y migración del JSON anterior ─────────────────────────────────────


async def test_schema_version_is_recorded(db: Database, tmp_path: Path):
    await db.setup()
    with sqlite3.connect(tmp_path / "vapora.db") as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


async def test_data_survives_reopening_the_database(tmp_path: Path):
    await Database(tmp_path / "vapora.db").set_channel(1, Feature.DEALS, 100)
    assert await Database(tmp_path / "vapora.db").channels(1) == {Feature.DEALS: 100}


async def test_database_folder_is_created(tmp_path: Path):
    database = Database(tmp_path / "data" / "nueva" / "vapora.db")
    await database.setup()
    assert (tmp_path / "data" / "nueva" / "vapora.db").exists()


async def test_imports_legacy_json_once(db: Database, tmp_path: Path):
    legacy = tmp_path / "state.json"
    legacy.write_text(
        json.dumps(
            {
                "guilds": {"10": {"deals_channel": 100, "sales_channel": 200, "wishlist_channel": 300}},
                "sent": ["10:Rebajas de Otoño-2026-10-01:7d"],
                "wishlist": {
                    "5": {
                        "367520": {"name": "Hollow Knight", "guild_id": 10, "notified_final": None},
                        "1057090": {"name": "Ori", "guild_id": 10, "notified_final": 299},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert await db.channels(10) == {Feature.DEALS: 100, Feature.SALES: 200, Feature.WISHLIST: 300}
    assert await db.sent_notices(10) == {("Rebajas de Otoño-2026-10-01", "7d")}
    assert await db.wishlist(5) == [
        Wish(5, 367520, "Hollow Knight", 10, None),
        Wish(5, 1057090, "Ori", 10, 299),
    ]
    assert not legacy.exists()
    assert (tmp_path / "state.json.migrado").exists()


async def test_corrupt_legacy_json_starts_empty(db: Database, tmp_path: Path):
    (tmp_path / "state.json").write_text("{no es json", encoding="utf-8")
    assert await db.channels(1) == {}
    assert await db.all_wishes() == []


async def test_existing_database_does_not_reimport_legacy_json(tmp_path: Path):
    await Database(tmp_path / "vapora.db", tmp_path / "state.json").setup()
    (tmp_path / "state.json").write_text(
        json.dumps({"guilds": {"10": {"deals_channel": 100}}}), encoding="utf-8"
    )
    reopened = Database(tmp_path / "vapora.db", tmp_path / "state.json")
    assert await reopened.channels(10) == {}
    assert (tmp_path / "state.json").exists()


async def test_version_1_database_is_upgraded_keeping_its_data(tmp_path: Path):
    """Así está la base en producción antes de este cambio: solo la primera migración."""
    path = tmp_path / "vapora.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(MIGRATIONS[0])
        conn.execute("PRAGMA user_version = 1")
        conn.execute("INSERT INTO guild_channels (guild_id, feature, channel_id) VALUES (10, 'ofertas', 100)")
        conn.execute("INSERT INTO wishlist (user_id, app_id, name) VALUES (5, 367520, 'Hollow Knight')")
    conn.close()

    database = Database(path, tmp_path / "state.json")
    assert await database.channels(10) == {Feature.DEALS: 100}
    assert await database.wishlist(5) == [Wish(5, 367520, "Hollow Knight", None, None)]
    assert await database.guilds_posted_on(Feature.DEALS, date(2026, 10, 5)) == set()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    conn.close()


async def test_failed_migration_leaves_the_database_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Si una migración falla a la mitad, no queda aplicada a medias ni se pierden datos."""
    path = tmp_path / "vapora.db"
    await Database(path).set_channel(10, Feature.DEALS, 100)
    broken = "CREATE TABLE a_medias (x INTEGER); DROP TABLE guild_channels; ESTO NO ES SQL;"
    monkeypatch.setattr(storage_module, "MIGRATIONS", (*MIGRATIONS, broken))

    with pytest.raises(sqlite3.OperationalError):
        await Database(path).setup()

    monkeypatch.setattr(storage_module, "MIGRATIONS", MIGRATIONS)
    assert await Database(path).channels(10) == {Feature.DEALS: 100}
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name = 'a_medias'").fetchall()
    conn.close()


async def test_unknown_channel_types_are_ignored(db: Database, tmp_path: Path):
    """Por si se vuelve a una versión anterior del bot con canales de tipos más nuevos."""
    await db.set_channel(10, Feature.DEALS, 100)
    with sqlite3.connect(tmp_path / "vapora.db") as conn:
        conn.execute("PRAGMA ignore_check_constraints = ON")
        conn.execute("INSERT INTO guild_channels (guild_id, feature, channel_id) VALUES (10, 'futuro', 200)")
    conn.close()
    assert await db.channels(10) == {Feature.DEALS: 100}


# ── Publicaciones diarias ─────────────────────────────────────────────────────


async def test_daily_posts_are_tracked_per_guild_feature_and_day(db: Database):
    today, tomorrow = date(2026, 10, 5), date(2026, 10, 6)
    await db.mark_posted(10, Feature.DEALS, today)
    await db.mark_posted(11, Feature.DEALS, today)
    await db.mark_posted(10, Feature.SALES, today)
    assert await db.guilds_posted_on(Feature.DEALS, today) == {10, 11}
    await db.mark_posted(10, Feature.DEALS, tomorrow)
    assert await db.guilds_posted_on(Feature.DEALS, today) == {11}
    assert await db.guilds_posted_on(Feature.DEALS, tomorrow) == {10}
    assert await db.guilds_posted_on(Feature.SALES, today) == {10}  # cada tipo por separado


# ── Límite de deseados con pedidos simultáneos ────────────────────────────────


async def test_wishlist_limit_holds_with_simultaneous_adds(db: Database):
    for app_id in range(MAX_WISHLIST_SIZE - 1):
        await db.add_wish(5, app_id, f"Juego {app_id}", None)
    results = await asyncio.gather(*(db.add_wish(5, 1000 + n, f"Extra {n}", None) for n in range(5)))
    assert results.count(AddWishResult.ADDED) == 1
    assert len(await db.wishlist(5)) == MAX_WISHLIST_SIZE
