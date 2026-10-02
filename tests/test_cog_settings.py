from unittest.mock import MagicMock

import pytest
from fakes import FakeBot, make_interaction, sent_kwargs, sent_text

from vapora import events
from vapora.cogs.settings import SettingsCog, missing_permissions
from vapora.storage import Database, Feature

GUILD, CHANNEL = 10, 100


@pytest.fixture
def bot(db: Database) -> FakeBot:
    return FakeBot(db)


def choice(feature: Feature) -> MagicMock:
    return MagicMock(value=feature.value)


def text_channel(channel_id: int = CHANNEL, **permissions: bool) -> MagicMock:
    granted = {"view_channel": True, "send_messages": True, "embed_links": True, **permissions}
    channel = MagicMock(id=channel_id, mention=f"<#{channel_id}>")
    channel.permissions_for.return_value = MagicMock(**granted)
    return channel


async def test_config_sets_the_channel(bot: FakeBot, db: Database):
    cog = SettingsCog(bot)  # type: ignore[arg-type]
    interaction = make_interaction(guild_id=GUILD)
    await cog.set_channel.callback(cog, interaction, choice(Feature.DEALS), text_channel())
    assert sent_text(interaction.response.send_message) == (
        "✅ **🔥 Ofertas destacadas** → <#100>\nLas voy a publicar todos los días a las 12:00."
    )
    assert sent_kwargs(interaction.response.send_message)["ephemeral"] is True
    assert await db.channels(GUILD) == {Feature.DEALS: CHANNEL}
    bot.dispatch.assert_not_called()


async def test_config_sales_channel_triggers_pending_notice(bot: FakeBot, db: Database):
    cog = SettingsCog(bot)  # type: ignore[arg-type]
    interaction = make_interaction(guild_id=GUILD)
    await cog.set_channel.callback(cog, interaction, choice(Feature.SALES), text_channel())
    assert sent_text(interaction.response.send_message).endswith(
        "Voy a avisar antes de cada rebaja, cuando empieza y en sus últimas 24 horas."
    )
    bot.dispatch.assert_called_once_with(events.SALES_CHANNEL_SET)


async def test_config_wishlist_channel(bot: FakeBot, db: Database):
    cog = SettingsCog(bot)  # type: ignore[arg-type]
    interaction = make_interaction(guild_id=GUILD)
    await cog.set_channel.callback(cog, interaction, choice(Feature.WISHLIST), text_channel(300))
    assert sent_text(interaction.response.send_message) == (
        "✅ **🔔 Avisos de deseados** → <#300>\n"
        "Cuando un juego de la lista de alguien entre en oferta, lo menciono ahí."
    )
    assert await db.channels(GUILD) == {Feature.WISHLIST: 300}


async def test_config_rejects_channel_where_vapora_cannot_post(bot: FakeBot, db: Database):
    cog = SettingsCog(bot)  # type: ignore[arg-type]
    interaction = make_interaction(guild_id=GUILD)
    locked = text_channel(send_messages=False, embed_links=False)
    await cog.set_channel.callback(cog, interaction, choice(Feature.DEALS), locked)
    assert sent_text(interaction.response.send_message) == (
        "⚠️ No puedo publicar en <#100>. Me faltan estos permisos ahí: **Enviar mensajes, Insertar enlaces**."
    )
    assert await db.channels(GUILD) == {}


def test_missing_permissions_lists_only_what_is_missing():
    assert missing_permissions(text_channel(), MagicMock()) == []
    assert missing_permissions(text_channel(view_channel=False), MagicMock()) == ["Ver canal"]


async def test_config_disable(bot: FakeBot, db: Database):
    await db.set_channel(GUILD, Feature.SALES, CHANNEL)
    cog = SettingsCog(bot)  # type: ignore[arg-type]
    interaction = make_interaction(guild_id=GUILD)
    await cog.disable.callback(cog, interaction, choice(Feature.SALES))
    assert sent_text(interaction.response.send_message) == "🔕 **📅 Avisos de rebajas** desactivado."
    assert await db.channels(GUILD) == {}


async def test_config_show(bot: FakeBot, db: Database):
    await db.set_channel(GUILD, Feature.DEALS, CHANNEL)
    cog = SettingsCog(bot)  # type: ignore[arg-type]
    interaction = make_interaction(guild_id=GUILD)
    await cog.show.callback(cog, interaction)
    embed = sent_kwargs(interaction.response.send_message)["embed"]
    assert embed.title == "⚙️ Configuración de Vapora"
    assert embed.fields[0].value.startswith("<#100>")
