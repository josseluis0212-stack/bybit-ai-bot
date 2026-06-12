from app.exchange.bingx_client import AsyncBingXClient
from app.utils.indicators import calculate_ema, calculate_atr
from app.logger import logger

async def analyze(client: AsyncBingXClient, symbol: str) -> dict:
    """
    SMC PRO V1 (5m Timeframe)
    Based on Advanced SMC Concepts:
    1. Trend Filter (EMA 100)
    2. Liquidity Sweep (AMD - Manipulation)
    3. BOS / ChoCH (Distribution)
    4. Orderblock + FVG for Entry
    """
    klines_5m = await client.get_klines(symbol, "5m", 100)
    if not klines_5m or len(klines_5m) < 100: 
        return {"signal": "NONE"}
        
    klines_5m = klines_5m[:-1] # Remove open candle
    
    closes = [c["close"] for c in klines_5m]
    highs = [c["high"] for c in klines_5m]
    lows = [c["low"] for c in klines_5m]
    
    ema100 = calculate_ema(closes, 100)[-1]
    atr = calculate_atr(highs, lows, closes, 14)[-1]
    
    c3 = klines_5m[-1]
    c2 = klines_5m[-2]
    c1 = klines_5m[-3]
    
    signal = "NONE"
    entry_price = 0.0
    sl_price = 0.0
    
    # Analyze macro trend
    is_uptrend = c3["close"] > ema100
    is_downtrend = c3["close"] < ema100
    
    # ------------------ LONG LOGIC ------------------
    if is_uptrend:
        # Find swing low (Liquidity Pool) in the past 40 candles (excluding the last 3)
        recent_lows = [k["low"] for k in klines_5m[-43:-3]]
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
                    logger.info(f"[{symbol} SMC-LONG] Sweep and BOS, but no FVG.")
    
    # ------------------ SHORT LOGIC ------------------
    elif is_downtrend:
        # Find swing high (Liquidity Pool) in the past 40 candles
        recent_highs = [k["high"] for k in klines_5m[-43:-3]]
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
                    logger.info(f"[{symbol} SMC-SHORT] Sweep and BOS, but no FVG.")
                    
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
