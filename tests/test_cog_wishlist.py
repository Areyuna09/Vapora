import discord
import pytest
from fakes import FakeBot, FakeSteam, make_interaction, sent_kwargs, sent_text
from helpers import make_item

from vapora.cogs.wishlist import WishlistCog
from vapora.storage import MAX_WISHLIST_SIZE, Database, Feature, Wish

HOLLOW_KNIGHT = make_item(367520, "Hollow Knight", price_cents=499)
ORI = make_item(1057090, "Ori and the Will of the Wisps", price_cents=299, initial_cents=2999, discount=90)
USER, GUILD, WISH_CHANNEL = 5, 10, 300


@pytest.fixture
def bot(db: Database) -> FakeBot:
    return FakeBot(db, FakeSteam(HOLLOW_KNIGHT, ORI))


@pytest.fixture
def cog(bot: FakeBot) -> WishlistCog:
    return WishlistCog(bot)  # type: ignore[arg-type]


async def add(cog: WishlistCog, text: str, interaction=None):
    interaction = interaction or make_interaction(USER, GUILD)
    await cog.add.callback(cog, interaction, text)
    return interaction


# ── /deseado agregar ──────────────────────────────────────────────────────────


async def test_add_game_at_full_price(cog: WishlistCog, db: Database):
    interaction = await add(cog, "367520")
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert sent_text(interaction.followup.send) == (
        "✅ Agregué **Hollow Knight** a tus deseados. Te aviso por MD cuando entre en oferta 🔔"
    )
    assert sent_kwargs(interaction.followup.send)["ephemeral"] is True
    assert await db.wishlist(USER) == [Wish(USER, 367520, "Hollow Knight", GUILD, None)]


async def test_add_says_which_channel_will_be_used(cog: WishlistCog, db: Database):
    await db.set_channel(GUILD, Feature.WISHLIST, WISH_CHANNEL)
    interaction = await add(cog, "367520")
    assert sent_text(interaction.followup.send).endswith("Te aviso en <#300> cuando entre en oferta 🔔")


async def test_add_by_name_or_link(cog: WishlistCog, db: Database):
    await add(cog, "hollow")
    await add(cog, "https://store.steampowered.com/app/1057090/Ori/")
    assert [wish.app_id for wish in await db.wishlist(USER)] == [367520, 1057090]


async def test_add_game_already_on_sale_shows_card_and_is_not_notified_again(cog: WishlistCog, db: Database):
    interaction = await add(cog, "1057090")
    assert sent_text(interaction.followup.send) == (
        "✅ Agregué **Ori and the Will of the Wisps** a tus deseados. ¡Y ya está en oferta! 🔥"
    )
    assert sent_kwargs(interaction.followup.send)["embed"].title == "🇦🇷 Ori and the Will of the Wisps"
    assert (await db.wishlist(USER))[0].notified_final_cents == 299


async def test_add_duplicate(cog: WishlistCog):
    await add(cog, "367520")
    interaction = await add(cog, "367520")
    assert sent_text(interaction.followup.send) == "Ya tenías **Hollow Knight** en tus deseados 😉"


async def test_add_to_full_list(cog: WishlistCog, db: Database):
    for app_id in range(MAX_WISHLIST_SIZE):
        await db.add_wish(USER, app_id, f"Juego {app_id}", GUILD)
    interaction = await add(cog, "367520")
    assert sent_text(interaction.followup.send) == (
        "Tu lista está llena (25 juegos). Sacá alguno con `/deseado quitar`."
    )


async def test_add_unknown_game(cog: WishlistCog, db: Database):
    interaction = await add(cog, "juego inexistente")
    assert sent_text(interaction.followup.send) == (
        "🤔 No encontré ese juego en Steam. Probá con el link de la tienda."
    )
    assert await db.wishlist(USER) == []


async def test_autocomplete_suggests_store_games(cog: WishlistCog, bot: FakeBot):
    interaction = make_interaction()
    choices = await cog._suggest_store_games(interaction, "hollow")
    assert [(choice.name, choice.value) for choice in choices] == [("Hollow Knight", "app:367520")]
    assert await cog._suggest_store_games(interaction, "h") == []  # muy corto
    assert await cog._suggest_store_games(interaction, "https://store.steampowered.com/app/1/") == []
    bot.steam.down = True
    assert await cog._suggest_store_games(interaction, "hollow") == []


# ── Botón "Avisame si baja" ───────────────────────────────────────────────────


async def test_wish_button_adds_without_repeating_the_card(cog: WishlistCog, db: Database):
    interaction = make_interaction(USER, GUILD)
    await cog.on_wish_button(interaction, 1057090)
    assert sent_text(interaction.followup.send).endswith("¡Y ya está en oferta! 🔥")
    assert "embed" not in sent_kwargs(interaction.followup.send)
    assert [wish.app_id for wish in await db.wishlist(USER)] == [1057090]


