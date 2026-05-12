import asyncio
import logging
import os
import socketio
from datetime import datetime
from aiohttp import web
from config.settings import settings
from api.bybit_client import bybit_client
from database.db_manager import db_manager
from strategy.market_scanner import market_scanner
from strategy.ema_strategy import ema_strategy
from execution_engine.executor import executor

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estado global del bot
BOT_ACTIVE = True

# Manejador para enviar logs al dashboard via Socket.io
class SocketIOLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            color = "text-text-muted"
            if "SE\u00d1AL" in log_entry: color = "neon-text-green font-black"
            elif "Error" in log_entry or "FALLIDA" in log_entry: color = "text-danger"
            elif "Escaneo" in log_entry: color = "text-cyan"
            
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(sio.emit("bot_log", {"msg": log_entry, "color": color}))
            except RuntimeError:
                # No hay loop corriendo, ignoramos el log de socket
                pass
        except:
            pass

socket_handler = SocketIOLogHandler()
socket_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger().addHandler(socket_handler)

sio = socketio.AsyncServer(async_mode="aiohttp")


@sio.event
async def connect(sid, environ):
    logger.info(f"Cliente conectado: {sid}")
    await sio.emit(
        "bot_status", {"status": "connected", "message": "Bot activo"}, to=sid
    )


@sio.event
async def disconnect(sid):
    logger.info(f"Cliente desconectado: {sid}")


@sio.event
async def reset_bot(sid, data):
    logger.info("Reset recibido via socket.io")
    try:
        await executor.emergency_close_all()
        db_manager.reset_all_stats()
        await sio.emit(
            "reset_response", {"status": "success", "message": "Reset completo"}
        )
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error en reset: {e}")
        await sio.emit("reset_response", {"status": "error", "message": str(e)})
        return {"status": "error"}


@sio.event
async def trigger_scan(sid, data):
    logger.info("Escaneo manual via socket.io")
    try:
        signals = await market_scanner.scan_market()
        for sig in signals:
            await executor.try_execute_signal(sig)
        await sio.emit("scan_response", {"status": "success", "signals": len(signals)})
        return {"status": "success", "signals": len(signals)}
    except Exception as e:
        logger.error(f"Error en escaneo: {e}")
        return {"status": "error"}


@sio.event
async def panic_close(sid, data):
    logger.info("Panic close via socket.io")
    try:
        await executor.emergency_close_all()
        await sio.emit(
            "panic_response", {"status": "success", "message": "Panico ejecutado"}
        )
        return {"status": "success"}
    except Exception as e:
        return {"status": "error"}


@sio.event
async def get_stats(sid, data):
    from analytics.analytics_manager import analytics_manager

    stats = analytics_manager.get_dashboard_stats()
    await sio.emit("stats_response", stats, to=sid)
    return stats


async def bot_loop():
    logger.info("🚀 Iniciando ANTIGRAVITY EMA v15 Alpha — PRODUCCIÓN")
    logger.info(
        f"Parámetros: {settings.LEVERAGE}x | Capital/Trade: {settings.TRADE_AMOUNT_USDT} USDT | Max Trades: {settings.MAX_CONCURRENT_TRADES}"
    )

    logger.info("Estrategia: EMA 9/21/89 | M5 Trend Filter | BE 45% | TS 85%")

    while True:
        try:
            if not BOT_ACTIVE:
                await asyncio.sleep(5)
                continue

            logger.info("🔍 [CICLO] Monitoreando posiciones y analizando oportunidades...")
            logger.info("📡 Bot Escaneando...") # Log para confirmar vida en terminal
            await executor.cleanup_old_orders()
            await executor.check_open_positions()
            
            logger.info(f"📡 [SCANNER] Escaneando mercado: Top {settings.TOP_COINS_LIMIT} Monedas (>$500k vol)...")
            signals = await market_scanner.scan_market()

            if signals:
                logger.info(f"✨ [SEÑAL] Se han detectado {len(signals)} oportunidades potenciales!")
                for sig in signals:
                    logger.info(
                        f"Ejecutando: {sig['symbol']} {sig['signal']} @ {sig['entry_price']}"
                    )
                    result = await executor.try_execute_signal(sig)
                    logger.info(
                        f"Resultado {sig['symbol']}: {'EXITOSA' if result else 'FALLIDA'}"
                    )
                    await asyncio.sleep(0.5)

            await sio.emit("heartbeat", {"timestamp": datetime.now().isoformat()})
            await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)

        except Exception as e:
            logger.warning(f"[Scanner] loop error: {e}")
            await asyncio.sleep(60)


async def keep_alive():
    """Pings the bot itself to prevent Render Free Tier from sleeping."""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        # Intentar construirla si no está la variable (algunas veces no está por defecto)
        # O simplemente omitir si no estamos en Render
        return

    logger.info(f"🛠️ Sistema Keep-Alive activado para: {url}")
    await asyncio.sleep(60) # Esperar a que el server suba
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(f"{url}/health") as resp:
                    if resp.status == 200:
                        logger.info("💤 Keep-alive: El bot sigue despierto.")
            except Exception as e:
                logger.debug(f"Keep-alive error: {e}")
            await asyncio.sleep(600) # Cada 10 minutos (Render duerme a los 15)


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


