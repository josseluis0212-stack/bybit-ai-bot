import pandas as pd
import numpy as np
import logging
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
from config.settings import settings

logger = logging.getLogger(__name__)

class BaseStrategy:
    def __init__(self, name="HYPER SCALPER QUANT V1"):
        self.name = name

    def analyze_symbol(self, symbol, df_ltf: pd.DataFrame, df_htf: pd.DataFrame):
        """
        Analiza el mercado con la lógica Hyper Scalper V1.
        """
        if len(df_ltf) < 50 or len(df_htf) < 100: return None
        
        # --- HTF ANALYSIS (15m) ---
        df_htf = df_htf.copy()
        df_htf["ema_100"] = EMAIndicator(close=df_htf["close"], window=100).ema_indicator()
        
        htf_curr = df_htf.iloc[-1]
        ema_100_htf = float(htf_curr["ema_100"])
        htf_close = float(htf_curr["close"])
        
        if pd.isna(ema_100_htf): return None
        
        bias = "LONG" if htf_close > ema_100_htf else "SHORT"
        
        # --- LTF ANALYSIS (1m) ---
        df = df_ltf.copy()
        df["ema_20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
        df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi()
        df["atr"] = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=settings.ATR_PERIOD).average_true_range()
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        price = float(curr["close"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])
        ema_20 = float(curr["ema_20"])
        
        if pd.isna(rsi) or pd.isna(atr) or pd.isna(ema_20): return None
        
        # Filtro de Volumen Promedio (1m)
        vol_avg = df["volume"].rolling(20).mean().iloc[-1]
        vol_ratio = float(curr["volume"]) / vol_avg if vol_avg > 0 else 1.0

        # --- CONDITIONS ---
        is_signal = False
        signal_type = ""
        
        if bias == "LONG":
            # 1. Filtro RSI
            if rsi > 65: return None
            
            # 2. Toque o cruce de EMA 20
            # Pullback a la EMA 20 (El mínimo debe haber tocado o estar muy cerca de la EMA)
            touched_ema = curr["low"] <= ema_20 and curr["close"] > ema_20
            if not touched_ema:
                touched_ema = prev["low"] <= prev["ema_20"] and curr["close"] > ema_20
            
            if not touched_ema: return None
            
            # 3. Confirmación SMC
            # a) Liquidity Sweep (Mínimo de las últimas 15 velas barrido)
            recent_lows = df["low"].iloc[-16:-1].min()
            sweep = curr["low"] < recent_lows and curr["close"] > recent_lows
            
            # b) FVG (Fair Value Gap)
            fvg = curr["low"] > prev2["high"]
            
            if sweep or fvg:
                is_signal = True
                signal_type = "LONG"
                
        elif bias == "SHORT":
            # 1. Filtro RSI
            if rsi < 35: return None
            
            # 2. Toque o cruce de EMA 20
            touched_ema = curr["high"] >= ema_20 and curr["close"] < ema_20
            if not touched_ema:
                touched_ema = prev["high"] >= prev["ema_20"] and curr["close"] < ema_20
                
            if not touched_ema: return None
            
            # 3. Confirmación SMC
            recent_highs = df["high"].iloc[-16:-1].max()
            sweep = curr["high"] > recent_highs and curr["close"] < recent_highs
            
            fvg = curr["high"] < prev2["low"]
            
            if sweep or fvg:
                is_signal = True
                signal_type = "SHORT"

        if is_signal:
            sl_dist = atr * settings.ATR_MULTIPLIER_SL
            tp_dist = atr * settings.ATR_MULTIPLIER_TP
            
            if signal_type == "LONG":
                sl = price - sl_dist
                tp = price + tp_dist
            else:
                sl = price + sl_dist
                tp = price - tp_dist
                
            # Excepción de Volumen (Modo Profit Infinito)
            if vol_ratio > 1.5:
                tp = None
                
            return {
                "symbol": symbol,
                "signal": signal_type,
                "entry_price": price,
                "sl": sl,
                "tp": tp,
                "atr": atr,
                "info": f"HyperScalper V1 | Vol:{vol_ratio:.1f}x | RSI:{rsi:.1f}"
            }
            
        return None

strategy = BaseStrategy()