async def test_wish_button_when_steam_is_down(cog: WishlistCog, bot: FakeBot, db: Database):
    bot.steam.down = True
    interaction = make_interaction(USER, GUILD)
    await cog.on_wish_button(interaction, 367520)
    assert sent_text(interaction.followup.send) == (
        "😕 No pude consultar ese juego en Steam. Probá de nuevo en un rato."
    )
    assert await db.wishlist(USER) == []


# ── /deseado quitar y /deseado lista ──────────────────────────────────────────


async def test_remove(cog: WishlistCog, db: Database):
    await db.add_wish(USER, 367520, "Hollow Knight", GUILD)
    interaction = make_interaction(USER, GUILD)
    await cog.remove.callback(cog, interaction, "367520")
    assert sent_text(interaction.response.send_message) == "🗑️ Saqué **Hollow Knight** de tus deseados."
    assert await db.wishlist(USER) == []


async def test_remove_something_not_in_the_list(cog: WishlistCog):
    for text in ("367520", "no es un id"):
        interaction = make_interaction(USER, GUILD)
        await cog.remove.callback(cog, interaction, text)
        assert sent_text(interaction.response.send_message) == "Ese juego no está en tus deseados."


async def test_remove_autocomplete_suggests_only_own_wishes(cog: WishlistCog, db: Database):
    await db.add_wish(USER, 367520, "Hollow Knight", GUILD)
    await db.add_wish(USER, 1057090, "Ori and the Will of the Wisps", GUILD)
    await db.add_wish(99, 730, "Counter-Strike 2", GUILD)
    choices = await cog._suggest_own_wishes(make_interaction(USER), "ori")
    assert [(choice.name, choice.value) for choice in choices] == [
        ("Ori and the Will of the Wisps", "app:1057090")
    ]
    assert len(await cog._suggest_own_wishes(make_interaction(USER), "")) == 2


async def test_show_list(cog: WishlistCog, db: Database):
    empty = make_interaction(USER)
    await cog.show.callback(cog, empty)
    assert (
        sent_text(empty.response.send_message)
        == "Tu lista está vacía. Agregá juegos con `/deseado agregar` 📝"
    )

    await db.add_wish(USER, 367520, "Hollow Knight", GUILD)
    interaction = make_interaction(USER)
    await cog.show.callback(cog, interaction)
    embed = sent_kwargs(interaction.response.send_message)["embed"]
    assert embed.title == "📝 Tus deseados (1/25)"
    assert sent_kwargs(interaction.response.send_message)["ephemeral"] is True


# ── Avisos de ofertas ─────────────────────────────────────────────────────────


async def test_notifies_in_the_wishlist_channel_mentioning_the_user(
    cog: WishlistCog, bot: FakeBot, db: Database
):
    await db.set_channel(GUILD, Feature.WISHLIST, WISH_CHANNEL)
    channel = bot.add_channel(WISH_CHANNEL)
    await db.add_wish(USER, 1057090, ORI.name, GUILD)

    await cog.check_prices()

    assert sent_text(channel.send) == (
        "<@5> 🔔 ¡**Ori and the Will of the Wisps**, de tu lista de deseados, está en oferta! (-90%)"
    )
    sent = sent_kwargs(channel.send)
    assert sent["embed"].title == "🇦🇷 Ori and the Will of the Wisps"
    mentions = sent["allowed_mentions"]
    assert [user.id for user in mentions.users] == [USER]  # solo esa persona
    assert not mentions.everyone and not mentions.roles
    assert (await db.wishlist(USER))[0].notified_final_cents == 299


async def test_same_sale_is_notified_only_once(cog: WishlistCog, bot: FakeBot, db: Database):
    await db.set_channel(GUILD, Feature.WISHLIST, WISH_CHANNEL)
    channel = bot.add_channel(WISH_CHANNEL)
    await db.add_wish(USER, 1057090, ORI.name, GUILD)
    await cog.check_prices()
    await cog.check_prices()
    channel.send.assert_awaited_once()


async def test_notifies_by_dm_when_guild_has_no_wishlist_channel(
    cog: WishlistCog, bot: FakeBot, db: Database
):
    user = bot.add_user(USER)
    await db.add_wish(USER, 1057090, ORI.name, GUILD)
    await cog.check_prices()
    assert sent_text(user.send).startswith("🔔 ¡**Ori and the Will of the Wisps**")
    assert (await db.wishlist(USER))[0].notified_final_cents == 299


async def test_falls_back_to_dm_when_channel_rejects_the_message(
    cog: WishlistCog, bot: FakeBot, db: Database
):
    await db.set_channel(GUILD, Feature.WISHLIST, WISH_CHANNEL)
    channel = bot.add_channel(WISH_CHANNEL)
    channel.send.side_effect = discord.HTTPException(type("R", (), {"status": 500, "reason": "x"})(), "falló")
    user = bot.add_user(USER)
    await db.add_wish(USER, 1057090, ORI.name, GUILD)
    await cog.check_prices()
    user.send.assert_awaited_once()


async def test_failed_notification_is_retried_next_time(cog: WishlistCog, bot: FakeBot, db: Database):
    bot.add_user(USER, dms_open=False)
    await db.add_wish(USER, 1057090, ORI.name, GUILD)
    await cog.check_prices()
    assert (await db.wishlist(USER))[0].notified_final_cents is None  # sin marcar: se reintenta