async def handle_trigger_scan(request):
    try:
        signals = await market_scanner.scan_market()
        if signals:
            for sig in signals:
                await executor.try_execute_signal(sig)
        return web.json_response({"status": "success", "signals_found": len(signals)})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_panic_close(request):
    success = await executor.emergency_close_all()
    if success:
        return web.json_response({"status": "success"})
    return web.json_response({"status": "error"}, status=500)


async def handle_reset(request):
    from analytics.analytics_manager import analytics_manager
    try:
        await executor.emergency_close_all()
        db_manager.reset_all_stats()
        analytics_manager.reset_date_now()
        executor.trade_state.clear()
        executor.cooldowns.clear()
        from risk_management.risk_manager import risk_manager
        risk_manager.daily_pnl = 0.0
        return web.json_response({"status": "success", "message": "Reset completo — Sistema v15 Alpha en ceros"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_performance(request):
    from analytics.analytics_manager import analytics_manager
    stats = analytics_manager.get_dashboard_stats()
    return web.json_response(stats)


async def handle_trades(request):
    active_positions = bybit_client.get_active_positions()
    trades = []
    
    # Obtener IDs de la DB para mapear estatus
    open_trades_db = db_manager.get_open_trades()
    db_map = {t.symbol: t.id for t in open_trades_db}

    for p in active_positions:
        symbol = p["symbol"]
        trade_id = db_map.get(symbol)
        status_flags = executor.get_trade_status(trade_id) if trade_id else {"be_active": False, "ts_active": False}
        
        trades.append({
            "symbol": symbol,
            "side": p["side"],
            "entry": float(p["avgPrice"]),
            "qty": float(p["size"]),
            "pnl": float(p["unrealisedPnl"]),
            "be_active": status_flags["be_active"],
            "ts_active": status_flags["ts_active"]
        })
    return web.json_response(trades)



async def handle_history(request):
    from analytics.analytics_manager import analytics_manager
    history = []
    
    # 1. Intentar obtener de la DB local (tiene motivos detallados)
    try:
        import sqlite3
        import pandas as pd
        db_path = os.path.join('database', 'trading_bot.db')
        conn = sqlite3.connect(db_path)
        df_db = pd.read_sql_query("SELECT * FROM trades WHERE status='CLOSED' ORDER BY close_time DESC LIMIT 50", conn)
        conn.close()

        
        if not df_db.empty:
            for _, row in df_db.iterrows():
                history.append({
                    "symbol": row["symbol"],
                    "side": row["side"],
                    "entry": float(row["entry_price"]),
                    "exit": float(row["exit_price"]) if row["exit_price"] else 0,
                    "pnl_usdt": float(row["pnl_usdt"]),
                    "reason": row["close_reason"] or "Closed"
                })
            return web.json_response(history)
    except Exception as e:
        logger.error(f"Error consultando DB local para historial: {e}")

    # 2. Fallback a Bybit Sync (si la DB está vacía o falla)
    df = analytics_manager._fetch_trades()
    if df is not None and not df.empty:
        df_last = df.sort_values("updatedTime", ascending=False).head(50)
        for _, row in df_last.iterrows():
            history.append({
                "symbol": row["symbol"],
                "side": row["side"],
                "entry": float(row["avgEntryPrice"]) if "avgEntryPrice" in row else 0,
                "exit": float(row["avgExitPrice"]) if "avgExitPrice" in row else 0,
                "pnl_usdt": float(row["closedPnl"]),
                "reason": "Bybit Sync"
            })
    return web.json_response(history)



async def handle_health_check(request):
    return web.Response(text="Bot is running!")


async def httpd_handle_static_index(request):
    index_path = os.path.join(os.path.dirname(__file__), 'dashboard', 'index.html')
    return web.FileResponse(index_path)


async def init_web_server():
    app = web.Application()
    sio.attach(app)

    app.router.add_get("/", httpd_handle_static_index)
    app.router.add_get("/health", handle_health_check)
    app.router.add_get("/api/status", handle_status)
    app.router.add_post("/api/start", handle_start)
    app.router.add_post("/api/stop", handle_stop)
    app.router.add_get("/api/trigger-scan", handle_trigger_scan)
    app.router.add_post("/api/panic-close", handle_panic_close)
    app.router.add_post("/api/reset", handle_reset)
    app.router.add_get("/api/history", handle_history)
    app.router.add_get("/api/performance", handle_performance)
    app.router.add_get("/api/trades", handle_trades)

    app.router.add_get("/app", httpd_handle_static_index)
    app.router.add_get("/app/", httpd_handle_static_index)
    app.router.add_get("/app/index.html", httpd_handle_static_index)

    dashboard_path = os.path.join(os.path.dirname(__file__), 'dashboard')
    app.router.add_static('/static/', path=dashboard_path, name='static')

    # Sincronización inicial y limpieza de TP reales
    await executor.force_sync_at_startup()
    
    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", "7860"))  # 7860 = Hugging Face Spaces default
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Servidor web + Socket.IO activo en puerto {port}")


async def main():
    asyncio.create_task(bot_loop())
    asyncio.create_task(keep_alive())
    await init_web_server()

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
