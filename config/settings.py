import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()


class Settings:
    # Bybit API
    BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
    BYBIT_DEMO = os.getenv("BYBIT_DEMO", "True").lower() == "true"

    PROXY_URL = os.getenv("PROXY_URL")

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # Parámetros de Riesgo Base
    LEVERAGE = 10
    TRADE_AMOUNT_USDT = 200.0
    MAX_CONCURRENT_TRADES = 10

    # PnL directo del exchange — sin simulación de fees
    # Las comisiones ya están incluidas en el closedPnl de Bybit

    # --- HYPER SCALPER V1 PARAMS ---
    SCAN_INTERVAL_SECONDS: int = 15
    MIN_VOLUME_24H: int = 500000
    TOP_COINS_LIMIT: int = 70
    STAGNATION_MOVE_PCT: float = 0.002
    
    ATR_PERIOD = 14
    ATR_MULTIPLIER_SL = 10.0
    ATR_MULTIPLIER_TP = 20.0
    
    COOLDOWN_MINUTES = 30
    
    BREAKEVEN_ACTIVATION_PCT = 0.60  # 60% hacia el TP
    TRAIL_PROTECTION_PCT = 0.50  # Asegurar 50% de la ganancia

settings = Settings()
