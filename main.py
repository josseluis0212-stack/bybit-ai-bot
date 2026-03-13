import asyncio
import logging
import os
from aiohttp import web
from config.settings import settings
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

async def handle_health_check(request):
    """Responde 200 OK para que Render sepa que la app está viva"""
    return web.Response(text="Bot is running! 🚀")

async def init_web_server():
    """Inicia un servidor web dummy para cumplir con los requisitos de Render (Web Service Free)"""
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", "10000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Servidor web dummy iniciado en el puerto {port}")

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
