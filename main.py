import asyncio
import logging
import os
import time
from aiohttp import web
from config.settings import settings
from strategy.market_scanner import market_scanner
from execution_engine.executor import executor
import aiohttp

# Configurar logging básico
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def render_heartbeat():
    """
    Servicio de Supervivencia: Evita que Render apague la instancia por inactividad.
    Realiza un self-ping cada 10 minutos.
    """
    port = os.environ.get("PORT", "10000")
    url = f"http://localhost:{port}/health"
    await asyncio.sleep(60) # Esperar a que el servidor inicie
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.info("💓 Heartbeat: Sistema activo y saludable.")
                    else:
                        logger.warning(f"💓 Heartbeat: Respuesta inesperada {response.status}")
            except Exception as e:
                logger.error(f"💓 Heartbeat Error: {e}")
            
            await asyncio.sleep(600) # 10 minutos

async def bot_loop():
    logger.info("🚀 INICIANDO HYPER-QUANT ULTRA V5.0 (SMC / FVG)...")
    from notifications.telegram_bot import telegram_notifier
    await telegram_notifier.send_message("🚀 **Hyper-Quant Ultra V5.0 Iniciado**\n\nEl sistema está en línea con filtrado institucional de **Alta Liquidez (> $10M)**.\n\nEstrategia: Smart Money Concepts (SMC)\nLógica: Liquidity Sweeps + Fair Value Gaps\nBias: Filtro de Tendencia 15m")
    
    while True:
        start_time = time.time()
        try:
            logger.info("--- [Ciclo de Escaneo de Alta Frecuencia] ---")
            
            # 0. Sincronizar y procesar cierres (TP/SL)
            # Nota: El user solicitó quitar el Time-Exit de 15m, lo cual ya se hizo en executor.py
            await executor.check_open_positions()
            
            # 1. Escanear el mercado completo
            signals = await market_scanner.scan_market()
            
            # 2. Procesar señales
            if signals:
                logger.info(f"Procesando {len(signals)} señales encontradas...")
                for sig in signals:
                    await executor.try_execute_signal(sig)
            
            # Cálculo de tiempo para mantener el ciclo cerca de 60s
            elapsed = time.time() - start_time
            sleep_time = max(1, 60 - elapsed)
            
            logger.info(f"Ciclo completado en {elapsed:.1f}s. Durmiendo {sleep_time:.1f}s...")
            await asyncio.sleep(sleep_time) 
            
        except Exception as e:
            logger.error(f"Error crítico en Hyper-Quant Loop: {e}")
            await asyncio.sleep(60)

async def handle_health_check(request):
    return web.Response(text="Hyper-Quant V3 is alive! 🚀")

async def init_web_server():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", "10000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Servidor de supervivencia iniciado en el puerto {port}")

async def main():
    # Iniciamos el servidor de salud, el heartbeat y el bucle del bot
    await asyncio.gather(
        init_web_server(),
        render_heartbeat(),
        bot_loop()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
    except Exception as e:
        logger.error(f"Falla catastrófica al iniciar: {e}")
