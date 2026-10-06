"""Qué puede hacer Vapora en cada canal, para no mandar pedidos que Discord va a rechazar.

Cada pedido rechazado (403) cuenta para el límite de Discord: con 10.000 cada 10 minutos
desde una IP, la bloquea entera (y en Railway la IP es compartida). Revisar los permisos
antes no cuesta nada: discord.py los tiene en memoria.
"""

from __future__ import annotations

from typing import Any

import discord


def missing_send_permissions(channel: Any, *, files: bool = False, reply: bool = False) -> list[str]:
    """Permisos que le faltan a Vapora para publicar una tarjeta en el canal.

    Args:
        files: si el mensaje lleva adjuntos.
        reply: si es una respuesta a otro mensaje (Discord pide poder leer el historial).

    En un MD no hay permisos que revisar: devuelve una lista vacía.
    """
    guild = getattr(channel, "guild", None)
    if guild is None:
        return []
    permissions = channel.permissions_for(guild.me)
    in_thread = isinstance(channel, discord.Thread)
    required = {
        "Ver canal": permissions.view_channel,
        "Enviar mensajes": permissions.send_messages_in_threads if in_thread else permissions.send_messages,
        "Insertar enlaces": permissions.embed_links,
    }
    if files:
        required["Adjuntar archivos"] = permissions.attach_files
    if reply:
        required["Leer el historial de mensajes"] = permissions.read_message_history
    return [name for name, granted in required.items() if not granted]


def can_hide_previews(channel: Any) -> bool:
    """Si Vapora puede ocultar el preview de un mensaje ajeno (solo en servidores)."""
    guild = getattr(channel, "guild", None)
    return guild is not None and bool(channel.permissions_for(guild.me).manage_messages)
