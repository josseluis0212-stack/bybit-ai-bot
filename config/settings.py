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
    LEVERAGE = int(os.getenv("LEVERAGE") or 10)
    TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT_USDT") or 20.0)
    MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES") or 10)

    # Cobertura de comisiones (para simular deducción y calcular PNL real)
    TAKER_FEE = 0.00055  # 0.055% bybit taker fee (entrada + salida = 0.11% aprox)
    BREAKEVEN_SPREAD = 0.0015  # 0.15% sobre entrada para cubrir comisiones reales

    # --- HYPER SCALPER V1 PARAMS ---
    SCAN_INTERVAL_SECONDS = 15
    MIN_VOL_24H_USD = 500000
    TOP_COINS_LIMIT = 70
    
    ATR_PERIOD = 14
    ATR_MULTIPLIER_SL = 2.2
    ATR_MULTIPLIER_TP = 4.4
    
    COOLDOWN_MINUTES = 30
    
    BREAKEVEN_ACTIVATION_PCT = 0.60  # 60% hacia el TP
    TRAIL_PROTECTION_PCT = 0.50  # Asegurar 50% de la ganancia

settings = Settings()
