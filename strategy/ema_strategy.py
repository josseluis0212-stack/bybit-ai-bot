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
        df['ema_fast'] = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_period, adjust=False).mean()

        # Analizar basándose en la última vela CERRADA (iloc[-2])
        # La vela iloc[-1] es la que está en formación
        curr = df.iloc[-2] 
        prev = df.iloc[-3]

        # 🟢 COMPRA (LONG)
        long_cross = (prev['ema_fast'] <= prev['ema_slow']) and (curr['ema_fast'] > curr['ema_slow'])
        price_above = (curr['close'] > curr['ema_fast'])

        if long_cross and price_above:
            entry_price = df.iloc[-1]['close'] # Entrar al precio actual
            recent_low = df.iloc[-5:-1]['low'].min()
            sl_price = recent_low * 0.9995
            
            risk = entry_price - sl_price
            if risk <= 0: return None
            
            tp_price = entry_price + (risk * 2.0)
            return self._build_signal(symbol, "LONG", entry_price, sl_price, tp_price)

        # 🔴 VENTA (SHORT)
        short_cross = (prev['ema_fast'] >= prev['ema_slow']) and (curr['ema_fast'] < curr['ema_slow'])
        price_below = (curr['close'] < curr['ema_fast'])

        if short_cross and price_below:
            entry_price = df.iloc[-1]['close']
            recent_high = df.iloc[-5:-1]['high'].max()
            sl_price = recent_high * 1.0005
            
            risk = sl_price - entry_price
            if risk <= 0: return None
            
            tp_price = entry_price - (risk * 2.0)
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
