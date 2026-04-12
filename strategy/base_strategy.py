import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant Ultra V9.2: Precision Plus (SMC + Trend + RSI + ADX + Vol).
    Especializada en Liquidity Sweeps, FVGs y Pullbacks con filtrado de ruido institucional.
    
    Lógica V9.2 (Precision Plus):
    1. Filtro de Bias (15m): Solo opera a favor de la tendencia (EMA 100).
    2. Filtro ADX (1m): Solo opera si ADX > 20 (Mercado con fuerza).
    3. Filtro Volumen (1m): Vela de entrada > 1.5x promedio de 10 velas.
    4. SMC mejorado: Lookback de 50 velas para Liquidity Sweeps.
    5. Gestión RSI: Long si RSI < 55, Short si RSI > 45.
    """

    def __init__(self):
        self.ema_bias_period = 100
        self.ema_short_period = 20
        self.atr_period = 14
        self.atr_sl_multiplier = 2.2
        self.atr_tp_multiplier = self.atr_sl_multiplier * 2.0  # Relación 1:2
        self.rsi_period = 14
        self.adx_period = 14

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
            
            # ADX para fuerza de tendencia
            adx_obj = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=self.adx_period)
            df['adx'] = adx_obj.adx()
            
            # Volumen Promedio
            df['vol_avg'] = df['volume'].rolling(window=10).mean()
            
        except Exception as e:
            logger.error(f"Error en indicadores V9.2 para {symbol}: {e}")
            return None

        # Datos actuales 1m
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        atr = curr['atr']
        price = curr['close']
        ema_20 = curr['ema_20']
        rsi = curr['rsi']
        adx = curr['adx']
        vol = curr['volume']
        vol_avg = curr['vol_avg']
        
        # --- FILTROS DE PRECISIÓN V9.2 ---
        if adx < 20: 
            return None # Mercado sin fuerza (Rango/Choppy)
            
        if vol < (vol_avg * 1.5):
            return None # Sin volumen institucional suficiente

        signal = None
        sl_price = None
        tp_price = None
        reason = ""

        # --- Lógica SMC LONG (Precision V9.2) ---
        if bias == "LONG":
            # Filtro RSI: Evitar comprar si está sobre el 55% del RSI
            if rsi > 55: return None

            # SMC: Liquidity Sweep (Lookback extendido a 50)
            range_low = df.iloc[-50:-6]['low'].min()
            recent_lows = df.iloc[-6:-1]['low']
            sweep_detected = any(recent_lows < range_low) and prev['close'] > range_low
            
            # FVG Alcista (Displacement)
            fvg_detected = curr['low'] > prev2['high']

            if sweep_detected and fvg_detected:
                signal = "LONG"
                reason = "SMC Sweep+FVG"
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_tp_multiplier)
            
            # Trend Pullback (EMA 20)
            elif price > ema_20 and prev['low'] <= ema_20 and curr['close'] > ema_20:
                signal = "LONG"
                reason = "Trend Pullback (EMA 20)"
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_tp_multiplier)

        # --- Lógica SMC SHORT (Precision V9.2) ---
        elif bias == "SHORT":
            # Filtro RSI: Evitar vender si está bajo el 45% del RSI
            if rsi < 45: return None

            # SMC: Liquidity Sweep (Lookback extendido a 50)
            range_high = df.iloc[-50:-6]['high'].max()
            recent_highs = df.iloc[-6:-1]['high']
            sweep_detected = any(recent_highs > range_high) and prev['close'] < range_high
            
            # FVG Bajista (Displacement)
            fvg_detected = curr['high'] < prev2['low']

            if sweep_detected and fvg_detected:
                signal = "SHORT"
                reason = "SMC Sweep+FVG"
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_tp_multiplier)
                
            # Trend Pullback
            elif price < ema_20 and prev['high'] >= ema_20 and curr['close'] < ema_20:
                signal = "SHORT"
                reason = "Trend Pullback (EMA 20)"
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_tp_multiplier)

        if signal:
            # Filtro de rentabilidad mínima
            potential_gain = abs(price - tp_price) / price
            if potential_gain < 0.0015: # 0.15% mínimo
                return None

            logger.info(f"🎯 [V9.2-Precision+] Señal {signal} en {symbol} | ADX: {adx:.1f} | Vol: {vol/vol_avg:.1f}x")
            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": price,
                "sl": sl_price,
                "tp": tp_price,
                "bias": bias,
                "reason": f"{reason} (ADX {adx:.0f}, Vol {vol/vol_avg:.1f}x)",
                "rsi": rsi
            }

        return None

strategy = HyperQuantStrategy()
