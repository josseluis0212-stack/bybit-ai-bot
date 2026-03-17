import asyncio
import logging
import os
from aiohttp import web
from config.settings import settings
from api.bybit_client import bybit_client
from database.db_manager import db_manager
from strategy.market_scanner import market_scanner
from execution_engine.executor import executor

# Configurar logging básico
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def bot_loop():
    logger.info("Iniciando Trading Bot Profesional Demo (Loop Principal)...")
    logger.info(f"Parámetros: {settings.LEVERAGE}x | Capital/Trade: {settings.TRADE_AMOUNT_USDT} USDT | Max Trades: {settings.MAX_CONCURRENT_TRADES}")
    
    # Sincronización forzada al inicio: cerrar trades "fantasma" de runs anteriores
    logger.info("Ejecutando sincronización inicial con Bybit...")
    await executor.force_sync_at_startup()
    
    while True:
        try:
            logger.info("--- Iniciando ciclo de escaneo ---")
            
            # 0. Sincronizar y cerrar posiciones abiertas que hayan tocado SL/TP
            await executor.check_open_positions()
            
            # 1. Escanear el mercado (TOP 50 en volumen para optimizar API)
            signals = await market_scanner.scan_market()
            
            # 2. Procesar señales encontradas
            if signals:
                logger.info(f"Procesando {len(signals)} señales generadas...")
                for sig in signals:
                    await executor.try_execute_signal(sig)
            else:
                logger.info("Sin señales en este ciclo.")
            
            logger.info("Ciclo completado. Pausando por 5 minutos...")
            # En producción puede ser cada 1, 5 o 15 minutos exactos usando un scheduler
            await asyncio.sleep(300) 
            
        except Exception as e:
            logger.error(f"Error crítico en el bucle principal: {e}")
            await asyncio.sleep(60)

async def handle_status(request):
    """Devuelve el estado general del bot y balance"""
    balance_info = bybit_client.get_wallet_balance()
    active_positions = bybit_client.get_active_positions()
    
    data = {
        "status": "Running",
        "balance": balance_info['result']['list'][0]['coin'] if balance_info.get('retCode') == 0 else [],
        "active_trades_count": len(active_positions),
        "leverage": settings.LEVERAGE,
        "strategy": "Institutional SMC (OB + FVG)"
    }
    return web.json_response(data)

async def handle_trades(request):
    """Devuelve el historial y trades abiertos desde la DB"""
    open_trades = db_manager.get_open_trades()
    # Para fines de simplificación, tomamos los últimos 50 trades totales
    session = db_manager.Session()
    from database.models import Trade
    all_trades = session.query(Trade).order_by(Trade.id.desc()).limit(50).all()
    
    trades_list = []
    for t in all_trades:
        trades_list.append({
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "status": t.status,
            "entry": t.entry_price,
            "exit": t.exit_price,
            "pnl_usdt": t.pnl_usdt,
            "pnl_pct": t.pnl_pct,
            "reason": t.close_reason,
            "time": t.close_time.isoformat() if t.close_time else None
        })
    session.close()
    return web.json_response(trades_list)

async def init_web_server():
    """Inicia un servidor web con API y health check"""
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    app.router.add_get('/api/status', handle_status)
    app.router.add_get('/api/trades', handle_trades)
    
    # Servir archivos estáticos (para el dashboard que construiremos)
    if os.path.exists('dashboard'):
        app.router.add_static('/app', 'dashboard')
        logger.info("Ruta /app habilitada para el dashboard móvil.")
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", "10000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Servidor web con API iniciado en el puerto {port}")

async def main():
    # Iniciamos el servidor web y el bot concurrentemente
    await asyncio.gather(
        init_web_server(),
        bot_loop()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
