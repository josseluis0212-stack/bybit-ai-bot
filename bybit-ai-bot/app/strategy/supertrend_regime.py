import pandas as pd
import pandas_ta as ta
import numpy as np
from app.logger import logger

def calculate_supertrend(df, atr_length=10, factor=3.0):
    st = ta.supertrend(df['high'], df['low'], df['close'], length=atr_length, multiplier=factor)
    if st is not None and not st.empty:
        df['supertrend'] = st.iloc[:, 0]
        df['supertrend_dir'] = st.iloc[:, 1]
    return df

async def evaluate_supertrend_regime(client, symbol: str):
    """
    Estrategia 2: SuperTrend EMA Regime MTF Pro (Implementación Exacta)
    """
    try:
        # Fetch data for 15m and 1h. Need enough data for EMA200 + 160 candles lookback
        klines_15m = await client.get_klines(symbol, interval="15", limit=500)
        klines_1h = await client.get_klines(symbol, interval="60", limit=250)

        if not klines_15m or len(klines_15m) < 400 or not klines_1h or len(klines_1h) < 220:
            return {"signal": "NONE", "exit_long": False, "exit_short": False}

        df_15m = pd.DataFrame(klines_15m)
        df_1h = pd.DataFrame(klines_1h)

        # Calculate Indicators 15m
        df_15m['ema_200'] = ta.ema(df_15m['close'], length=200)
        df_15m['ema_9'] = ta.ema(df_15m['close'], length=9)
        df_15m['ema_21'] = ta.ema(df_15m['close'], length=21)
        df_15m = calculate_supertrend(df_15m, atr_length=10, factor=3.0)
        df_15m['atr'] = ta.atr(df_15m['high'], df_15m['low'], df_15m['close'], length=10)
        
        adx = ta.adx(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
        if adx is not None and not adx.empty:
            df_15m['adx'] = adx['ADX_14']
        else:
            df_15m['adx'] = 0

        # Slope EMA200 against 10 candles ago
        df_15m['ema_200_slope'] = df_15m['ema_200'] - df_15m['ema_200'].shift(10)
        df_15m['distance_to_ema200'] = abs(df_15m['close'] - df_15m['ema_200'])

        # Calculate Indicators 1h
        df_1h['ema_200_1h'] = ta.ema(df_1h['close'], length=200)
        df_1h['ema_9_1h'] = ta.ema(df_1h['close'], length=9)
        df_1h['ema_21_1h'] = ta.ema(df_1h['close'], length=21)

        # Drop NaN
        df_15m.dropna(inplace=True)
        df_1h.dropna(inplace=True)

        if len(df_15m) < 170:
            return {"signal": "NONE", "exit_long": False, "exit_short": False}

        latest_1h = df_1h.iloc[-1]
        
        # Look from index -161 to -2 (160 candles backwards)
        lookback_df = df_15m.iloc[-161:-1]
        
        long_armed = False
        short_armed = False

        # Vectorized check for previous armed state (Caducidad 160 velas)
        # En pandas_ta: direction == 1 es Alcista (Verde), direction == -1 es Bajista (Rojo)
        # superRed: direction == -1
        bearish_prior = (
            (lookback_df['supertrend_dir'] == -1) & 
            (lookback_df['close'] < lookback_df['ema_200']) & 
            (lookback_df['ema_9'] < lookback_df['ema_21'])
        )
        if bearish_prior.any():
            long_armed = True

        # superGreen: direction == 1
        bullish_prior = (
            (lookback_df['supertrend_dir'] == 1) & 
            (lookback_df['close'] > lookback_df['ema_200']) & 
            (lookback_df['ema_9'] > lookback_df['ema_21'])
        )
        if bullish_prior.any():
            short_armed = True

        latest_15m = df_15m.iloc[-1]
        
        signal = "NONE"
        reason = ""
        exit_long = False
        exit_short = False

        # Condiciones base para la vela actual
        superGreen = latest_15m['supertrend_dir'] == 1
        superRed = latest_15m['supertrend_dir'] == -1
        
        adx_ok = latest_15m['adx'] >= 18
        slope_long_ok = latest_15m['ema_200_slope'] > 0
        slope_short_ok = latest_15m['ema_200_slope'] < 0
        distance_ok = latest_15m['distance_to_ema200'] >= (0.3 * latest_15m['atr'])
        
        htf_long_ok = latest_1h['close'] > latest_1h['ema_200_1h'] and latest_1h['ema_9_1h'] > latest_1h['ema_21_1h']
        htf_short_ok = latest_1h['close'] < latest_1h['ema_200_1h'] and latest_1h['ema_9_1h'] < latest_1h['ema_21_1h']

        # Condición contraria bajista completa (Exit Long)
        if (short_armed and
            superRed and
            latest_15m['close'] < latest_15m['ema_200'] and
            latest_15m['supertrend'] < latest_15m['ema_200'] and
            latest_15m['ema_9'] < latest_15m['ema_200'] and
            latest_15m['ema_21'] < latest_15m['ema_200'] and
            latest_15m['ema_9'] < latest_15m['ema_21']):
            exit_long = True

        # Condición contraria alcista completa (Exit Short)
        if (long_armed and
            superGreen and
            latest_15m['close'] > latest_15m['ema_200'] and
            latest_15m['supertrend'] > latest_15m['ema_200'] and
            latest_15m['ema_9'] > latest_15m['ema_200'] and
            latest_15m['ema_21'] > latest_15m['ema_200'] and
            latest_15m['ema_9'] > latest_15m['ema_21']):
            exit_short = True

        # Evaluate Long Entry
        if (long_armed and 
            superGreen and
            latest_15m['close'] > latest_15m['ema_200'] and
            latest_15m['supertrend'] > latest_15m['ema_200'] and
            latest_15m['ema_9'] > latest_15m['ema_200'] and
            latest_15m['ema_21'] > latest_15m['ema_200'] and
            latest_15m['ema_9'] > latest_15m['ema_21'] and
            adx_ok and
            slope_long_ok and
            distance_ok and
            htf_long_ok):
            
            signal = "LONG"
            reason = "SuperTrend Regime MTF Pro - Long Entry"

        # Evaluate Short Entry
        elif (short_armed and
            superRed and
            latest_15m['close'] < latest_15m['ema_200'] and
            latest_15m['supertrend'] < latest_15m['ema_200'] and
            latest_15m['ema_9'] < latest_15m['ema_200'] and
            latest_15m['ema_21'] < latest_15m['ema_200'] and
            latest_15m['ema_9'] < latest_15m['ema_21'] and
            adx_ok and
            slope_short_ok and
            distance_ok and
            htf_short_ok):
            
            signal = "SHORT"
            reason = "SuperTrend Regime MTF Pro - Short Entry"

        return {
            "signal": signal,
            "reason": reason,
            "atr": latest_15m['atr'],
            "exit_long": exit_long,
            "exit_short": exit_short
        }

    except Exception as e:
        logger.error(f"[SUPERTREND] Error evaluating {symbol}: {e}")
        return {"signal": "NONE", "exit_long": False, "exit_short": False}

