import pandas as pd
import pandas_ta as ta
import numpy as np

def calculate_indicators_15m(df, config):
    """
    Calculates 15m timeframe indicators.
    df should have columns: timestamp, open, high, low, close, volume
    """
    if df.empty or len(df) < config.EMA_TREND_PERIOD + 10:
        return df
        
    df = df.copy()
    
    # EMAs
    df['ema_200'] = ta.ema(df['close'], length=config.EMA_TREND_PERIOD)
    df['ema_9'] = ta.ema(df['close'], length=config.EMA_FAST_PERIOD)
    df['ema_21'] = ta.ema(df['close'], length=config.EMA_MEDIUM_PERIOD)
    
    # SuperTrend
    # pandas_ta supertrend returns a dataframe with columns: SUPERT_length_factor, SUPERTd_length_factor, SUPERTl_length_factor, SUPERTs_length_factor
    st = ta.supertrend(df['high'], df['low'], df['close'], length=config.SUPERTREND_ATR_LENGTH, multiplier=config.SUPERTREND_FACTOR)
    
    # We need the trend direction and the value.
    # SUPERTd_10_3.0 will be 1 for uptrend (green) and -1 for downtrend (red)
    # SUPERT_10_3.0 will be the line value itself
    st_val_col = f'SUPERT_{config.SUPERTREND_ATR_LENGTH}_{config.SUPERTREND_FACTOR}'
    st_dir_col = f'SUPERTd_{config.SUPERTREND_ATR_LENGTH}_{config.SUPERTREND_FACTOR}'
    
    df['supertrend'] = st[st_val_col]
    df['supertrend_dir'] = st[st_dir_col] # 1 = green, -1 = red
    
    # ATR for risk management
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=config.ATR_LENGTH)
    
    # ADX
    # pandas_ta adx returns a dataframe with ADX_14, DMP_14, DMN_14
    adx = ta.adx(df['high'], df['low'], df['close'], length=config.ADX_LENGTH)
    adx_col = f'ADX_{config.ADX_LENGTH}'
    df['adx'] = adx[adx_col]
    
    # Slope of EMA200 (difference vs N bars ago)
    df['ema_200_slope'] = df['ema_200'].diff(periods=config.SLOPE_LOOKBACK)
    
    # Distance between price and EMA200
    df['distance_to_ema200'] = abs(df['close'] - df['ema_200'])
    
    return df

def calculate_indicators_1h(df, config):
    """
    Calculates 1h timeframe indicators.
    df should have columns: timestamp, open, high, low, close, volume
    """
    if df.empty or len(df) < config.EMA_TREND_PERIOD:
        return df
        
    df = df.copy()
    
    # 1H EMAs
    df['ema_200_1h'] = ta.ema(df['close'], length=config.EMA_TREND_PERIOD)
    df['ema_9_1h'] = ta.ema(df['close'], length=config.EMA_FAST_PERIOD)
    df['ema_21_1h'] = ta.ema(df['close'], length=config.EMA_MEDIUM_PERIOD)
    
    return df
