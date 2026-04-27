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
from strategy.base_strategy import strategy
from execution_engine.executor import executor

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Manejador para enviar logs al dashboard via Socket.io
class SocketIOLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            color = "text-text-muted"
            if "SEÑAL" in log_entry: color = "neon-text-green font-black"
            elif "Error" in log_entry or "FALLIDA" in log_entry: color = "text-danger"
            elif "Escaneo" in log_entry: color = "text-cyan"
            
            asyncio.create_task(sio.emit("bot_log", {"msg": log_entry, "color": color}))
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
    logger.info("Iniciando Trading Bot Profesional Demo...")
    logger.info(
        f"Parámetros: {settings.LEVERAGE}x | Capital/Trade: {settings.TRADE_AMOUNT_USDT} USDT | Max Trades: {settings.MAX_CONCURRENT_TRADES}"
    )

    await executor.force_sync_at_startup()

    logger.info(
        f"Bot Configurado: Killzones={settings.KILLZONE_FILTER}, HTF_Confluence={settings.HTF_CONFLUENCE}"
    )

    while True:
        try:
            logger.info("🔍 [CICLO] Monitoreando posiciones y analizando oportunidades...")
            await executor.check_open_positions()
            
            logger.info("📡 [SCANNER] Escaneando mercado con filtros Elite (5m / $10M)...")
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
            await asyncio.sleep(300)

        except Exception as e:
            logger.error(f"Error en bucle: {e}")
            await asyncio.sleep(60)


async def handle_status(request):
    balance_info = bybit_client.get_wallet_balance()
    active_positions = bybit_client.get_active_positions()

    status = {
        "status": "Running",
        "strategy": "Institutional SMC Quantum v5.0",
        "balance": balance_info["result"]["list"][0]["coin"]
        if balance_info and balance_info.get("retCode") == 0
        else [],
        "active_trades_count": len(active_positions),
        "leverage": settings.LEVERAGE,
    }
    return web.json_response(status)


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
        return web.json_response({"status": "success", "message": "Reset completo"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_performance(request):
    from analytics.analytics_manager import analytics_manager
    stats = analytics_manager.get_dashboard_stats()
    return web.json_response(stats)


async def handle_trades(request):
    active_positions = bybit_client.get_active_positions()
    trades = []
    for p in active_positions:
        trades.append({
            "symbol": p["symbol"],
            "side": p["side"],
            "entry": float(p["avgPrice"]),
            "qty": float(p["size"]),
            "pnl": float(p["unrealisedPnl"])
        })
    return web.json_response(trades)


async def handle_history(request):
    closed_trades = db_manager.get_history(limit=50)
    history = []
    for t in closed_trades:
        history.append(
            {
                "symbol": t.symbol,
                "side": t.side,
                "entry": t.entry_price,
                "exit": t.exit_price,
                "pnl_usdt": t.pnl_usdt,
                "reason": t.close_reason,
            }
        )
    return web.json_response(history)


async def handle_health_check(request):
    return web.Response(text="Bot is running!")


async def httpd_handle_static_index(request):
    index_path = os.path.join(os.path.dirname(__file__), 'dashboard', 'index.html')
    return web.FileResponse(index_path)


async def init_web_server():
    app = web.Application()
    sio.attach(app)

    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/trigger-scan", handle_trigger_scan)
    app.router.add_post("/api/panic-close", handle_panic_close)
    app.router.add_get("/api/reset", handle_reset)
    app.router.add_post("/api/reset", handle_reset)
    app.router.add_get("/api/history", handle_history)
    app.router.add_get("/api/performance", handle_performance)
    app.router.add_get("/api/trades", handle_trades)

    app.router.add_get("/app", httpd_handle_static_index)
    app.router.add_get("/app/", httpd_handle_static_index)
    app.router.add_get("/app/index.html", httpd_handle_static_index)

    dashboard_path = os.path.join(os.path.dirname(__file__), 'dashboard')
    app.router.add_static('/static/', path=dashboard_path, name='static')

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Servidor web + Socket.IO activo en puerto {port}")


async def main():
    asyncio.create_task(bot_loop())
    await init_web_server()

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
