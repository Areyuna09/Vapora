"""Eventos propios de Vapora, para que sus partes se avisen cosas sin conocerse entre sí.

Se disparan con `bot.dispatch(nombre, ...)` y los atiende cualquier cog que tenga un
listener llamado `on_<nombre>`.
"""

# Alguien tocó "Avisame si baja" en una tarjeta. Argumentos: (interaction, app_id).
WISH_BUTTON = "wish_button"

# Un servidor eligió el canal de avisos de rebajas. Sin argumentos.
SALES_CHANNEL_SET = "sales_channel_set"
