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
        
        return df

    def analyze_symbol(self, symbol, df: pd.DataFrame):
        """
        Analiza un símbolo con lógica SMC y filtros profesionales.
        """
        if len(df) < 110: return None
        
        df = self.calculate_indicators(df)
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        price = float(curr["close"])
        ema_50 = float(curr["ema_50"])
        ema_100 = float(curr["ema_100"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])
        
        if pd.isna(ema_100) or pd.isna(rsi) or pd.isna(atr): return None

        # SESGO (HTF Confluence)
        bias = "LONG" if price > ema_100 else "SHORT"
        
        # Volumen Relativo
        vol_avg = df["volume"].rolling(20).mean().iloc[-1]
        vol_ratio = float(curr["volume"]) / vol_avg if vol_avg > 0 else 1.0

        if bias == "LONG":
            # Filtro RSI: Evitar sobrecompra extrema
            if rsi > 70: return None
            
            # SMC Entry: Sweep de Liquidez (Buscar mínimo barrido)
            recent_lows = df["low"].iloc[-15:-1].min()
            sweep = curr["low"] < recent_lows and curr["close"] > recent_lows
            
            # FVG (Fair Value Gap)
            fvg = curr["low"] > prev2["high"]
            
            if sweep or fvg:
                sl = price - (atr * 2.2)
                tp = price + (atr * 4.4)
                
                # MODO PROFIT INFINITO (V9.1): Si volumen > 1.5x promedio
                if vol_ratio > 1.5:
                    tp = None
                    logger.info(f"🚀 {symbol} MODO PROFIT INFINITO (Vol: {vol_ratio:.1f}x)")

                return {
                    "symbol": symbol, "signal": "LONG", "entry_price": price,
                    "sl": sl, "tp": tp, "atr": atr,
                    "info": f"SMC LONG | RSI:{rsi:.1f} | Vol:{vol_ratio:.1f}"
                }

        else: # SHORT
            # Filtro RSI: Evitar sobreventa extrema
            if rsi < 30: return None
            
            # SMC Entry: Sweep de Liquidez (Buscar máximo barrido)
            recent_highs = df["high"].iloc[-15:-1].max()
            sweep = curr["high"] > recent_highs and curr["close"] < recent_highs
            
            # FVG (Fair Value Gap)
            fvg = curr["high"] < prev2["low"]

            if sweep or fvg:
                sl = price + (atr * 2.2)
                tp = price - (atr * 4.4)
                
                # MODO PROFIT INFINITO
                if vol_ratio > 1.5:
                    tp = None
                    logger.info(f"🚀 {symbol} MODO PROFIT INFINITO (Vol: {vol_ratio:.1f}x)")

                return {
                    "symbol": symbol, "signal": "SHORT", "entry_price": price,
                    "sl": sl, "tp": tp, "atr": atr,
                    "info": f"SMC SHORT | RSI:{rsi:.1f} | Vol:{vol_ratio:.1f}"
                }

        return None
