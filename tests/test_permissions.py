from unittest.mock import MagicMock

import discord

from vapora.permissions import can_hide_previews, missing_send_permissions

ALL = {
    "view_channel": True,
    "send_messages": True,
    "send_messages_in_threads": True,
    "embed_links": True,
    "attach_files": True,
    "read_message_history": True,
    "manage_messages": True,
}


def channel(kind: type = discord.TextChannel, **permissions: bool) -> MagicMock:
    mock = MagicMock(spec=kind)
    mock.guild = MagicMock()
    mock.permissions_for.return_value = MagicMock(**{**ALL, **permissions})
    return mock


def dm_channel() -> MagicMock:
    mock = MagicMock(spec=discord.DMChannel)
    mock.guild = None
    return mock


def test_nothing_missing():
    assert missing_send_permissions(channel(), files=True, reply=True) == []


def test_lists_only_what_is_missing():
    assert missing_send_permissions(channel(view_channel=False)) == ["Ver canal"]
    assert missing_send_permissions(channel(embed_links=False, send_messages=False)) == [
        "Enviar mensajes",
        "Insertar enlaces",
    ]


def test_files_and_replies_are_checked_only_when_needed():
    limited = channel(attach_files=False, read_message_history=False)
    assert missing_send_permissions(limited) == []
    assert missing_send_permissions(limited, files=True) == ["Adjuntar archivos"]
    assert missing_send_permissions(limited, reply=True) == ["Leer el historial de mensajes"]


def test_threads_use_their_own_send_permission():
    thread = channel(discord.Thread, send_messages=False)
    assert missing_send_permissions(thread) == []  # en hilos cuenta "Enviar mensajes en hilos"
    assert missing_send_permissions(channel(discord.Thread, send_messages_in_threads=False)) == [
        "Enviar mensajes"
    ]


def test_permissions_are_checked_for_vapora_itself():
    text = channel()
    missing_send_permissions(text)
    text.permissions_for.assert_called_once_with(text.guild.me)


def test_direct_messages_have_nothing_to_check():
    assert missing_send_permissions(dm_channel(), files=True, reply=True) == []


def test_hiding_previews_needs_manage_messages_and_a_server():
    assert can_hide_previews(channel())
    assert not can_hide_previews(channel(manage_messages=False))
    assert not can_hide_previews(dm_channel())  # en un MD nunca se puede editar un mensaje ajeno
