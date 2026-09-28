import os

from dotenv import load_dotenv

load_dotenv()


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value.replace(",", ".")) if value else default


# IVA sobre servicios digitales del exterior. Es lo que cobra la tarjeta al pagar Steam en pesos.
# La percepción de Ganancias del 30% no aplica a plataformas de videojuegos desde abril 2025
# (ARCA) y el Impuesto PAIS se derogó en diciembre 2024.
IVA_PERCENT = _float_env("IVA_PERCENT", 21.0)

# Ingresos Brutos de tu provincia (varía: 0% en varias, ~2% en CABA/PBA). 0 = sin IIBB.
PROVINCE_TAX_PERCENT = _float_env("PROVINCE_TAX_PERCENT", 0.0)

# Cada cuánto se actualizan las cotizaciones del dólar.
EXCHANGE_RATE_TTL_SECONDS = int(_float_env("EXCHANGE_RATE_TTL_SECONDS", 30 * 60))
