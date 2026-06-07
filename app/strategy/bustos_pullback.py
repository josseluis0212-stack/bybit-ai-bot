from app.utils.indicators import calculate_ema, calculate_sma

async def evaluate_bustos_pullback(client, symbol: str) -> dict:
    """
    Estrategia "Riesgo 99.9% Eliminado" (Federico Bustos)
    - Trend: 1H > EMA 50
    - Trigger: 5M pullback tocando EMA 21
    - Riesgo: Stop Loss debajo de SMA 50
    - TP: Último máximo (con RR > 1)
    """
    # 1. Macro Trend (1H)
    klines_1h = await client.get_klines(symbol, "1h", 100)
    if not klines_1h or len(klines_1h) < 50: return {"signal": "NONE"}
    closes_1h = [c["close"] for c in klines_1h]
    ema50_1h = calculate_ema(closes_1h, 50)[-1]
    current_close_1h = closes_1h[-1]
    
    bias = "LONG" if current_close_1h > ema50_1h else "SHORT"
    
    # 2. Ejecución (5M)
    klines_5m = await client.get_klines(symbol, "5m", 60)
    if not klines_5m or len(klines_5m) < 55: return {"signal": "NONE"}
    
    closes_5m = [c["close"] for c in klines_5m]
    highs_5m = [c["high"] for c in klines_5m]
    lows_5m = [c["low"] for c in klines_5m]
    
    ema21_5m = calculate_ema(closes_5m, 21)[-1]
    sma50_5m = calculate_sma(closes_5m, 50)[-1]
    
    c = klines_5m[-1]  # La vela que acaba de cerrar
    
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    signal = "NONE"
    
    if bias == "LONG":
        # Condición de tendencia en 5M: EMA 21 debe estar por encima de SMA 50
        if ema21_5m > sma50_5m:
            # Pullback a la EMA 21: El low tocó o cruzó la EMA 21, pero el cierre se mantuvo por encima
            if c["low"] <= ema21_5m and c["close"] > ema21_5m:
                entry_price = c["close"]  # Entramos al mercado inmediatamente
                sl_price = sma50_5m * 0.9995  # SL ligeramente por debajo de la SMA 50
                
                # Buscar el máximo reciente (Take Profit)
                recent_high = max(highs_5m[-20:])
                
                # Verificar asimetría (Risk/Reward mínimo de 1:1)
                risk = entry_price - sl_price
                reward = recent_high - entry_price
                
                if risk > 0 and reward >= risk:
                    tp_price = recent_high
                    signal = "LONG"
    else:
        # Condición de tendencia bajista en 5M: EMA 21 por debajo de SMA 50
        if ema21_5m < sma50_5m:
            # Pullback a la EMA 21: El high tocó o cruzó la EMA 21, pero el cierre se mantuvo por debajo
            if c["high"] >= ema21_5m and c["close"] < ema21_5m:
                entry_price = c["close"]
                sl_price = sma50_5m * 1.0005  # SL ligeramente por encima de la SMA 50
                
                # Buscar el mínimo reciente (Take Profit)
                recent_low = min(lows_5m[-20:])
                
                risk = sl_price - entry_price
                reward = entry_price - recent_low
                
                if risk > 0 and reward >= risk:
                    tp_price = recent_low
                    signal = "SHORT"
                    
    if signal != "NONE":
        return {
            "signal": signal,
            "entry_price": entry_price,
            "sl_price": sl_price,
            # we also return tp_price so the engine can use it, though engine uses ATR currently
            "tp_price": tp_price,
            "atr": abs(entry_price - sl_price) / 2.5,  # Fake ATR to satisfy engine logic if needed
            "strategy": "BUSTOS_PULLBACK"
        }
        
    return {"signal": "NONE"}
