from app.exchange.bingx_client import AsyncBingXClient
from app.utils.indicators import calculate_ema, calculate_atr, calculate_adx
from app.logger import logger
from app.config import Config

async def analyze(client: AsyncBingXClient, symbol: str) -> dict:
    """
    SMC PRO V1 (15m Timeframe with 1H Trend)
    Based on Advanced SMC Concepts:
    1. Trend Filter (EMA 100 on 1H)
    2. Strength Filter (ADX > 20 on 15m)
    3. Liquidity Sweep (AMD - Manipulation)
    4. BOS / ChoCH (Distribution)
    5. Orderblock + FVG for Entry
    """
    # Fetch 15m candles
    klines_15m = await client.get_klines(symbol, Config.TIMEFRAME, 100)
    if not klines_15m or len(klines_15m) < 100: 
        return {"signal": "NONE"}
        
    # Fetch 1h candles
    klines_1h = await client.get_klines(symbol, "1h", 100)
    if not klines_1h or len(klines_1h) < 100:
        return {"signal": "NONE"}
        
    klines_15m = klines_15m[:-1] # Remove open candle
    klines_1h = klines_1h[:-1] # Remove open candle
    
    closes_15m = [c["close"] for c in klines_15m]
    highs_15m = [c["high"] for c in klines_15m]
    lows_15m = [c["low"] for c in klines_15m]
    
    closes_1h = [c["close"] for c in klines_1h]
    
    # 1H Trend Filter
    ema100_1h = calculate_ema(closes_1h, 100)[-1]
    
    # 15M Indicators
    atr = calculate_atr(highs_15m, lows_15m, closes_15m, 14)[-1]
    adx_list = calculate_adx(highs_15m, lows_15m, closes_15m, 14)
    adx_val = adx_list[-1] if adx_list else 0
    
    c3 = klines_15m[-1]
    c2 = klines_15m[-2]
    c1 = klines_15m[-3]
    
    signal = "NONE"
    entry_price = 0.0
    sl_price = 0.0
    
    # Analyze macro trend (1H)
    is_uptrend = c3["close"] > ema100_1h
    is_downtrend = c3["close"] < ema100_1h
    
    # Analyze ADX strength
    has_strength = adx_val > 20
    
    # ------------------ LONG LOGIC ------------------
    if is_uptrend and has_strength:
        # Find swing low (Liquidity Pool) in the past 40 candles (excluding the last 3)
        recent_lows = [k["low"] for k in klines_15m[-43:-3]]
        swing_low = min(recent_lows)
        
        # 1. Manipulation: Did c1 or c2 sweep the liquidity?
        liquidity_sweep = c1["low"] < swing_low or c2["low"] < swing_low
        
        if liquidity_sweep:
            # 2. Distribution (ChoCH/BOS): Did c3 break structure up with momentum?
            bos = c3["close"] > c1["high"] and c3["close"] > c3["open"]
            
            if bos:
                # 3. FVG / Orderblock Detection
                fvg = c3["low"] > c1["high"]
                if fvg:
                    signal = "LONG"
                    # Entry at the FVG / Orderblock overlap
                    entry_price = c1["high"]
                    # SL below the manipulation sweep
                    sl_price = min(c1["low"], c2["low"]) - (0.5 * atr)
                else:
                    pass
    
    # ------------------ SHORT LOGIC ------------------
    elif is_downtrend and has_strength:
        # Find swing high (Liquidity Pool) in the past 40 candles
        recent_highs = [k["high"] for k in klines_15m[-43:-3]]
        swing_high = max(recent_highs)
        
        # 1. Manipulation: Did c1 or c2 sweep the liquidity?
        liquidity_sweep = c1["high"] > swing_high or c2["high"] > swing_high
        
        if liquidity_sweep:
            # 2. Distribution (ChoCH/BOS): Did c3 break structure down with momentum?
            bos = c3["close"] < c1["low"] and c3["close"] < c3["open"]
            
            if bos:
                # 3. FVG / Orderblock Detection
                fvg = c3["high"] < c1["low"]
                if fvg:
                    signal = "SHORT"
                    entry_price = c1["low"]
                    sl_price = max(c1["high"], c2["high"]) + (0.5 * atr)
                else:
                    pass
                    
    if signal != "NONE":
        return {
            "signal": signal,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "atr": atr,
            "strategy": "SMC_PRO_V1",
            "is_limit": True
        }
        
    return {"signal": "NONE"}
