from app.utils.indicators import calculate_ema, calculate_sma, calculate_atr, calculate_hull_ma, calculate_macd, calculate_bollinger_bands, ta_rising, ta_falling, calculate_dmi, calculate_rsi
from app.config import Config
from app.logger import logger

async def evaluate_antigravity_v13(client, symbol: str) -> dict:
    """
    Estrategia "ANTIGRAVITY QUANTUM V13 PRO - FINAL"
    """
    # Fetch enough klines for EMA200 calculation
    klines = await client.get_klines(symbol, Config.TIMEFRAME, 250)
    if not klines or len(klines) < 220:
        return {"signal": "NONE"}
    
    # Drop the unclosed candle
    klines = klines[:-1]
    
    closes = [c["close"] for c in klines]
    highs = [c["high"] for c in klines]
    lows = [c["low"] for c in klines]
    volumes = [c["volume"] for c in klines]
    
    # INDICADORES
    ema9 = calculate_ema(closes, 9)
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    ema100 = calculate_ema(closes, 100)
    ema200 = calculate_ema(closes, 200)
    
    hull20 = calculate_hull_ma(closes, 20)
    hull50 = calculate_hull_ma(closes, 50)
    
    atr14 = calculate_atr(highs, lows, closes, 14)
    plus_di, minus_di, adx14 = calculate_dmi(highs, lows, closes, 14)
    
    volMA = calculate_sma(volumes, 20)
    volSMA50 = calculate_sma(volumes, 50)
    
    rsi14 = calculate_rsi(closes, 14)
    macd_line, signal_line, _ = calculate_macd(closes, 12, 26, 9)
    
    bb_middle, bb_upper, bb_lower = calculate_bollinger_bands(closes, 20, 2.0)
    
    # Current values
    current_close = closes[-1]
    current_volume = volumes[-1]
    current_atr = atr14[-1] if atr14 else 0
    
    # Trend Bull/Bear
    rising_ema9 = ta_rising(ema9, 2)
    falling_ema9 = ta_falling(ema9, 2)
    rising_ema20 = ta_rising(ema20, 3)
    falling_ema20 = ta_falling(ema20, 3)
    
    trendBull = current_close > ema100[-1] and ema20[-1] > ema50[-1] and rising_ema20
    trendBear = current_close < ema100[-1] and ema20[-1] < ema50[-1] and falling_ema20
    
    # Volume Filter (Relaxed slightly)
    volSurge = current_volume > volMA[-1] * 1.05
    volIncreasing = current_volume > volSMA50[-1] * 0.85
    volFilter = volSurge and volIncreasing
    
    # ADX Filter (Relaxed)
    adxThreshold = 14
    adxFilterBull = adx14[-1] > adxThreshold and plus_di[-1] > minus_di[-1]
    adxFilterBear = adx14[-1] > adxThreshold and minus_di[-1] > plus_di[-1]
    
    # RSI Filter
    rsiFilterBull = rsi14[-1] > 30 and rsi14[-1] < 80
    rsiFilterBear = rsi14[-1] < 70 and rsi14[-1] > 20
    
    # MACD Filter
    macdBull = macd_line[-1] > signal_line[-1]
    macdBear = macd_line[-1] < signal_line[-1]
    
    # Bollinger Bands Filter
    bbFilterBull = current_close > bb_middle[-1] and current_close < bb_upper[-1]
    bbFilterBear = current_close < bb_middle[-1] and current_close > bb_lower[-1]
    
    # Volatility OK
    atrPercent = (current_atr / current_close) * 100 if current_close > 0 else 0
    volatilityOK = atrPercent > 0.25 and atrPercent < 4.5
    
    # Crossovers
    prev_hull20 = hull20[-2]
    prev_hull50 = hull50[-2]
    curr_hull20 = hull20[-1]
    curr_hull50 = hull50[-1]
    
    hullCrossLong = prev_hull20 <= prev_hull50 and curr_hull20 > curr_hull50
    hullCrossShort = prev_hull20 >= prev_hull50 and curr_hull20 < curr_hull50
    
    longEntry = trendBull and volFilter and adxFilterBull and rsiFilterBull and macdBull and bbFilterBull and volatilityOK and hullCrossLong
    shortEntry = trendBear and volFilter and adxFilterBear and rsiFilterBear and macdBear and bbFilterBear and volatilityOK and hullCrossShort
    
    signal = "NONE"
    if longEntry:
        signal = "LONG"
    elif shortEntry:
        signal = "SHORT"
        
    if signal == "NONE":
        return {"signal": "NONE"}
        
    # GESTION DE RIESGO
    atrSL = 2.5
    riskReward = 3.0
    
    dynamicSl = current_atr * atrSL
    dynamicTp = dynamicSl * riskReward
    
    entry_price = current_close
    sl_price = entry_price - dynamicSl if signal == "LONG" else entry_price + dynamicSl
    tp_price = entry_price + dynamicTp if signal == "LONG" else entry_price - dynamicTp
    
    return {
        "signal": signal,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price, # Final max target
        "atr": current_atr,
        "strategy": "ANTIGRAVITY_V13_PRO",
        "is_limit": False
    }
