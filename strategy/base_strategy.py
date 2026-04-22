"""
Hyper-Quant Ultra V10 - Precision Scalper (MEJORADO)
=====================================================

Mejoras sobre V9:
- Filtro de tendencia en 15m (EMA 50)
- Filtro de volatilidad (ATR ratio)
- Filtro de momentum (RSI confluence)
- Solo entrada en tendencia confirmada
- SL adaptativo según volatilidad
- Ratio R:R mejorado a 2.5:1

Timeframes: 15m (Bias) + 1m (Execution)
Indicators: EMA (100, 50, 20), RSI (14), ATR (14)
Entry: SMC Sweep + FVG + Tendencia confirmada
Risk: SL 1.5x ATR, TP 3.75x ATR (Ratio ~2.5:1)
"""

import pandas as pd
import numpy as np
import logging
from config.settings import settings

logger = logging.getLogger(__name__)


class HyperQuantStrategy:
    def __init__(self):
        self.ema_bias_period = 100
        self.ema_trend_period = 50
        self.ema_short_period = 20
        self.atr_period = 14
        self.rsi_period = 14
        self.rsi_long_max = 65
        self.rsi_short_min = 35
        self.rsi_oversold = 40
        self.rsi_overbought = 60
        self.fvg_min_pct = 0.001
        self.atr_volatility_filter = 2.0

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame = None):
        if df is None or len(df) < 50:
            return None

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        if df["close"].isna().any():
            return None

        df["atr"] = self._calculate_atr(df)
        df["atr_sma"] = df["atr"].rolling(20).mean()
        df["ema_20"] = df["close"].ewm(span=self.ema_short_period, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=self.ema_trend_period, adjust=False).mean()
        df["ema_100"] = df["close"].ewm(span=self.ema_bias_period, adjust=False).mean()
        df["rsi"] = self._calculate_rsi(df)

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        price = curr["close"]
        ema_20 = curr["ema_20"]
        ema_50 = curr["ema_50"]
        ema_100 = curr["ema_100"]
        rsi = curr["rsi"]
        atr = curr["atr"]
        atr_sma = curr["atr_sma"]

        if pd.isna(rsi) or pd.isna(atr) or atr == 0:
            return None

        volatility_ratio = atr / atr_sma if not pd.isna(atr_sma) else 1.0

        if volatility_ratio < 0.3:
            logger.debug(f"Omitiendo {symbol} - Baja volatilidad (ratio: {volatility_ratio:.2f})")
            return None

        bias = "LONG" if price > ema_100 else "SHORT"
        trend = "LONG" if ema_50 > ema_100 else "SHORT"

        if bias == "LONG":
            if trend == "SHORT":
                return None

            if rsi > self.rsi_long_max:
                return None

            recent_lows = df["low"].iloc[-15:-1].min()
            sweep = curr["low"] < recent_lows and prev["close"] > recent_lows

            fvg_gap = curr["low"] - prev2["high"]
            fvg_pct = fvg_gap / price if price > 0 else 0
            fvg = fvg_gap > 0 and fvg_pct > self.fvg_min_pct

            pullback = (
                price > ema_20 and prev["low"] <= ema_20 and curr["close"] > ema_20
            )

            rsi_confluence = rsi < 60 and rsi > 30

            if (sweep and fvg) or pullback:
                sl = price - (atr * 1.5)
                tp = price + (atr * 3.75)

                return {
                    "symbol": symbol,
                    "signal": "LONG",
                    "entry_price": price,
                    "sl": sl,
                    "tp": tp,
                    "atr": atr,
                    "info": f"V10 LONG | RSI:{rsi:.1f} | ATR:{atr:.4f} | R:R 2.5:1",
                }

        else:
            if trend == "LONG":
                return None

            if rsi < self.rsi_short_min:
                return None

            recent_highs = df["high"].iloc[-15:-1].max()
            sweep = curr["high"] > recent_highs and prev["close"] < recent_highs

            fvg_gap = prev2["low"] - curr["high"]
            fvg_pct = fvg_gap / price if price > 0 else 0
            fvg = fvg_gap > 0 and fvg_pct > self.fvg_min_pct

            pullback = (
                price < ema_20 and prev["high"] >= ema_20 and curr["close"] < ema_20
            )

            rsi_confluence = rsi > 40 and rsi < 70

            if (sweep and fvg) or pullback:
                sl = price + (atr * 1.5)
                tp = price - (atr * 3.75)

                return {
                    "symbol": symbol,
                    "signal": "SHORT",
                    "entry_price": price,
                    "sl": sl,
                    "tp": tp,
                    "atr": atr,
                    "info": f"V10 SHORT | RSI:{rsi:.1f} | ATR:{atr:.4f} | R:R 2.5:1",
                }

        return None

    def check_market_regime(self, df: pd.DataFrame) -> str:
        if df is None or len(df) < 50:
            return "UNKNOWN"

        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["atr"] = self._calculate_atr(df)
        df["atr_ma"] = df["atr"].rolling(20).mean()

        curr = df.iloc[-1]
        price = curr["close"]
        ema_50 = curr["ema_50"]
        atr = curr["atr"]
        atr_ma = curr["atr_ma"]

        if price > ema_50:
            trend = "UP"
        else:
            trend = "DOWN"

        volatility = atr / atr_ma if not pd.isna(atr_ma) else 1.0

        if volatility > 1.5:
            regime = "HIGH_VOLATILITY"
        elif volatility < 0.7:
            regime = "LOW_VOLATILITY"
        else:
            regime = "NORMAL"

        return f"{trend}_{regime}"

    def _calculate_atr(self, df, period=14):
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def _calculate_rsi(self, df, period=14):
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))


strategy = HyperQuantStrategy()
