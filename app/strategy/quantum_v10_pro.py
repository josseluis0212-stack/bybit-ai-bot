from app.utils.indicators import calculate_ema, calculate_rsi, calculate_atr, calculate_adx, calculate_sma

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
        if not (current_close_15m > ema50_15m and 50 < rsi_15m < 65):
            return {"signal": "NONE"}
    else:
        if not (current_close_15m < ema50_15m and 35 < rsi_15m < 50):
            return {"signal": "NONE"}
            
    # 3. Sniper Gatillo (5M FVG)
    klines_5m = await client.get_klines(symbol, "5m", 20)
    if not klines_5m or len(klines_5m) < 5: return {"signal": "NONE"}
    
    # Calculate ATR for SL/TP
    highs = [c["high"] for c in klines_5m]
    lows = [c["low"] for c in klines_5m]
    closes_5m = [c["close"] for c in klines_5m]
    volumes_5m = [c["volume"] for c in klines_5m]
    atr = calculate_atr(highs, lows, closes_5m, 14)[-1]
    
    # Calculate 10-period SMA of Volume
    sma_vol_10 = calculate_sma(volumes_5m, 10)
    
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
        
        # FVG found
        # Apply Smart Money Order Flow (Volume Filter) on the displacement candle (c2)
        # Displacement candle volume must be >= 90% of SMA-10 volume
        idx_c2 = len(volumes_5m) + i - 1  # Get absolute index of c2
        if c2["volume"] < 0.9 * sma_vol_10[idx_c2]:
            continue
            
        # Break of Structure (BOS) Validation
        start_idx = i - 12
        end_idx = i - 2
        if start_idx < -len(klines_5m): start_idx = -len(klines_5m)
        local_high = max([c["high"] for c in klines_5m[start_idx:end_idx]]) if end_idx > start_idx else c1["high"]
        local_low = min([c["low"] for c in klines_5m[start_idx:end_idx]]) if end_idx > start_idx else c1["low"]
        
        range_c3 = c3["high"] - c3["low"]
        latest_c = klines_5m[-1]
        
        if bias == "LONG":
            # Bullish FVG with BOS
            if c3["low"] > c1["high"] and c3["close"] > c3["open"] and c3["close"] > local_high:
                fvg_top = c3["low"]
                fvg_bottom = c1["high"]
                mitigation_price = fvg_bottom + ((fvg_top - fvg_bottom) * 0.5)
                
                # Check if mitigated by the most recent candles
                if latest_c["low"] <= mitigation_price <= latest_c["high"] or (i == -1 and c3["low"] <= mitigation_price):
                    fvg_found = True
                    entry_price = latest_c["close"]  # Execute market at current close
                    sl_price = c1["low"] - (0.5 * atr)
                    break
        else:
            # Bearish FVG with BOS
            if c3["high"] < c1["low"] and c3["close"] < c3["open"] and c3["close"] < local_low:
                fvg_top = c1["low"]
                fvg_bottom = c3["high"]
                mitigation_price = fvg_bottom + ((fvg_top - fvg_bottom) * 0.5)
                
                # Check if mitigated by the most recent candles
                if latest_c["low"] <= mitigation_price <= latest_c["high"] or (i == -1 and c3["high"] >= mitigation_price):
                    fvg_found = True
                    entry_price = latest_c["close"]
                    sl_price = c1["high"] + (0.5 * atr)
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
