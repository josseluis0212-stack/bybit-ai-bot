import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_KEY = os.getenv("BYBIT_API_KEY", "").strip()
    SECRET_KEY = os.getenv("BYBIT_API_SECRET", os.getenv("BYBIT_SECRET_KEY", "")).strip()
    DEMO_MODE = os.getenv("BYBIT_DEMO", os.getenv("DEMO_MODE", "true")).lower() == "true"
    TIMEFRAME = os.getenv("TIMEFRAME", "5m")
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "8.0")) # Deprecated, using MARGIN_USDT now
    MARGIN_USDT = 15.0  # Forzado a 15 dólares de margen real por operación
    MAX_OPEN_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES", os.getenv("MAX_OPEN_TRADES", "5")))
    LEVERAGE = int(os.getenv("LEVERAGE", "10"))
    ENTRY_ORDER_MAX_AGE = int(os.getenv("ENTRY_ORDER_MAX_AGE", "1800"))
    MIN_VOLUME_24H = float(os.getenv("MIN_VOLUME_24H", "500000"))
    EARLY_EXIT_VOL_MULT = float(os.getenv("EARLY_EXIT_VOL_MULT", "1.8"))
    EARLY_EXIT_LOOKBACK_MINUTES = int(os.getenv("EARLY_EXIT_LOOKBACK_MINUTES", "20"))
    MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES", "5"))
    SAME_SYMBOL_ONLY = os.getenv("SAME_SYMBOL_ONLY", "false").lower() == "true"
    SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "15"))
    USE_TELEGRAM = os.getenv("USE_TELEGRAM", "false").lower() == "true"
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    PNL_START_TIME = 1781567203307 # Timestamp to zero-out past PNL
    
    # BTC Volatility Block Parameters
    BTC_VOLATILITY_BLOCK_DURATION = int(os.getenv("BTC_VOLATILITY_BLOCK_DURATION", "7200"))  # 2 hours in seconds
    BTC_VOL_CUMUL_BODY_PCT = float(os.getenv("BTC_VOL_CUMUL_BODY_PCT", "1.5"))
    BTC_VOL_CUMUL_RANGE_PCT = float(os.getenv("BTC_VOL_CUMUL_RANGE_PCT", "1.5"))
    
    # Cooldown
    COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "45"))
    
    # v2.0 Specifications
    HARD_SL_USDT = float(os.getenv("HARD_SL_USDT", "5.0"))
    EARLY_CUT_TIME_MINS = int(os.getenv("EARLY_CUT_TIME_MINS", "120"))
    EARLY_CUT_LOSS_PCT = float(os.getenv("EARLY_CUT_LOSS_PCT", "0.40"))
    BREAKEVEN_ACTIVATION_PCT = float(os.getenv("BREAKEVEN_ACTIVATION_PCT", "0.40"))
    BREAKEVEN_LOCK_PCT = float(os.getenv("BREAKEVEN_LOCK_PCT", "0.15"))
    TRAILING_ACTIVATION_PCT = float(os.getenv("TRAILING_ACTIVATION_PCT", "0.70"))
    TRAILING_DISTANCE_PCT = float(os.getenv("TRAILING_DISTANCE_PCT", "1.0"))
    
    # Base URLs - Dynamic based on DEMO_MODE
    DEMO_MODE = os.getenv("BYBIT_DEMO", os.getenv("DEMO_MODE", "true")).lower() == "true"
    REST_URL = "https://api-demo.bybit.com" if DEMO_MODE else "https://api.bybit.com"
    WS_URL = "wss://stream.bybit.com/v5/public/linear"
    WS_PRIVATE_URL = "wss://stream-demo.bybit.com/v5/private" if DEMO_MODE else "wss://stream.bybit.com/v5/private"
    
    # Paths
    STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")

os.makedirs(Config.STORAGE_DIR, exist_ok=True)
