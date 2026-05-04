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

        # 2. Buscar si hubo un cruce en las últimas 5 velas cerradas
        # Miramos desde iloc[-6] hasta iloc[-2]
        crossover_long = False
        crossover_short = False
        
        for i in range(-6, -1):
            prev_v = df.iloc[i-1]
            curr_v = df.iloc[i]
            
            if prev_v['ema_fast'] <= prev_v['ema_slow'] and curr_v['ema_fast'] > curr_v['ema_slow']:
                crossover_long = True
            if prev_v['ema_fast'] >= prev_v['ema_slow'] and curr_v['ema_fast'] < curr_v['ema_slow']:
                crossover_short = True

        # 3. Datos actuales para validación de precio
        last_closed = df.iloc[-2]
        current_price = df.iloc[-1]['close']

        # 🟢 COMPRA (LONG)
        # Si hubo cruce reciente Y el precio sigue por encima de las medias
        if crossover_long and current_price > last_closed['ema_fast']:
            entry_price = current_price
            recent_low = df.iloc[-10:-1]['low'].min()
            sl_price = recent_low * 0.9992 # SL un poco más holgado
            
            risk = entry_price - sl_price
            if risk <= 0: return None
            
            tp_price = entry_price + (risk * 2.0)
            logger.info(f"🔥 [EMA] SEÑAL LONG DETECTADA (Cruce reciente) en {symbol}")
            return self._build_signal(symbol, "LONG", entry_price, sl_price, tp_price)

        # 🔴 VENTA (SHORT)
        if crossover_short and current_price < last_closed['ema_fast']:
            entry_price = current_price
            recent_high = df.iloc[-10:-1]['high'].max()
            sl_price = recent_high * 1.0008
            
            risk = sl_price - entry_price
            if risk <= 0: return None
            
            tp_price = entry_price - (risk * 2.0)
            logger.info(f"🔥 [EMA] SEÑAL SHORT DETECTADA (Cruce reciente) en {symbol}")
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
