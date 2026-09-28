<div align="center">

# 💨 Vapora

**Pegá un link de Steam y Vapora te dice cuánto sale en pesos argentinos 🇦🇷**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)
![Steam](https://img.shields.io/badge/Steam-Store%20API-171A21?logo=steam&logoColor=white)
![Hosting](https://img.shields.io/badge/Oracle%20Cloud-Always%20Free-F80000?logo=oracle&logoColor=white)

</div>

---

## ✨ Qué hace

Vapora escucha los mensajes del servidor. Cuando alguien comparte un link de la tienda de Steam, responde con una tarjeta así:

```
┌──────────────────────────────────────────────────────────────┐
│ 🇦🇷 The Last of Us™ Parte I                                  │
│ Descubre el galardonado juego que inspiró la aclamada serie… │
│                                                              │
│ 🎭 Acción · Aventura                                         │
│                                                              │
│ 💵 Precio Steam (AR)   💳 Mercado Pago     🟣 ARQ            │
│ USD 29,99              $ 56.246,24         $ 48.683,97       │
│ ~~USD 59,99~~ (-50%)                                         │
│                                                              │
│ ⭐ Reseñas             📅 Lanzamiento      🛠️ Desarrollador  │
│ Muy positivas          28 MAR 2023         Naughty Dog LLC   │
│ 85% de 109.742                                               │
│                                                              │
│ [ imagen del juego ]                                         │
│ Oficial $ 1.550,00 · ARQ $ 1.623,34 · IVA 21% (sin IIBB)     │
└──────────────────────────────────────────────────────────────┘
```

- 🔗 **Detección automática**: sin comandos. Juegos, DLC, paquetes (`/sub/`) y bundles, varios por mensaje.
- 🧉 **Juegos argentinos**: los destaca en la tarjeta (lista del curador de Steam que usa Steamcito).
- 🔥 **Ofertas destacadas**: `/ofertas` o todos los días en el canal que elijas, con precio en pesos.
- 🔔 **Deseados**: cada uno arma su lista con `/deseado` o con el botón **Avisame si baja** de cada tarjeta, y Vapora lo menciona en el canal de deseados cuando un juego entra en oferta.
- 📅 **Rebajas de Steam**: `/rebajas` y avisos automáticos una semana antes, un día antes, al empezar y en las últimas 24 h.
- 🧹 **Reemplaza el preview de Discord** por su propia tarjeta, así no quedan dos.
- 💸 **Precio en pesos** con los impuestos vigentes, según el medio de pago.
- ⚡ **Caché**: los datos de Steam se guardan 1 hora y la cotización 30 minutos.

## 💰 Cómo calcula el precio

| Medio de pago | Fórmula | Fuente |
|---|---|---|
| 💳 **Mercado Pago** / tarjeta en pesos | USD × dólar oficial × (1 + IVA 21% + IIBB) | [dolarapi.com](https://dolarapi.com) |
| 🟣 **ARQ** | USD × dólar cripto | [dolarapi.com](https://dolarapi.com) |

> [!NOTE]
> Desde abril de 2025 **no** se cobra la percepción de Ganancias del 30% a las plataformas de videojuegos, y el Impuesto PAIS se derogó en diciembre de 2024. El cálculo coincide con el de [Steamcito](https://steamcito.com.ar).

Steam cobra en **USD** para la región LATAM, así que Vapora toma el precio en dólares de la API de Steam (`cc=ar`) y lo convierte.

## 🚀 Instalación local

**Requisitos:** Python 3.11 o superior y un bot creado en el [Discord Developer Portal](https://discord.com/developers/applications) con **Message Content Intent** activado.

```powershell
git clone https://github.com/<tu-usuario>/vapora.git
cd vapora
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # y pegá tu token adentro
python bot.py
```

### Invitar el bot a un servidor

```
https://discord.com/oauth2/authorize?client_id=<CLIENT_ID>&scope=bot&permissions=93184
```

| Permiso | Para qué |
|---|---|
| Ver canales · Leer historial | Leer los mensajes con links |
| Enviar mensajes · Insertar enlaces | Responder con la tarjeta |
| Gestionar mensajes | Ocultar el preview original de Discord (opcional) |

## 💬 Comandos

| Comando | Qué hace | Quién |
|---|---|---|
| `/ofertas` | Ofertas destacadas de Steam con precio en pesos | Todos |
| `/rebajas` | Rebaja actual y próximas, con cuenta regresiva | Todos |
| `/deseado agregar` | Agregar un juego a tus deseados (por nombre o link) | Todos |
| `/deseado lista` · `/deseado quitar` | Ver o sacar juegos de tus deseados | Todos |
| `/ayuda` | Qué hace Vapora y cómo usarla | Todos |
| `/config canal` | Elegir el canal de las ofertas diarias, los avisos de rebajas o los avisos de deseados | Admins* |
| `/config desactivar` | Dejar de publicar ofertas o avisos | Admins* |
| `/config ver` | Ver la configuración del servidor | Admins* |

<sub>* Quienes tengan el permiso **Gestionar servidor**. Se puede cambiar en Ajustes del servidor → Integraciones → Vapora.</sub>

Cada servidor elige sus propios canales. Se guardan en `data/state.json` junto con los avisos ya enviados y las listas de deseados.

Los deseados se revisan cada hora. Vapora avisa **una vez por oferta** (y otra si el precio baja más) en el canal elegido con `/config canal` → *Avisos de deseados*, mencionando a cada persona. Si el servidor no eligió canal, avisa por MD.

## ⚙️ Configuración

Todo se configura en el archivo `.env` (ver [`.env.example`](.env.example)):

| Variable | Default | Descripción |
|---|---|---|
| `DISCORD_TOKEN` | — | Token del bot (**obligatorio**) |
| `IVA_PERCENT` | `21` | IVA sobre servicios digitales |
| `PROVINCE_TAX_PERCENT` | `0` | Ingresos Brutos de tu provincia (ej. `2` en CABA/PBA) |
| `EXCHANGE_RATE_TTL_SECONDS` | `1800` | Cada cuánto se actualiza la cotización |
| `DEALS_HOUR` | `12` | Hora de Argentina a la que se publican las ofertas del día |

> [!TIP]
> Las fechas de las rebajas están en [`sales.py`](sales.py), copiadas del [calendario oficial de Steamworks](https://partner.steamgames.com/doc/marketing/upcoming_events). Valve no las publica en una API, así que hay que actualizarlas a mano una o dos veces por año.

## 🧪 Tests

```powershell
pip install -r requirements-dev.txt
pytest
```

## 🖥️ Deploy 24/7

Vapora corre en una VM **Always Free** de Oracle Cloud como servicio `systemd`, que la arranca con el sistema y la reinicia si se cae. El archivo del servicio está en [`deploy/vapora.service`](deploy/vapora.service).

```bash
sudo cp deploy/vapora.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vapora
journalctl -u vapora -f     # ver logs
```

## 📁 Estructura

```
├── bot.py              # Bot de Discord: eventos y armado de la tarjeta
├── steam.py            # Consultas a la tienda y reseñas de Steam
├── prices.py           # Cotizaciones y conversión a pesos
├── sales.py            # Calendario de rebajas de Steam
├── wishlist.py         # Deseados: cuándo avisar de una oferta
├── storage.py          # Canales, avisos enviados y deseados (JSON)
├── announcements.py    # Tarjetas de ofertas y avisos de rebajas
├── formatting.py       # Formato de precios (USD y pesos)
├── config.py           # Impuestos y parámetros configurables
├── deploy/
│   └── vapora.service  # Servicio systemd para el servidor
└── tests/              # Tests con pytest
```

## 🔒 Seguridad

El token **nunca** se sube al repositorio: vive solo en `.env`, que está en el `.gitignore`. Si se filtra, regeneralo en el Developer Portal con **Reset Token**.

---

<div align="center">
<sub>Hecho con 🧉 en Argentina · Datos de Steam, <a href="https://dolarapi.com">DolarAPI</a> e ideas de <a href="https://steamcito.com.ar">Steamcito</a></sub>
</div>
