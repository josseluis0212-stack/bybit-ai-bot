import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant Ultra V9.3 (Dynamic Scalper): Intelligent Take Profit based on signals.
    Implementa un ratio 1:2 para movimientos institucionales y 1:1.5 para pullbacks rápidos.
    """

    def __init__(self):
        self.ema_bias_period = 100
        self.ema_short_period = 20
        self.atr_period = 14
        self.atr_sl_multiplier = 2.2 # Riesgo base
        self.rsi_period = 14

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame):
        if len(df) < 50 or len(df_htf) < self.ema_bias_period:
            return None

        # Asegurar tipos numéricos
        for d in [df, df_htf]:
            for col in ['open', 'high', 'low', 'close', 'volume']:
                d[col] = pd.to_numeric(d[col], errors='coerce')

        try:
            # 1. Calcular Bias e indicadores en HTF (15m)
            df_htf['ema_bias'] = ta.trend.ema_indicator(df_htf['close'], window=self.ema_bias_period)
            df_htf['rsi_htf'] = ta.momentum.rsi(df_htf['close'], window=self.rsi_period)
            
            htf_price = df_htf.iloc[-1]['close']
            htf_ema = df_htf.iloc[-1]['ema_bias']
            htf_rsi = df_htf.iloc[-1]['rsi_htf']
            bias = "LONG" if htf_price > htf_ema else "SHORT"

            # 2. Indicadores en 1m
            df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_period)
            df['ema_20'] = ta.trend.ema_indicator(df['close'], window=self.ema_short_period)
            df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
            
        except Exception as e:
            logger.error(f"Error en indicadores V9.3 Dynamic para {symbol}: {e}")
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
        rr_ratio = 1.0

        # --- Lógica LONG (Dynamic TP) ---
        if bias == "LONG":
            if htf_rsi > 75 or rsi > 60: return None

            # A. SMC Sweep (Institutional - High RR 1:2)
            range_low = df.iloc[-15:-6]['low'].min()
            recent_lows = df.iloc[-6:-1]['low']
            sweep_detected = any(recent_lows < range_low) and prev['close'] > range_low
            fvg_detected = curr['low'] > prev2['high']

            if sweep_detected and fvg_detected:
                signal = "LONG"
                reason = "SMC Sweep+FVG"
                rr_ratio = 2.0
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_sl_multiplier * rr_ratio)
            
            # B. Trend Pullback (Retail - Conservative RR 1:1.5)
            elif price > ema_20 and prev['low'] <= ema_20 and curr['close'] > ema_20:
                signal = "LONG"
                reason = "Pullback EMA 20"
                rr_ratio = 1.5
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_sl_multiplier * rr_ratio)

        # --- Lógica SHORT (Dynamic TP) ---
        elif bias == "SHORT":
            if htf_rsi < 25 or rsi < 40: return None

            # A. SMC Sweep (Institutional - High RR 1:2)
            range_high = df.iloc[-15:-6]['high'].max()
            recent_highs = df.iloc[-6:-1]['high']
            sweep_detected = any(recent_highs > range_high) and prev['close'] < range_high
            fvg_detected = curr['high'] < prev2['low']

            if sweep_detected and fvg_detected:
                signal = "SHORT"
                reason = "SMC Sweep+FVG"
                rr_ratio = 2.0
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_sl_multiplier * rr_ratio)
                
            # B. Trend Pullback (Retail - Conservative RR 1:1.5)
            elif price < ema_20 and prev['high'] >= ema_20 and curr['close'] < ema_20:
                signal = "SHORT"
                reason = "Pullback EMA 20"
                rr_ratio = 1.5
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_sl_multiplier * rr_ratio)

        if signal:
            potential_gain = abs(price - tp_price) / price
            if potential_gain < 0.0012: # 0.12% mínimo
                return None

            logger.info(f"🎯 [V9.3-DYNAMIC] Señal {signal} en {symbol} | RR 1:{rr_ratio}")
            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": price,
                "sl": sl_price,
                "tp": tp_price,
                "bias": bias,
                "reason": f"{reason} (RR 1:{rr_ratio})",
                "rsi": rsi,
                "htf_rsi": htf_rsi
            }

        return None

strategy = HyperQuantStrategy()
