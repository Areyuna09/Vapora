<div align="center">

# 💨 Vapora

**Pegá un link de Steam y Vapora te dice cuánto sale en pesos argentinos 🇦🇷**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)
![Steam](https://img.shields.io/badge/Steam-Store%20API-171A21?logo=steam&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white)
![Ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?logo=ruff&logoColor=black)
![mypy](https://img.shields.io/badge/types-mypy%20strict-2A6DB2)

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
- 🧉 **Juegos argentinos**: los destaca en la tarjeta (lista del curador de Steam [Videojuegos Argentinos](https://store.steampowered.com/curator/45013169/)).
- 🔥 **Ofertas destacadas**: `/ofertas` o todos los días en el canal que elijas, con precio en pesos.
- 🔔 **Deseados**: cada uno arma su lista con `/deseado` o con el botón **Avisame si baja** de cada tarjeta, y Vapora lo menciona en el canal de deseados cuando un juego entra en oferta.
- 📅 **Rebajas de Steam**: `/rebajas` y avisos automáticos una semana antes, un día antes, al empezar y en las últimas 24 h.
- 🖼️ **Fondos de Wallpaper Engine**: `/fondo` recomienda uno en tendencia (con categoría opcional), hay un fondo del día en el canal que elijas, y los links del Workshop se muestran con su vista previa. Las vistas previas animadas de Steam son GIF chicos (160-256 px), así que Vapora las agranda a 480 px sin perder la animación. Solo fondos aptos para todo público.
- 🧹 **Reemplaza el preview de Discord** por su propia tarjeta, así no quedan dos.
- 🎨 **Color de temporada**: durante una rebaja de Steam, las tarjetas toman su color (naranja en otoño, celeste hielo en invierno, rosa en primavera y amarillo en verano).
- 💸 **Precio en pesos** con los impuestos vigentes, según el medio de pago.
- ⚡ **Caché**: los datos de Steam se guardan 1 hora y la cotización 30 minutos.

## 💰 Cómo calcula el precio

| Medio de pago | Fórmula | Fuente |
|---|---|---|
| 💳 **Mercado Pago** / tarjeta en pesos | USD × dólar oficial × (1 + IVA 21% + IIBB) | [dolarapi.com](https://dolarapi.com) |
| 🟣 **ARQ** | USD × dólar cripto | [dolarapi.com](https://dolarapi.com) |

> [!NOTE]
> Desde abril de 2025 **no** se cobra la percepción de Ganancias del 30% a las plataformas de videojuegos, y el Impuesto PAIS se derogó en diciembre de 2024.

Steam cobra en **USD** para la región LATAM, así que Vapora toma el precio en dólares de la API de Steam (`cc=ar`) y lo convierte.

## 🚀 Instalación local

**Requisitos:** Python 3.11 o superior (el proyecto usa 3.12) y un bot creado en el [Discord Developer Portal](https://discord.com/developers/applications) con **Message Content Intent** activado.

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
| `/deseado lista` · `/deseado quitar` | Ver o sacar juegos de tus deseados (de la lista o por nombre) | Todos |
| `/fondo` | Un fondo de Wallpaper Engine en tendencia (categoría opcional) | Todos |
| `/ayuda` | Qué hace Vapora y cómo usarla | Todos |
| `/config canal` | Elegir el canal de las ofertas diarias, los avisos de rebajas, los avisos de deseados o el fondo del día | Admins* |
| `/config desactivar` | Dejar de publicar ofertas o avisos | Admins* |
| `/config ver` | Ver la configuración del servidor | Admins* |

<sub>* Quienes tengan el permiso **Gestionar servidor**. Se puede cambiar en Ajustes del servidor → Integraciones → Vapora.</sub>

Cada servidor elige sus propios canales. Se guardan en una base **SQLite** (`data/vapora.db`) junto con los avisos ya enviados y las listas de deseados.

Las ofertas diarias y el fondo del día salen una vez por día en cada servidor. Si Vapora se reinicia (por ejemplo, con un deploy) hasta 6 horas después de `DEALS_HOUR` o `WALLPAPER_HOUR` y todavía no publicó, publica apenas se conecta.

Los deseados se revisan cada hora, pidiendo a Steam solo los precios y de a 100 juegos por pedido. Vapora avisa **una vez por oferta** (y otra si el precio baja más) en el canal elegido con `/config canal` → *Avisos de deseados*, mencionando a cada persona. Si el servidor no eligió canal, avisa por MD.

## ⚙️ Configuración

Todo se configura en el archivo `.env` (ver [`.env.example`](.env.example)):

| Variable | Default | Descripción |
|---|---|---|
| `DISCORD_TOKEN` | — | Token del bot (**obligatorio**) |
| `IVA_PERCENT` | `21` | IVA sobre servicios digitales |
| `PROVINCE_TAX_PERCENT` | `0` | Ingresos Brutos de tu provincia (ej. `2` en CABA/PBA) |
| `EXCHANGE_RATE_TTL_SECONDS` | `1800` | Cada cuánto se actualiza la cotización |
| `DEALS_HOUR` | `12` | Hora de Argentina a la que se publican las ofertas del día |
| `WALLPAPER_HOUR` | `18` | Hora de Argentina a la que se publica el fondo del día |
| `DATABASE_FILE` | `data/vapora.db` | Archivo de la base de datos SQLite |

> [!TIP]
> Las fechas de las rebajas se leen una vez por día del [calendario oficial de Steamworks](https://partner.steamgames.com/doc/marketing/upcoming_events). Valve no las publica en una API, así que Vapora interpreta esa página; si el formato cambia, usa la lista de respaldo de [`vapora/sales.py`](vapora/sales.py) y lo avisa en los logs.
>
> Con los fondos pasa algo parecido: sin API key, Steam no permite buscar en el Workshop, así que la lista de tendencias se lee de la [página pública](https://steamcommunity.com/app/431960/workshop/) (cada 6 horas por categoría) y los datos de cada fondo salen de la API pública. Si la página cambia, `/fondo` responde que no encontró fondos y lo avisa en los logs; el resto del bot sigue igual.

## 🗄️ Base de datos

Vapora usa **SQLite** (viene con Python, no hay que instalar nada). En Railway, la base vive en el volumen montado en `/app/data`.

| Tabla | Qué guarda |
|---|---|
| `guild_channels` | Canal elegido con `/config` para cada tipo de aviso de cada servidor |
| `sent_announcements` | Avisos de rebajas ya enviados, para no repetirlos |
| `wishlist` | Deseados de cada persona y a qué precio se avisó la última oferta |

La estructura se actualiza sola al arrancar (`PRAGMA user_version`). Si existe el `data/state.json` de versiones anteriores, se importa una vez y se renombra a `state.json.migrado`.

## 🧪 Calidad del código

```powershell
pip install -r requirements-dev.txt
ruff check .          # linter
ruff format --check . # formato
mypy                  # tipos (modo estricto)
pytest                # tests
```

Conviene correr los cuatro antes de cada push: Railway despliega lo que se sube a `main`.

Los tests no usan la red ni Discord: Steam, DolarAPI y las interacciones se reemplazan por dobles de prueba (`tests/helpers.py` y `tests/fakes.py`), y la base de datos es una SQLite temporal por test.

## 🖥️ Deploy 24/7

Vapora corre en [Railway](https://railway.com), que la redeploya sola con cada push a `main`.

| Ajuste del servicio | Valor |
|---|---|
| Start command | `python bot.py` |
| Variables | `DISCORD_TOKEN` (y las opcionales de arriba) |
| Volumen | montado en `/app/data`, para que la base de datos sobreviva a los redeploys |

La versión de Python se fija en [`.python-version`](.python-version).

## 📁 Estructura

```
├── bot.py                  # Punto de entrada (python bot.py)
├── vapora/
│   ├── bot.py              # VaporaBot: crea los servicios y registra los cogs
│   ├── config.py           # Settings: configuración leída del entorno
│   ├── cache.py            # Cachés en memoria con vencimiento
│   ├── pricing.py          # Cotizaciones del dólar y conversión a pesos
│   ├── sales.py            # Calendario de rebajas y cuándo avisarlas
│   ├── wishlist.py         # Reglas de los deseados: cuándo avisar una oferta
│   ├── storage.py          # Base de datos SQLite
│   ├── events.py           # Eventos internos entre cogs
│   ├── steam/              # Tienda de Steam
│   │   ├── models.py       #   modelos (StoreItem, Price, Deal…)
│   │   ├── links.py        #   detección de links en un mensaje
│   │   ├── parsers.py      #   respuestas de Steam → modelos (funciones puras)
│   │   ├── client.py       #   SteamClient: pedidos y caché
│   │   └── workshop.py     #   fondos de Wallpaper Engine del Workshop
│   ├── ui/                 # Lo que se ve en Discord
│   │   ├── game_card.py    #   tarjeta de un juego
│   │   ├── wallpaper_card.py # tarjeta de un fondo
│   │   ├── announcements.py#   ofertas y avisos de rebajas
│   │   ├── panels.py       #   /ayuda, /config y /deseado
│   │   ├── buttons.py      #   botones de las tarjetas
│   │   └── formatting.py   #   formato de precios
│   └── cogs/               # Comandos, eventos y tareas, por función
│       ├── links.py        #   responde a los links de Steam y del Workshop
│       ├── deals.py        #   /ofertas, /rebajas y sus publicaciones
│       ├── wishlist.py     #   /deseado y avisos de ofertas
│       ├── wallpapers.py   #   /fondo y el fondo del día
│       ├── settings.py     #   /config
│       └── general.py      #   /ayuda
└── tests/                  # Tests con pytest
```

Las dependencias van en una sola dirección: los **cogs** usan la **UI** y los **servicios** (`steam`, `pricing`, `sales`, `storage`), y estos no saben nada de Discord. Por eso la lógica se puede probar sin conectarse.

## 🔒 Seguridad

El token **nunca** se sube al repositorio: vive solo en `.env`, que está en el `.gitignore`. Si se filtra, regeneralo en el Developer Portal con **Reset Token**.

Además:

- **Sin menciones masivas**: Vapora no menciona a nadie salvo a quien pidió un aviso de deseados. Un `@everyone` en el nombre de un juego o un fondo (que vienen de Steam) no notifica a nadie.
- **Límites por usuario**: 8 comandos o botones cada 20 s, 5 mensajes con links cada 30 s y 3 `/fondo` por minuto. Quien se pasa recibe un solo aviso de "más despacio" (o ninguno, en los links), así el spam no se convierte en pedidos de Vapora a Discord.
- **Descargas solo de Steam**: las vistas previas se bajan solo por HTTPS desde los servidores de imágenes de Steam, sin seguir redirecciones y con tope de tamaño.
- **Consultas a la base parametrizadas** y `/config` reservado a quienes gestionan el servidor.

---

<div align="center">
<sub>Datos de Steam y <a href="https://dolarapi.com">DolarAPI</a></sub>
</div>
