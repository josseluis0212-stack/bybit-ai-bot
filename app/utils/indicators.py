import pandas as pd
import numpy as np

def calculate_ema(closes: list[float], period: int) -> list[float]:
    if len(closes) < period:
        return [0.0] * len(closes)
    s = pd.Series(closes)
    ema = s.ewm(span=period, adjust=False).mean()
    return ema.tolist()

def calculate_rsi(closes: list[float], period: int = 14) -> list[float]:
    if len(closes) <= period:
        return [50.0] * len(closes)
    
    s = pd.Series(closes)
    delta = s.diff()
    
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50.0) # Fill NaN with neutral 50
    return rsi.tolist()

def calculate_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if len(closes) <= period:
        return [0.0] * len(closes)
        
    df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})
    df['prev_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = (df['high'] - df['prev_close']).abs()
    df['tr3'] = (df['low'] - df['prev_close']).abs()
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    atr = df['tr'].rolling(window=period).mean()
    return atr.fillna(0.0).tolist()

def calculate_adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if len(closes) <= period:
        return [0.0] * len(closes)
        
    df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})
    df['prev_close'] = df['close'].shift(1)
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)
    
    # Calculate True Range
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = (df['high'] - df['prev_close']).abs()
    df['tr3'] = (df['low'] - df['prev_close']).abs()
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # Calculate Directional Movement
    df['up_move'] = df['high'] - df['prev_high']
    df['down_move'] = df['prev_low'] - df['low']
    
    df['+dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
    df['-dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
    
    # Wilder's Smoothing
    tr_smoothed = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (df['+dm'].ewm(alpha=1/period, adjust=False).mean() / tr_smoothed)
    minus_di = 100 * (df['-dm'].ewm(alpha=1/period, adjust=False).mean() / tr_smoothed)
    
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return adx.fillna(0.0).tolist()
