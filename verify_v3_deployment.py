import asyncio
import logging
from strategy.market_scanner import market_scanner
from execution_engine.executor import executor
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY_V3")

async def verify_one_cycle():
    logger.info("--- INICIANDO VERIFICACIÓN DE ESCANEO GLOBAL HYPER-QUANT V3 ---")
    import time
    start = time.time()
    
    # 1. Simular chequeo de posiciones
    await executor.check_open_positions()
    
    # 2. Escaneo Global Real
    logger.info("Paso 2: Iniciando escaneo de TODO el mercado (Paralelo)...")
    signals = await market_scanner.scan_market()
    
    end = time.time()
    duration = end - start
    
    logger.info(f"--- VERIFICACIÓN COMPLETADA en {duration:.1f}s ---")
    
    if duration > 50:
        logger.warning("ALERTA: El escaneo tardó casi 60s. Podría haber solapamiento en el loop.")
    else:
        logger.info("RENDIMIENTO ÓPTIMO: El escaneo encaja perfectamente en el ciclo de 1m.")

if __name__ == "__main__":
    asyncio.run(verify_one_cycle())

if __name__ == "__main__":
    asyncio.run(verify_one_cycle())
