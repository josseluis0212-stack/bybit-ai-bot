"""
Configuración Actual del Bot
============================

Monedas: 100 (top por volumen)
Volumen mínimo: 330,000 USDT
Máximo operaciones: 10
Margen: $20
Apalancamiento: 10x
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
    BYBIT_DEMO = os.getenv("BYBIT_DEMO", "True").lower() == "true"

    PROXY_URL = os.getenv("PROXY_URL")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    LEVERAGE = int(os.getenv("LEVERAGE") or 5)
    TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT_USDT") or 100.0)
    MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES") or 10)

    BREAKEVEN_SPREAD = 0.001

    KILLZONE_FILTER = os.getenv("KILLZONE_FILTER", "True").lower() == "true"
    HTF_CONFLUENCE = os.getenv("HTF_CONFLUENCE", "True").lower() == "true"


settings = Settings()