async def test_game_at_full_price_is_not_notified(cog: WishlistCog, bot: FakeBot, db: Database):
    user = bot.add_user(USER)
    await db.add_wish(USER, 367520, HOLLOW_KNIGHT.name, GUILD)
    await cog.check_prices()
    user.send.assert_not_awaited()


async def test_ended_sale_is_forgotten_so_the_next_one_notifies(cog: WishlistCog, bot: FakeBot, db: Database):
    bot.add_user(USER)
    await db.add_wish(USER, 367520, HOLLOW_KNIGHT.name, GUILD, notified_final_cents=249)
    await cog.check_prices()
    assert (await db.wishlist(USER))[0].notified_final_cents is None


async def test_steam_down_skips_the_check_without_losing_state(cog: WishlistCog, bot: FakeBot, db: Database):
    user = bot.add_user(USER)
    await db.add_wish(USER, 1057090, ORI.name, GUILD)
    bot.steam.down = True
    await cog.check_prices()
    user.send.assert_not_awaited()
    assert (await db.wishlist(USER))[0].notified_final_cents is None


async def test_each_user_is_notified_about_their_own_wishes(cog: WishlistCog, bot: FakeBot, db: Database):
    first, second = bot.add_user(5), bot.add_user(6)
    await db.add_wish(5, 1057090, ORI.name, None)
    await db.add_wish(6, 1057090, ORI.name, None)
    await db.add_wish(6, 367520, HOLLOW_KNIGHT.name, None)
    await cog.check_prices()
    first.send.assert_awaited_once()
    second.send.assert_awaited_once()


# ── Mejoras: botón robusto, quitar por nombre y chequeo en lote ───────────────


async def test_wish_button_always_answers_even_on_unexpected_errors(
    cog: WishlistCog, bot: FakeBot, monkeypatch: pytest.MonkeyPatch
):
    async def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("base de datos rota")

    monkeypatch.setattr(bot.db, "add_wish", broken)
    interaction = make_interaction(USER, GUILD)
    await cog.on_wish_button(interaction, 367520)  # no propaga: el error se registra
    assert sent_text(interaction.followup.send) == "😕 Algo salió mal. Probá de nuevo en un rato."


async def test_remove_by_typed_name(cog: WishlistCog, db: Database):
    await db.add_wish(USER, 367520, "Hollow Knight", GUILD)
    interaction = make_interaction(USER, GUILD)
    await cog.remove.callback(cog, interaction, "hollow knight")
    assert sent_text(interaction.response.send_message) == "🗑️ Saqué **Hollow Knight** de tus deseados."
    assert await db.wishlist(USER) == []


async def test_remove_by_autocomplete_choice(cog: WishlistCog, db: Database):
    await db.add_wish(USER, 367520, "Hollow Knight", GUILD)
    await cog.remove.callback(cog, make_interaction(USER, GUILD), "app:367520")
    assert await db.wishlist(USER) == []


async def test_add_by_autocomplete_choice(cog: WishlistCog, db: Database):
    await add(cog, "app:367520")
    assert [wish.app_id for wish in await db.wishlist(USER)] == [367520]


async def test_price_check_asks_all_prices_at_once_and_cards_only_for_sales(
    cog: WishlistCog, bot: FakeBot, db: Database
):
    bot.add_user(5)
    bot.add_user(6)
    await db.add_wish(5, 1057090, ORI.name, None)
    await db.add_wish(6, 1057090, ORI.name, None)
    await db.add_wish(6, 367520, HOLLOW_KNIGHT.name, None)
    await cog.check_prices()
    assert bot.steam.price_requests == [{1057090, 367520}]
    assert [ref.id for ref in bot.steam.item_requests] == [
        1057090
    ]  # una sola vez, solo el que está en oferta


async def test_notification_card_shows_the_fresh_price(cog: WishlistCog, bot: FakeBot, db: Database):
    user = bot.add_user(USER)
    await db.add_wish(USER, 1057090, ORI.name, GUILD)
    fresh = make_item(1057090, ORI.name, price_cents=199, initial_cents=2999, discount=93)
    stale_card = ORI  # lo que tendría el caché de tarjetas

    async def prices(app_ids: object) -> dict:
        return {1057090: fresh.price}

    bot.steam.prices = prices  # type: ignore[method-assign]
    assert bot.steam.items[ORI.ref] is stale_card
    await cog.check_prices()
    assert "1,99" in sent_kwargs(user.send)["embed"].fields[0].value
    assert (await db.wishlist(USER))[0].notified_final_cents == 199


async def test_games_steam_did_not_report_are_left_untouched(cog: WishlistCog, bot: FakeBot, db: Database):
    user = bot.add_user(USER)
    await db.add_wish(USER, 42, "Juego retirado de la tienda", GUILD, notified_final_cents=100)
    await cog.check_prices()
    user.send.assert_not_awaited()
    assert (await db.wishlist(USER))[0].notified_final_cents == 100  # no se olvida el aviso
