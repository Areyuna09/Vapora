from unittest.mock import AsyncMock, MagicMock

import pytest
from fakes import FakeBot, make_interaction, sent_kwargs

from vapora.cogs.general import GeneralCog
from vapora.storage import Database


@pytest.fixture
def bot(db: Database) -> FakeBot:
    return FakeBot(db)


async def test_help_hides_admin_section_from_members(bot: FakeBot):
    cog = GeneralCog(bot)  # type: ignore[arg-type]
    sections = {}
    for is_admin in (False, True):
        interaction = make_interaction(manage_guild=is_admin)
        await cog.show_help.callback(cog, interaction)
        sent = sent_kwargs(interaction.response.send_message)
        assert sent["ephemeral"] is True
        sections[is_admin] = [field.name for field in sent["embed"].fields]
    assert "⚙️ Administración" in sections[True]
    assert "⚙️ Administración" not in sections[False]


async def test_ping(bot: FakeBot):
    cog = GeneralCog(bot)  # type: ignore[arg-type]
    ctx = MagicMock(send=AsyncMock())
    await cog.ping.callback(cog, ctx)
    ctx.send.assert_awaited_once_with("🏓 Pong!")
