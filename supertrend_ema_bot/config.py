import os

# Exchange Settings
EXCHANGE_ID = os.getenv('EXCHANGE_ID', 'bybit')
API_KEY = os.getenv('API_KEY', '')
API_SECRET = os.getenv('API_SECRET', '')
TESTNET = os.getenv('TESTNET', 'true').lower() == 'true'

# Trading Parameters
SYMBOL = os.getenv('SYMBOL', 'BTC/USDT:USDT') # Use standard ccxt format for linear futures
TIMEFRAME_15M = '15m'
TIMEFRAME_1H = '1h'
TRADE_CAPITAL = 15.0 # 15 USDT per trade

# Indicator Parameters
EMA_TREND_PERIOD = 200
EMA_FAST_PERIOD = 9
EMA_MEDIUM_PERIOD = 21

SUPERTREND_ATR_LENGTH = 10
SUPERTREND_FACTOR = 3.0

ATR_LENGTH = 10

ADX_LENGTH = 14
ADX_MIN = 18

SLOPE_LOOKBACK = 10 # Check slope of EMA200 over last 10 candles
MIN_DISTANCE_TO_EMA200_ATR_MULTIPLIER = 0.3

MAX_SETUP_WINDOW_CANDLES = 160

# Risk Management
STOP_LOSS_ATR_MULTIPLIER = 2.5
BREAKEVEN_TRIGGER_ATR_MULTIPLIER = 2.0
TRAILING_TRIGGER_ATR_MULTIPLIER = 2.5
