from app.utils.indicators import calculate_atr, calculate_sma

async def evaluate_v10_pro(client, symbol: str) -> dict:
    """
    ESTRATEGIA A: QUANTUM SMC V10 PRO (Vacíos de Liquidez)
    - Temporalidad: 5 Minutos (5M).
    - Liquidity Sweep (Barrida de últimos 15 mínimos/máximos).
    - Volumen de desplazamiento > 1.25x SMA(15)
    - FVG (Fair Value Gap) mitigation al 50%.
    - SL a 2.0x ATR.
    """
    # Descargar 100 velas para tener data de sobra para historial (Sweep) y SMA
    klines_5m = await client.get_klines(symbol, "5m", 100)
    if not klines_5m or len(klines_5m) < 40: 
        return {"signal": "NONE"}
        
    # Descartar la última vela (está incompleta/abierta y arruina los cálculos de volumen)
    klines_5m = klines_5m[:-1]
    
    from app.logger import logger
    
    # Extraer arrays para cálculos
    highs = [c["high"] for c in klines_5m]
    lows = [c["low"] for c in klines_5m]
    closes = [c["close"] for c in klines_5m]
    volumes = [c["volume"] for c in klines_5m]
    
    atr = calculate_atr(highs, lows, closes, 14)[-1]
    sma_vol_15 = calculate_sma(volumes, 15)
    
    # Analizamos la estructura de 3 velas más reciente:
    # Vela 1 = klines_5m[-3]
    # Vela 2 = klines_5m[-2]
    # Vela 3 = klines_5m[-1]  (La vela que acaba de cerrar)
    
    c1 = klines_5m[-3]
    c2 = klines_5m[-2]
    c3 = klines_5m[-1]
    
    # Volumen de la Vela 3 (Desplazamiento) vs SMA 15
    # SMA de volumen correspondiente a la vela 3
    vol_sma3 = sma_vol_15[-1]
    
    signal = "NONE"
    entry_price = 0.0
    sl_price = 0.0
    
    # ------------------ LONG LOGIC ------------------
    # 1. Filtro de Volumen: Vela 3 > 1.15x SMA(15)
    if c3["volume"] > 1.15 * vol_sma3:
        # 2. Liquidity Sweep: Mínimo de c1 o c3 rompió el mínimo de las 15 velas anteriores a c1
        # Obtenemos las 15 velas antes de c1 (índices -18 a -4)
        history_15_low = min([k["low"] for k in klines_5m[-18:-3]])
        
        sweep_valid_long = (c1["low"] < history_15_low) or (c3["low"] < history_15_low)
        
        if sweep_valid_long:
            # 3. Fair Value Gap: Mínimo de c2 > Máximo de c1 AND c3 Verde
            if c2["low"] > c1["high"] and c3["close"] > c3["open"]:
                signal = "LONG"
                # Limit Order mitigation at 50% FVG
                entry_price = (c2["low"] + c1["high"]) / 2.0
                sl_price = entry_price - (2.0 * atr)
            else:
                logger.info(f"[{symbol} SMC-LONG] Failed FVG: c2_low={c2['low']:.2f} <= c1_high={c1['high']:.2f} or not green")
        else:
            logger.info(f"[{symbol} SMC-LONG] Failed Sweep: lows not < {history_15_low:.2f}")
    else:
        logger.info(f"[{symbol} SMC] Failed Volume: vol_c3={c3['volume']:.2f} <= 1.15*SMA({vol_sma3:.2f})")

    # ------------------ SHORT LOGIC ------------------
    if signal == "NONE":
        if c3["volume"] > 1.15 * vol_sma3:
            # 2. Liquidity Sweep: Máximo de c1 o c3 rompió el máximo de las 15 velas anteriores a c1
            history_15_high = max([k["high"] for k in klines_5m[-18:-3]])
            
            sweep_valid_short = (c1["high"] > history_15_high) or (c3["high"] > history_15_high)
            
            if sweep_valid_short:
                # 3. Fair Value Gap: Máximo de c2 < Mínimo de c1 AND c3 Roja
                if c2["high"] < c1["low"] and c3["close"] < c3["open"]:
                    signal = "SHORT"
                    entry_price = (c2["high"] + c1["low"]) / 2.0
                    sl_price = entry_price + (2.0 * atr)
                else:
                    logger.info(f"[{symbol} SMC-SHORT] Failed FVG: c2_high={c2['high']:.2f} >= c1_low={c1['low']:.2f} or not red")
            else:
                logger.info(f"[{symbol} SMC-SHORT] Failed Sweep: highs not > {history_15_high:.2f}")

    # Invalidation Check: If current close or low touched the SL before we can even place the limit
    if signal == "LONG" and c3["close"] <= sl_price:
        signal = "NONE"
    if signal == "SHORT" and c3["close"] >= sl_price:
        signal = "NONE"

    if signal != "NONE":
        return {
            "signal": signal,
            "entry_price": entry_price, # Limit price for engine to wait for
            "sl_price": sl_price,
            "atr": atr,
            "strategy": "SMC_V10_PRO",
            "is_limit": True
        }
        
    return {"signal": "NONE"}
