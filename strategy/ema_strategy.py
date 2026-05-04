"""
Estrategia EMA Crossover (EMA 9 / EMA 21)
Reglas:
1. LONG: EMA 9 cruza hacia arriba EMA 21 + Precio > ambas EMAs.
2. SHORT: EMA 9 cruza hacia abajo EMA 21 + Precio < ambas EMAs.
3. SL: Mínimo/Máximo reciente (3 velas).
4. TP: 2:1 Riesgo/Recompensa.
"""
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

class EMAStrategy:
    def __init__(self, fast_period=9, slow_period=21):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.consecutive_losses = 0
        self.blocked = False

    def analyze(self, df: pd.DataFrame, symbol: str) -> dict | None:
        if len(df) < self.slow_period + 5:
            return None

        df = df.copy()
        
        # Calcular EMAs
        # 1. Calcular EMAs
        df['ema_fast'] = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_period, adjust=False).mean()

        # 2. Detectar si las medias están cruzadas (Filtro de Tendencia)
        curr = df.iloc[-1]
        last_closed = df.iloc[-2]
        is_uptrend = curr['ema_fast'] > curr['ema_slow']
        is_downtrend = curr['ema_fast'] < curr['ema_slow']

        # Log para las monedas principales (opcional, solo debug interno)
        if symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            logger.info(f"📊 [{symbol}] EMA9: {curr['ema_fast']:.2f} | EMA21: {curr['ema_slow']:.2f} | Tendencia: {'UP' if is_uptrend else 'DOWN'}")

        # 3. Detectar cruce reciente (en las últimas 10 velas para ser muy agresivos)
        recent_cross_up = False
        recent_cross_down = False
        for i in range(-11, -1):
            if df.iloc[i-1]['ema_fast'] <= df.iloc[i-1]['ema_slow'] and df.iloc[i]['ema_fast'] > df.iloc[i]['ema_slow']:
                recent_cross_up = True
            if df.iloc[i-1]['ema_fast'] >= df.iloc[i-1]['ema_slow'] and df.iloc[i]['ema_fast'] < df.iloc[i]['ema_slow']:
                recent_cross_down = True

        # 🟢 ENTRADA LONG
        if is_uptrend and recent_cross_up:
            # Filtro de distancia (no entrar si ya se voló demasiado)
            dist_ema = (curr['close'] - curr['ema_fast']) / curr['ema_fast']
            if dist_ema > 0.02: return None 

            entry_price = curr['close']
            sl_price = df.iloc[-15:-1]['low'].min() * 0.9985
            if entry_price <= sl_price: return None
            tp_price = entry_price + (entry_price - sl_price) * 1.5
            logger.info(f"💰 [OPORTUNIDAD] LONG en {symbol} | Precio: {entry_price}")
            return self._build_signal(symbol, "LONG", entry_price, sl_price, tp_price)

        # 🔴 ENTRADA SHORT
        if is_downtrend and recent_cross_down:
            dist_ema = (curr['ema_fast'] - curr['close']) / curr['ema_fast']
            if dist_ema > 0.02: return None

            entry_price = curr['close']
            sl_price = df.iloc[-15:-1]['high'].max() * 1.0015
            if entry_price >= sl_price: return None
            tp_price = entry_price - (sl_price - entry_price) * 1.5
            logger.info(f"💰 [OPORTUNIDAD] SHORT en {symbol} | Precio: {entry_price}")
            return self._build_signal(symbol, "SHORT", entry_price, sl_price, tp_price)

        return None

    def _build_signal(self, symbol, side, entry, sl, tp):
        return {
            "symbol": symbol,
            "signal": side,
            "entry_price": entry,
            "sl": sl,
            "tp1": tp,
            "tp2": tp,
            "tp3": tp,
            "tp1_pct": 1.0,
            "tp2_pct": 0.0,
            "tp3_pct": 0.0,
            "breakeven_r": 1.0,
            "sl_distance": abs(entry - sl) / entry,
            "strategy": "EMA_CROSS_9_21",
        }

ema_strategy = EMAStrategy()
