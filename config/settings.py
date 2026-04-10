import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()


class Settings:
    # Bybit API
    BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
    BYBIT_DEMO = os.getenv("BYBIT_DEMO", "True").lower() == "true"

    # Proxy (Crucial para Render/Hugging Face 403 bypass)
    PROXY_URL = os.getenv("PROXY_URL")  # Ejemplo: "http://user:pass@host:port"

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # Parámetros de Riesgo Base
    LEVERAGE = int(os.getenv("LEVERAGE") or 5)
    TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT_USDT") or 100.0)
    MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES") or 10)

    # Cobertura de comisiones (para breakeven mínimo)
    BREAKEVEN_SPREAD = 0.001  # 0.1% sobre entrada para cubrir comisiones

    # Filtros Institucionales
    KILLZONE_FILTER = os.getenv("KILLZONE_FILTER", "True").lower() == "true"
    HTF_CONFLUENCE = os.getenv("HTF_CONFLUENCE", "True").lower() == "true"


settings = Settings()
