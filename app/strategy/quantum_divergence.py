from app.utils.indicators import calculate_rsi, calculate_atr, calculate_sma

async def evaluate_divergence(client, symbol: str) -> dict:
    # 1. Divergence Radar (15M)
    klines_15m = await client.get_klines(symbol, "15m", 50)
    if not klines_15m or len(klines_15m) < 40: return {"signal": "NONE"}
    
    closes_15m = [c["close"] for c in klines_15m]
    lows_15m = [c["low"] for c in klines_15m]
    highs_15m = [c["high"] for c in klines_15m]
    
    rsi_15m = calculate_rsi(closes_15m, 14)
    current_rsi = rsi_15m[-1]
    
    # Detect Swing Lows and Swing Highs
    swing_lows = []
    swing_highs = []
    
    for i in range(2, len(klines_15m) - 2):
        # Swing Low
        if lows_15m[i] < lows_15m[i-1] and lows_15m[i] < lows_15m[i-2] and lows_15m[i] < lows_15m[i+1] and lows_15m[i] < lows_15m[i+2]:
            swing_lows.append((i, lows_15m[i], rsi_15m[i]))
            
        # Swing High
        if highs_15m[i] > highs_15m[i-1] and highs_15m[i] > highs_15m[i-2] and highs_15m[i] > highs_15m[i+1] and highs_15m[i] > highs_15m[i+2]:
            swing_highs.append((i, highs_15m[i], rsi_15m[i]))
            
    bias = "NONE"
    
    # Bullish Divergence check
    if len(swing_lows) >= 2:
        idx_old, min_old, rsi_old = swing_lows[-2]
        idx_new, min_new, rsi_new = swing_lows[-1]
        
        # LL in price, HL in RSI, old RSI extreme <= 30, momentum reversing
        if min_new < min_old and rsi_new > rsi_old and rsi_old <= 30 and current_rsi > rsi_new:
            bias = "LONG"
            
    # Bearish Divergence check
    if bias == "NONE" and len(swing_highs) >= 2:
        idx_old, max_old, rsi_old = swing_highs[-2]
        idx_new, max_new, rsi_new = swing_highs[-1]
        
        # HH in price, LH in RSI, old RSI extreme >= 70, momentum reversing
        if max_new > max_old and rsi_new < rsi_old and rsi_old >= 70 and current_rsi < rsi_new:
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
    volumes_5m = [c["volume"] for c in klines_5m]
    atr = calculate_atr(highs_5m, lows_5m, closes_5m, 14)[-1]
    
    # Calculate 10-period SMA of Volume
    sma_vol_10 = calculate_sma(volumes_5m, 10)
    
    fvg_found = False
    entry_price = 0.0
    sl_price = 0.0
    
    # Look for FVG in the last 5 candles
    for i in range(-1, -6, -1):
        if len(klines_5m) < abs(i) + 2: continue
        c1 = klines_5m[i-2]
        c2 = klines_5m[i-1]
        c3 = klines_5m[i]
        
        # Apply Smart Money Order Flow (Volume Filter) on the displacement candle (c2)
        # Displacement candle volume must be >= 80% of SMA-10 volume
        idx_c2 = len(volumes_5m) + i - 1  # Get absolute index of c2
        if c2["volume"] < 0.80 * sma_vol_10[idx_c2]:
            continue
            
        range_c3 = c3["high"] - c3["low"]
        latest_c = klines_5m[-1]
        
        if bias == "LONG":
            # Bullish FVG with strong rejection
            if c3["low"] > c1["high"] and c3["close"] > c3["open"] and (c3["close"] - c3["low"]) > (range_c3 * 0.5):
                fvg_top = c3["low"]
                fvg_bottom = c1["high"]
                mitigation_price = fvg_bottom + ((fvg_top - fvg_bottom) * 0.5)
                
                # Check if mitigated
                if latest_c["low"] <= mitigation_price <= latest_c["high"] or (i == -1 and c3["low"] <= mitigation_price):
                    fvg_found = True
                    entry_price = latest_c["close"]
                    sl_price = c1["low"] - (0.5 * atr)
                    break
        else:
            # Bearish FVG with strong rejection
            if c3["high"] < c1["low"] and c3["close"] < c3["open"] and (c3["high"] - c3["close"]) > (range_c3 * 0.5):
                fvg_top = c1["low"]
                fvg_bottom = c3["high"]
                mitigation_price = fvg_bottom + ((fvg_top - fvg_bottom) * 0.5)
                
                # Check if mitigated
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
            "strategy": "QUANTUM_DIVERGENCE"
        }
        
    return {"signal": "NONE"}
