
async def handle_status(request):
    balance_info = bybit_client.get_wallet_balance()
    active_positions = bybit_client.get_active_positions()

    status = {
        "status": "Running" if BOT_ACTIVE else "Stopped",
        "strategy": "Triple EMA Pro v15 Alpha (9/21/89) — Render.com",
        "balance": [c for c in balance_info["result"]["list"][0]["coin"] if c["coin"] in ["USDT", "USDC"]]
        if balance_info and balance_info.get("retCode") == 0
        else [],
        "usdt_balance": next((float(c['walletBalance']) for c in balance_info["result"]["list"][0]["coin"] if c["coin"] == "USDT"), 0) if balance_info and balance_info.get("retCode") == 0 else 0,
        "usdc_balance": next((float(c['walletBalance']) for c in balance_info["result"]["list"][0]["coin"] if c["coin"] == "USDC"), 0) if balance_info and balance_info.get("retCode") == 0 else 0,
        "active_trades_count": len(active_positions),
        "leverage": settings.LEVERAGE,
        "bot_active": BOT_ACTIVE,
        "config": {
            "trade_amount": settings.TRADE_AMOUNT_USDT,
            "atr_sl": settings.ATR_MULTIPLIER_SL,
            "atr_tp": settings.ATR_MULTIPLIER_TP,
            "be_pct": settings.BREAKEVEN_ACTIVATION_PCT,
            "ts_pct": settings.TRAILING_STOP_ACTIVATION_PCT
        }
    }
    return web.json_response(status)


async def handle_start(request):
    global BOT_ACTIVE
    BOT_ACTIVE = True
    logger.warning(f"🚀 [BOT_CONTROL] Bot ACTIVADO desde: {request.remote}")
    return web.json_response({"status": "success", "message": "Bot activado correctamente"})


async def handle_stop(request):
    global BOT_ACTIVE
    BOT_ACTIVE = False
    logger.warning(f"🛑 [BOT_CONTROL] Bot DETENIDO desde: {request.remote} | Agente: {request.headers.get('User-Agent')}")
    # No cerramos posiciones automáticamente en STOP, solo pausamos el escaneo
    # await executor.emergency_close_all() 
    return web.json_response({"status": "success", "message": "Bot detenido (Escaneo pausado)"})
