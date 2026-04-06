import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant Ultra V6.0: Balanced Scalper (SMC + Trend).
    Especializada en Liquidity Sweeps, FVGs y Pullbacks de tendencia.
    
    Lógica V6.0 (Balanced):
    1. Filtro de Bias (15m): Solo opera a favor de la tendencia (EMA 100).
    2. Liquidity Sweep (1m): Detecta sacudidas en los últimos 5 minutos.
    3. FVG / Displacement: Identifica desequilibrios instituciones.
    4. Trend Pullback: Entrada secundaria si el precio corrige a la EMA 20 (1m).
    5. Riesgo: 1.5x ATR para SL, 2.5x ATR para TP (Equilibrio Frecuencia/Efectividad).
    """

    def __init__(self):
        self.ema_bias_period = 100
        self.ema_short_period = 20
        self.atr_period = 14
        self.atr_sl_multiplier = 1.5
        self.atr_tp_multiplier = 2.5

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
            logger.error(f"Error en indicadores V6 para {symbol}: {e}")
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

        # --- Lógica SMC LONG (Balanced) ---
        if bias == "LONG":
            # A. SMC: Liquidity Sweep en las últimas 5 velas
            # Buscamos el mínimo de las velas -15 a -6 (rango de liquidez)
            range_low = df.iloc[-15:-6]['low'].min()
            # Si alguna de las últimas 5 velas limpió ese mínimo
            recent_lows = df.iloc[-6:-1]['low']
            sweep_detected = any(recent_lows < range_low) and prev['close'] > range_low
            
            # FVG Alcista (Vela actual > Vela de hace 2 posiciones)
            fvg_detected = curr['low'] > prev2['high']

            if sweep_detected and fvg_detected:
                signal = "LONG"
                reason = "SMC (Sweep+FVG)"
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_tp_multiplier)
            
            # B. Secondary: Trend Pullback (Ema 20)
            elif price > ema_20 and prev['low'] <= ema_20 and curr['close'] > ema_20:
                signal = "LONG"
                reason = "Trend Pullback (EMA 20)"
                sl_price = price - (atr * 1.8) # SL un poco más amplio para pullbacks
                tp_price = price + (atr * 2.2)

        # --- Lógica SMC SHORT (Balanced) ---
        elif bias == "SHORT":
            # A. SMC: Liquidity Sweep
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
                sl_price = price + (atr * 1.8)
                tp_price = price - (atr * 2.2)

        if signal:
            # Filtro de rentabilidad mínima
            potential_gain = abs(price - tp_price) / price
            if potential_gain < 0.0020: # 0.20% mínimo para cubrir comisiones y slippage
                return None

            logger.info(f"🎯 [V6-{reason}] Señal {signal} en {symbol} detectada.")
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
