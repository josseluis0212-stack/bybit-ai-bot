import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant Ultra V9: SMC Standard Scalper (SMC + Trend).
    Especializada en Liquidity Sweeps, FVGs y Pullbacks.
    
    Lógica V9 (Standard):
    1. Filtro de Bias (15m): Solo opera a favor de la tendencia (EMA 100).
    2. Liquidity Sweep (1m): Detecta sacudidas institucionales.
    3. FVG / Displacement: Identifica desequilibrios de mercado.
    4. Gestión de Riesgo: SL 2.0x ATR y TP relación 1:2 (4.0x ATR).
    """

    def __init__(self):
        self.ema_bias_period = 100
        self.ema_short_period = 20
        self.atr_period = 14
        self.atr_sl_multiplier = 2.0
        self.atr_tp_multiplier = self.atr_sl_multiplier * 2.0  # Relación 1:2

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame):
        if len(df) < 50 or len(df_htf) < self.ema_bias_period:
            return None

        # Asegurar tipos numéricos
        for d in [df, df_htf]:
            for col in ['open', 'high', 'low', 'close', 'volume']:
                d[col] = pd.to_numeric(d[col], errors='coerce')

        try:
            # 1. Calcular Bias en HTF (15m)
            df_htf['ema_bias'] = ta.trend.ema_indicator(df_htf['close'], window=self.ema_bias_period)
            htf_price = df_htf.iloc[-1]['close']
            htf_ema = df_htf.iloc[-1]['ema_bias']
            bias = "LONG" if htf_price > htf_ema else "SHORT"

            # 2. Indicadores en 1m
            df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_period)
            df['ema_20'] = ta.trend.ema_indicator(df['close'], window=self.ema_short_period)
            
        except Exception as e:
            logger.error(f"Error en indicadores V9.1 para {symbol}: {e}")
            return None

        # Datos actuales 1m
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        atr = curr['atr']
        price = curr['close']
        ema_20 = curr['ema_20']
        
        signal = None
        sl_price = None
        tp_price = None
        reason = ""

        # --- Lógica SMC LONG (V9 Standard) ---
        if bias == "LONG":

            # SMC: Liquidity Sweep
            range_low = df.iloc[-15:-6]['low'].min()
            recent_lows = df.iloc[-6:-1]['low']
            sweep_detected = any(recent_lows < range_low) and prev['close'] > range_low
            
            # FVG Alcista
            fvg_detected = curr['low'] > prev2['high']

            if sweep_detected and fvg_detected:
                signal = "LONG"
                reason = "SMC (Sweep+FVG)"
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_tp_multiplier)
            
            # Trend Pullback (EMA 20)
            elif price > ema_20 and prev['low'] <= ema_20 and curr['close'] > ema_20:
                signal = "LONG"
                reason = "Trend Pullback (EMA 20)"
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_tp_multiplier)

        # --- Lógica SMC SHORT (V9 Standard) ---
        elif bias == "SHORT":

            # SMC: Liquidity Sweep
            range_high = df.iloc[-15:-6]['high'].max()
            recent_highs = df.iloc[-6:-1]['high']
            sweep_detected = any(recent_highs > range_high) and prev['close'] < range_high
            
            # FVG Bajista
            fvg_detected = curr['high'] < prev2['low']

            if sweep_detected and fvg_detected:
                signal = "SHORT"
                reason = "SMC (Sweep+FVG)"
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_tp_multiplier)
                
            # B. Secondary: Trend Pullback
            elif price < ema_20 and prev['high'] >= ema_20 and curr['close'] < ema_20:
                signal = "SHORT"
                reason = "Trend Pullback (EMA 20)"
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_tp_multiplier)

        if signal:
            logger.info(f"🎯 [V9-Standard] Señal {signal} en {symbol}")
            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": price,
                "sl": sl_price,
                "tp": tp_price,
                "bias": bias,
                "reason": reason
            }

        return None

strategy = HyperQuantStrategy()
