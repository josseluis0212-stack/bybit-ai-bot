from app.utils.indicators import calculate_ema, calculate_rsi, calculate_atr, calculate_adx

async def evaluate_v10_pro(client, symbol: str) -> dict:
    # 1. Macro Bias (1H)
    klines_1h = await client.get_klines(symbol, "1h", 100)
    if not klines_1h or len(klines_1h) < 50: return {"signal": "NONE"}
    closes_1h = [c["close"] for c in klines_1h]
    ema50_1h = calculate_ema(closes_1h, 50)[-1]
    current_close_1h = closes_1h[-1]
    
    bias = "LONG" if current_close_1h > ema50_1h else "SHORT"
    
    # 2. Momentum (15M)
    klines_15m = await client.get_klines(symbol, "15m", 100)
    if not klines_15m or len(klines_15m) < 50: return {"signal": "NONE"}
    closes_15m = [c["close"] for c in klines_15m]
    highs_15m = [c["high"] for c in klines_15m]
    lows_15m = [c["low"] for c in klines_15m]
    
    ema50_15m = calculate_ema(closes_15m, 50)[-1]
    rsi_15m = calculate_rsi(closes_15m, 14)[-1]
    adx_15m = calculate_adx(highs_15m, lows_15m, closes_15m, 14)[-1]
    current_close_15m = closes_15m[-1]
    
    if adx_15m < 20:
        return {"signal": "NONE"}
        
    if bias == "LONG":
        if not (current_close_15m > ema50_15m and rsi_15m < 65):
            return {"signal": "NONE"}
    else:
        if not (current_close_15m < ema50_15m and rsi_15m > 35):
            return {"signal": "NONE"}
            
    # 3. Sniper Gatillo (5M FVG)
    klines_5m = await client.get_klines(symbol, "5m", 20)
    if not klines_5m or len(klines_5m) < 5: return {"signal": "NONE"}
    
    # Calculate ATR for SL/TP
    highs = [c["high"] for c in klines_5m]
    lows = [c["low"] for c in klines_5m]
    closes_5m = [c["close"] for c in klines_5m]
    atr = calculate_atr(highs, lows, closes_5m, 14)[-1]
    
    fvg_found = False
    entry_price = 0.0
    sl_price = 0.0
    
    # Look for FVG in the last 5 candles
    # We iterate backwards through the last 5 indices (-1 to -5)
    for i in range(-1, -6, -1):
        if len(klines_5m) < abs(i) + 2: continue
        c1 = klines_5m[i-2]
        c2 = klines_5m[i-1] # The big candle
        c3 = klines_5m[i]
        
        if bias == "LONG":
            # Bullish FVG: Low actual (c3) > High prev (c1) + vela alcista
            if c3["low"] > c1["high"] and c3["close"] > c3["open"]:
                fvg_found = True
                entry_price = (c3["low"] + c1["high"]) / 2.0  # Punto medio del FVG
                sl_price = entry_price - (2.5 * atr)
                break
        else:
            # Bearish FVG: High actual (c3) < Low prev (c1) + vela bajista
            if c3["high"] < c1["low"] and c3["close"] < c3["open"]:
                fvg_found = True
                entry_price = (c3["high"] + c1["low"]) / 2.0  # Punto medio del FVG
                sl_price = entry_price + (2.5 * atr)
                break
                
    if fvg_found:
        return {
            "signal": bias,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "atr": atr,
            "strategy": "QUANTUM_V10_PRO"
        }
        
    return {"signal": "NONE"}
