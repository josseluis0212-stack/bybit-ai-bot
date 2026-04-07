import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant Ultra V9.0: Precision Scalper (SMC + Trend + RSI).
    Especializada en Liquidity Sweeps, FVGs y Pullbacks con gestión de ruido mejorada.
    
    Lógica V9.0 (Precision):
    1. Filtro de Bias (15m): Solo opera a favor de la tendencia (EMA 100).
    2. Filtro RSI (1m): Evita compras en sobrecompra (>65) y ventas en sobreventa (<35).
    3. Liquidity Sweep (1m): Detecta sacudidas institucionales.
    4. FVG / Displacement: Identifica desequilibrios de mercado.
    5. Gestión de Riesgo: SL amplio (2.2x ATR) y TP conservador (1.5x ATR) para asegurar beneficios.
    """

    def __init__(self):
        self.ema_bias_period = 100
        self.ema_short_period = 20
        self.atr_period = 14
        self.atr_sl_multiplier = 2.2
        self.atr_tp_multiplier = 1.5
        self.rsi_period = 14

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
            df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
            
        except Exception as e:
            logger.error(f"Error en indicadores V9 para {symbol}: {e}")
            return None

        # Datos actuales 1m
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        atr = curr['atr']
        price = curr['close']
        ema_20 = curr['ema_20']
        rsi = curr['rsi']
        
        signal = None
        sl_price = None
        tp_price = None
        reason = ""

        # --- Lógica SMC LONG (Precision V9.0) ---
        if bias == "LONG":
            # Filtro RSI: Evitar comprar si está muy sobrecomprado (>65)
            if rsi > 65: return None

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
                sl_price = price - (atr * 2.0)
                tp_price = price + (atr * 1.5)

        # --- Lógica SMC SHORT (Precision V9.0) ---
        elif bias == "SHORT":
            # Filtro RSI: Evitar vender si está muy sobrevendido (<35)
            if rsi < 35: return None

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
                sl_price = price + (atr * 2.0)
                tp_price = price - (atr * 1.5)

        if signal:
            # Filtro de rentabilidad mínima
            potential_gain = abs(price - tp_price) / price
            if potential_gain < 0.0015: # 0.15% mínimo
                return None

            logger.info(f"🎯 [V9-Precision] Señal {signal} en {symbol} | RSI: {rsi:.1f}")
            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": price,
                "sl": sl_price,
                "tp": tp_price,
                "bias": bias,
                "reason": f"{reason} (RSI {rsi:.0f})",
                "rsi": rsi
            }

        return None

strategy = HyperQuantStrategy()
