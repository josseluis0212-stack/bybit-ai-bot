import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant Ultra V9.4 (Triple-Check Dynamic): 15m Bias + 1m EMA50 Alignment + 1m ADX Force.
    Implementa un sistema de 3 niveles de confirmación y Take Profit inteligente.
    """

    def __init__(self):
        self.ema_bias_period = 100
        self.ema_target_period = 50 # Nuevo verificador de micro-tendencia
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
            # 1. NIVEL 1: Marco HTF (15m) - Bias Estructural
            df_htf['ema_bias'] = ta.trend.ema_indicator(df_htf['close'], window=self.ema_bias_period)
            df_htf['rsi_htf'] = ta.momentum.rsi(df_htf['close'], window=self.rsi_period)
            
            htf_price = df_htf.iloc[-1]['close']
            htf_ema = df_htf.iloc[-1]['ema_bias']
            htf_rsi = df_htf.iloc[-1]['rsi_htf']
            bias = "LONG" if htf_price > htf_ema else "SHORT"

            # 2. NIVEL 2: Marco ejecución (1m) - Alineación de Micro-Tendencia
            df['ema_50'] = ta.trend.ema_indicator(df['close'], window=self.ema_target_period)
            df['ema_20'] = ta.trend.ema_indicator(df['close'], window=self.ema_short_period)
            
            # 3. NIVEL 3: Marco ejecución (1m) - Fuerza e Inercia (ADX)
            df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
            df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_period)
            df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
            
        except Exception as e:
            logger.error(f"Error en indicadores V9.4 Triple-Check para {symbol}: {e}")
            return None

        # Datos actuales 1m
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        price = curr['close']
        ema_50 = curr['ema_50']
        ema_20 = curr['ema_20']
        adx = curr['adx']
        rsi = curr['rsi']
        atr = curr['atr']
        
        # FILTRO DE FUERZA MÍNIMA: ADX > 18
        if adx < 18:
            return None

        # Definir el multiplicador del TP según la fuerza (Dynamic TP)
        # ADX > 25 (Fuerte) -> RR 1:2
        # ADX 18-25 (Moderado/Dudoso) -> RR 1:1.5
        rr_ratio = 2.0 if adx > 25 else 1.5
        
        signal = None
        sl_price = None
        tp_price = None
        reason = ""

        # --- Lógica LONG (Triple-Check) ---
        if bias == "LONG":
            # Filtros de agotamiento
            if htf_rsi > 75 or rsi > 60: return None
            # Verificador Micro-Trend: Precio debe estar sobre la EMA 50
            if price < ema_50: return None

            # A. SMC Sweep (Institutional)
            range_low = df.iloc[-15:-6]['low'].min()
            recent_lows = df.iloc[-6:-1]['low']
            sweep_detected = any(recent_lows < range_low) and prev['close'] > range_low
            fvg_detected = curr['low'] > prev2['high']

            if sweep_detected and fvg_detected:
                signal = "LONG"
                reason = "SMC Sweep+FVG"
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_sl_multiplier * rr_ratio)
            
            # B. Trend Pullback (EMA 20)
            elif price > ema_20 and prev['low'] <= ema_20 and curr['close'] > ema_20:
                signal = "LONG"
                reason = "Pullback EMA 20"
                sl_price = price - (atr * self.atr_sl_multiplier)
                tp_price = price + (atr * self.atr_sl_multiplier * rr_ratio)

        # --- Lógica SHORT (Triple-Check) ---
        elif bias == "SHORT":
            # Filtros de agotamiento
            if htf_rsi < 25 or rsi < 40: return None
            # Verificador Micro-Trend: Precio debe estar bajo la EMA 50
            if price > ema_50: return None

            # A. SMC Sweep (Institutional)
            range_high = df.iloc[-15:-6]['high'].max()
            recent_highs = df.iloc[-6:-1]['high']
            sweep_detected = any(recent_highs > range_high) and prev['close'] < range_high
            fvg_detected = curr['high'] < prev2['low']

            if sweep_detected and fvg_detected:
                signal = "SHORT"
                reason = "SMC Sweep+FVG"
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_sl_multiplier * rr_ratio)
                
            # B. Trend Pullback
            elif price < ema_20 and prev['high'] >= ema_20 and curr['close'] < ema_20:
                signal = "SHORT"
                reason = "Pullback EMA 20"
                sl_price = price + (atr * self.atr_sl_multiplier)
                tp_price = price - (atr * self.atr_sl_multiplier * rr_ratio)

        if signal:
            potential_gain = abs(price - tp_price) / price
            if potential_gain < 0.0012: # 0.12% mínimo
                return None

            logger.info(f"🎯 [V9.4] Señal {signal} en {symbol} | ADX: {adx:.1f} | RR 1:{rr_ratio}")
            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": price,
                "sl": sl_price,
                "tp": tp_price,
                "bias": bias,
                "reason": f"{reason} (ADX {adx:.0f}, RR 1:{rr_ratio})",
                "rsi": rsi,
                "adx": adx
            }

        return None

strategy = HyperQuantStrategy()
