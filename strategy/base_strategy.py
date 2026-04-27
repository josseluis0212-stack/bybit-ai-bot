import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
import pandas_ta as ta

logger = logging.getLogger(__name__)

class BaseStrategy:
    def __init__(self, name="Elite SMC"):
        self.name = name

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df
        df = df.copy()
        
        # Medias Elite
        df["ema_50"] = ta.ema(df["close"], length=50)
        df["ema_100"] = ta.ema(df["close"], length=100)
        
        # RSI y ATR
        df["rsi"] = ta.rsi(df["close"], length=14)
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        
        # Filtro de Volatilidad Relativa (Nuevo)
        df["atr_sma_50"] = df["atr"].rolling(50).mean()
        
        return df

    def analyze_symbol(self, symbol, df: pd.DataFrame):
        """
        Analiza un símbolo con lógica SMC avanzada y filtros de volatilidad.
        """
        if len(df) < 110: return None
        
        df = self.calculate_indicators(df)
        curr = df.iloc[-1]
        prev2 = df.iloc[-3]
        
        price = float(curr["close"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])
        atr_avg = float(curr["atr_sma_50"])
        
        if pd.isna(atr) or pd.isna(atr_avg): return None

        # 1. FILTRO DE VOLATILIDAD RELATIVA (Mejora 3)
        # Solo operar si la volatilidad actual es superior al promedio de 50 velas
        if atr < (atr_avg * 0.9): # Un poco de margen, pero filtrando mercados muertos
            return None

        # SESGO (HTF Confluence)
        ema_100 = float(curr["ema_100"])
        bias = "LONG" if price > ema_100 else "SHORT"
        
        vol_avg = df["volume"].rolling(20).mean().iloc[-1]
        vol_ratio = float(curr["volume"]) / vol_avg if vol_avg > 0 else 1.0

        # Multiplicadores ATR (Mejora 1: 3.0 / 6.0)
        atr_sl_mult = 3.0
        atr_tp_mult = 6.0

        if bias == "LONG":
            if rsi > 70: return None
            
            recent_lows = df["low"].iloc[-15:-1].min()
            sweep = curr["low"] < recent_lows and curr["close"] > recent_lows
            fvg = curr["low"] > prev2["high"]
            
            if sweep or fvg:
                sl = price - (atr * atr_sl_mult)
                tp = price + (atr * atr_tp_mult)
                
                # 2. MOVIMIENTO MÍNIMO PCT (Mejora 1: 0.25%)
                if (tp - price) / price < 0.0025:
                    return None

                if vol_ratio > 1.5:
                    tp = None
                    logger.info(f"🚀 {symbol} MODO PROFIT INFINITO (Vol: {vol_ratio:.1f}x)")

                return {
                    "symbol": symbol, "signal": "LONG", "entry_price": price,
                    "sl": sl, "tp": tp, "atr": atr,
                    "info": f"SMC LONG | RSI:{rsi:.1f} | Vol:{vol_ratio:.1f}"
                }

        else: # SHORT
            if rsi < 30: return None
            
            recent_highs = df["high"].iloc[-15:-1].max()
            sweep = curr["high"] > recent_highs and curr["close"] < recent_highs
            fvg = curr["high"] < prev2["low"]

            if sweep or fvg:
                sl = price + (atr * atr_sl_mult)
                tp = price - (atr * atr_tp_mult)
                
                # 2. MOVIMIENTO MÍNIMO PCT (Mejora 1: 0.25%)
                if (price - tp) / price < 0.0025:
                    return None

                if vol_ratio > 1.5:
                    tp = None
                    logger.info(f"🚀 {symbol} MODO PROFIT INFINITO (Vol: {vol_ratio:.1f}x)")

                return {
                    "symbol": symbol, "signal": "SHORT", "entry_price": price,
                    "sl": sl, "tp": tp, "atr": atr,
                    "info": f"SMC SHORT | RSI:{rsi:.1f} | Vol:{vol_ratio:.1f}"
                }

        return None
