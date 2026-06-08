from app.utils.indicators import calculate_ema, calculate_rsi, calculate_adx, calculate_supertrend, calculate_atr

async def evaluate_supertrend_pullback(client, symbol: str) -> dict:
    """
    ESTRATEGIA B: SUPERTREND PULLBACK V3
    - Temporalidad: 5 Minutos (5M).
    - Macro: EMA 9 > EMA 21, Precio > EMA 50, ADX > 20.
    - Supertrend: (10, 3.0) define tendencia y SL.
    - Momentum: RSI en canal de aceleración (50-70 LONG, 30-50 SHORT).
    - Gatillo: Mecha perfora EMA 21 pero cierra a favor.
    - Entrada por Market Order.
    """
    klines_5m = await client.get_klines(symbol, "5m", 100)
    if not klines_5m or len(klines_5m) < 60: 
        return {"signal": "NONE"}
        
    # Descartar la última vela (está incompleta/abierta y arruina los cálculos de volumen/indicadores)
    klines_5m = klines_5m[:-1]
    
    from app.logger import logger
    
    closes = [c["close"] for c in klines_5m]
    highs = [c["high"] for c in klines_5m]
    lows = [c["low"] for c in klines_5m]
    
    # 1. Indicadores
    ema9 = calculate_ema(closes, 9)[-1]
    ema21 = calculate_ema(closes, 21)[-1]
    ema50 = calculate_ema(closes, 50)[-1]
    
    rsi14 = calculate_rsi(closes, 14)[-1]
    adx14 = calculate_adx(highs, lows, closes, 14)[-1]
    
    supertrend = calculate_supertrend(highs, lows, closes, 10, 3.0)
    st_val = supertrend[-1]["value"]
    st_dir = supertrend[-1]["dir"]  # 1 = LONG (Verde), -1 = SHORT (Rojo)
    
    atr14 = calculate_atr(highs, lows, closes, 14)[-1]
    
    c = klines_5m[-1]  # Última vela cerrada
    
    signal = "NONE"
    entry_price = 0.0
    sl_price = 0.0
    
    # Filtro Rango (Relajado para permitir más operaciones)
    if adx14 > 15:
        # ---------------- LONG LOGIC ----------------
        if ema9 > ema21 and c["close"] > ema50 and st_dir == 1:
            if 50 < rsi14 < 75:
                if c["low"] <= ema9 and c["close"] > ema21:
                    signal = "LONG"
                    entry_price = c["close"]
                    sl_price = entry_price - (1.5 * atr14)
                else:
                    logger.info(f"[{symbol} ST-LONG] Failed Pullback: low={c['low']:.2f} > ema9={ema9:.2f} or close={c['close']:.2f} < ema21={ema21:.2f}")
            else:
                logger.info(f"[{symbol} ST-LONG] Failed RSI: {rsi14:.2f} not in 50-75")
        elif st_dir == 1:
            logger.info(f"[{symbol} ST-LONG] Failed Macro: ema9>ema21={ema9>ema21}, close>ema50={c['close']>ema50}, st_dir={st_dir}")
            
        # ---------------- SHORT LOGIC ----------------
        elif ema9 < ema21 and c["close"] < ema50 and st_dir == -1:
            if 25 < rsi14 < 50:
                if c["high"] >= ema9 and c["close"] < ema21:
                    signal = "SHORT"
                    entry_price = c["close"]
                    sl_price = entry_price + (1.5 * atr14)
                else:
                    logger.info(f"[{symbol} ST-SHORT] Failed Pullback: high={c['high']:.2f} < ema9={ema9:.2f} or close={c['close']:.2f} > ema21={ema21:.2f}")
            else:
                logger.info(f"[{symbol} ST-SHORT] Failed RSI: {rsi14:.2f} not in 25-50")
        elif st_dir == -1:
            logger.info(f"[{symbol} ST-SHORT] Failed Macro: ema9<ema21={ema9<ema21}, close<ema50={c['close']<ema50}, st_dir={st_dir}")
    else:
        logger.info(f"[{symbol} SUPERTREND] Rango/Lateralidad detectada. ADX = {adx14:.2f} (debe ser > 15)")

    if signal != "NONE":
        return {
            "signal": signal,
            "entry_price": entry_price, # Market entry
            "sl_price": sl_price,
            "atr": abs(entry_price - sl_price) / 2.5, # Dummy ATR calculation, engine parses target_dist
            "strategy": "SUPERTREND_PULLBACK_V3",
            "is_limit": False
        }
        
    return {"signal": "NONE"}
