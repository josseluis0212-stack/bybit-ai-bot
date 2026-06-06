from app.utils.indicators import calculate_rsi, calculate_atr

async def evaluate_divergence(client, symbol: str) -> dict:
    # 1. Divergence Radar (15M)
    klines_15m = await client.get_klines(symbol, "15m", 50)
    if not klines_15m or len(klines_15m) < 40: return {"signal": "NONE"}
    
    closes_15m = [c["close"] for c in klines_15m]
    lows_15m = [c["low"] for c in klines_15m]
    highs_15m = [c["high"] for c in klines_15m]
    
    rsi_15m = calculate_rsi(closes_15m, 14)
    current_rsi = rsi_15m[-1]
    
    # We analyze the last 30 candles, split into two windows of 15
    window_old_lows = lows_15m[-30:-15]
    window_new_lows = lows_15m[-15:]
    window_old_highs = highs_15m[-30:-15]
    window_new_highs = highs_15m[-15:]
    
    window_old_rsi = rsi_15m[-30:-15]
    window_new_rsi = rsi_15m[-15:]
    
    # Bullish Divergence
    # LL in price, HL in RSI, currently Oversold (<40)
    min_price_old = min(window_old_lows)
    min_price_new = min(window_new_lows)
    
    idx_min_old = window_old_lows.index(min_price_old)
    idx_min_new = window_new_lows.index(min_price_new)
    
    rsi_at_min_old = window_old_rsi[idx_min_old]
    rsi_at_min_new = window_new_rsi[idx_min_new]
    
    bias = "NONE"
    
    if min_price_new < min_price_old and rsi_at_min_new > rsi_at_min_old and current_rsi < 40:
        bias = "LONG"
    
    # Bearish Divergence
    # HH in price, LH in RSI, currently Overbought (>60)
    max_price_old = max(window_old_highs)
    max_price_new = max(window_new_highs)
    
    idx_max_old = window_old_highs.index(max_price_old)
    idx_max_new = window_new_highs.index(max_price_new)
    
    rsi_at_max_old = window_old_rsi[idx_max_old]
    rsi_at_max_new = window_new_rsi[idx_max_new]
    
    if bias == "NONE":
        if max_price_new > max_price_old and rsi_at_max_new < rsi_at_max_old and current_rsi > 60:
            bias = "SHORT"
            
    if bias == "NONE":
        return {"signal": "NONE"}
        
    # 2. Sniper Gatillo (5M FVG)
    klines_5m = await client.get_klines(symbol, "5m", 20)
    if not klines_5m or len(klines_5m) < 5: return {"signal": "NONE"}
    
    # Calculate ATR for SL/TP
    highs_5m = [c["high"] for c in klines_5m]
    lows_5m = [c["low"] for c in klines_5m]
    closes_5m = [c["close"] for c in klines_5m]
    atr = calculate_atr(highs_5m, lows_5m, closes_5m, 14)[-1]
    
    fvg_found = False
    entry_price = 0.0
    sl_price = 0.0
    
    # Look for FVG in the last 5 candles
    for i in range(-1, -6, -1):
        if len(klines_5m) < abs(i) + 2: continue
        c1 = klines_5m[i-2]
        c2 = klines_5m[i-1]
        c3 = klines_5m[i]
        
        if bias == "LONG":
            # Bullish FVG
            if c3["low"] > c1["high"] and c3["close"] > c3["open"]:
                fvg_found = True
                entry_price = (c3["low"] + c1["high"]) / 2.0
                sl_price = entry_price - (2.5 * atr)
                break
        else:
            # Bearish FVG
            if c3["high"] < c1["low"] and c3["close"] < c3["open"]:
                fvg_found = True
                entry_price = (c3["high"] + c1["low"]) / 2.0
                sl_price = entry_price + (2.5 * atr)
                break
                
    if fvg_found:
        return {
            "signal": bias,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "atr": atr,
            "strategy": "QUANTUM_DIVERGENCE"
        }
        
    return {"signal": "NONE"}
