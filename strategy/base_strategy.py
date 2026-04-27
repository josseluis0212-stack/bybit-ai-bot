import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

logger = logging.getLogger(__name__)

class BaseStrategy:
    def __init__(self, name="Institutional SMC Quantum v5.1"):
        self.name = name

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.copy()
        
        # Medias (Using 'ta' library)
        df["ema_50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
        
        # RSI y ATR
        df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi()
        df["atr"] = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range()
        
        # Filtro de Volatilidad Relativa
        df["atr_sma_50"] = df["atr"].rolling(50).mean()
        
        # Detección de Order Blocks (OB)
        df['bullish_ob'] = np.where((df['close'] < df['open']) & (df['close'].shift(-1) > df['open'].shift(-1)), df['low'], np.nan)
        df['bullish_ob'] = df['bullish_ob'].ffill()
        
        df['bearish_ob'] = np.where((df['close'] > df['open']) & (df['close'].shift(-1) < df['open'].shift(-1)), df['high'], np.nan)
        df['bearish_ob'] = df['bearish_ob'].ffill()

        return df

    def analyze_symbol(self, symbol, df: pd.DataFrame, htf_bias=None):
        """
        Analiza un símbolo con lógica SMC v5.1 e integración de Bias HTF (15m).
        """
        if len(df) < 50: return None
        
        df = self.calculate_indicators(df)
        curr = df.iloc[-1]
        prev2 = df.iloc[-3]
        
        price = float(curr["close"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])
        atr_avg = float(curr["atr_sma_50"])
        
        if pd.isna(atr) or pd.isna(atr_avg): return None

        # 1. FILTRO DE VOLATILIDAD (ATR > Promedio 50 velas)
        if atr < (atr_avg * 0.9): return None

        # 2. SESGO HTF (Integración de MarketScanner)
        bias = htf_bias if htf_bias else ("LONG" if price > float(curr["ema_50"]) else "SHORT")
        
        # 3. FILTRO DE VOLUMEN
        vol_avg = df["volume"].rolling(20).mean().iloc[-1]
        vol_ratio = float(curr["volume"]) / vol_avg if vol_avg > 0 else 1.0

        # Multiplicadores ATR (Dashboard: 3.0 / 6.0)
        atr_sl_mult = 3.0
        atr_tp_mult = 6.0

        if bias == "LONG":
            # Filtro de Fatiga RSI (Dashboard: 35-65)
            if rsi > 65: return None
            
            # Liquidity Sweep
            recent_lows = df["low"].iloc[-15:-1].min()
            sweep = curr["low"] < recent_lows and curr["close"] > recent_lows
            
            # FVG (Fair Value Gap)
            fvg = curr["low"] > prev2["high"]
            
            # Mitigación de OB
            ob_mitigation = not pd.isna(curr['bullish_ob']) and curr['low'] <= curr['bullish_ob'] and curr['close'] > curr['bullish_ob']

            if sweep or fvg or ob_mitigation:
                sl = price - (atr * atr_sl_mult)
                tp = price + (atr * atr_tp_mult)
                
                if (tp - price) / price < 0.0025: return None
                if vol_ratio > 1.8: tp = None

                return {
                    "symbol": symbol, "signal": "LONG", "entry_price": price,
                    "sl": sl, "tp": tp, "atr": atr,
                    "info": f"SMC v5.1 LONG | RSI:{rsi:.1f} | HTF:{bias}"
                }

        else: # SHORT
            if rsi < 35: return None
            
            recent_highs = df["high"].iloc[-15:-1].max()
            sweep = curr["high"] > recent_highs and curr["close"] < recent_highs
            fvg = curr["high"] < prev2["low"]
            ob_mitigation = not pd.isna(curr['bearish_ob']) and curr['high'] >= curr['bearish_ob'] and curr['close'] < curr['bearish_ob']

            if sweep or fvg or ob_mitigation:
                sl = price + (atr * atr_sl_mult)
                tp = price - (atr * atr_tp_mult)
                
                if (price - tp) / price < 0.0025: return None
                if vol_ratio > 1.8: tp = None

                return {
                    "symbol": symbol, "signal": "SHORT", "entry_price": price,
                    "sl": sl, "tp": tp, "atr": atr,
                    "info": f"SMC v5.1 SHORT | RSI:{rsi:.1f} | HTF:{bias}"
                }

        return None

strategy = BaseStrategy()
