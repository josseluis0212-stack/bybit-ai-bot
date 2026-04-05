import asyncio
import logging
import sys
from execution_engine.executor import executor
from strategy.market_scanner import market_scanner
from strategy.base_strategy import strategy
from api.bybit_client import bybit_client

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Iniciando llenado forzado de operaciones hasta el límite (10)...")
    
    # Obtener tickers para buscar señales frescas
    tickers = bybit_client.get_tickers()
    if not tickers:
        logger.error("No se pudieron obtener tickers.")
        return

    count_opened = 0
    # Obtenemos posiciones actuales para saber cuántas faltan
    pos = bybit_client.get_positions()
    current_count = len(pos['result']['list']) if pos and pos.get('retCode') == 0 else 0
    logger.info(f"Operaciones actuales en Bybit: {current_count}")
    
    needed = 10 - current_count
    if needed <= 0:
        logger.info("Ya se alcanzó o superó el límite de 10 operaciones.")
        # Intentar abrir una más para probar el bloqueo
        needed = 1
    
    logger.info(f"Intentando abrir {needed} operaciones adicionales...")
    
    for item in tickers:
        if count_opened >= needed + 1: # +1 para probar el bloqueo
            break
            
        symbol = item['symbol']
        # Evitar abrir el mismo si ya está (simplificado)
        if any(p['symbol'] == symbol for p in pos['result']['list']):
            continue

        df = await market_scanner.get_klines_as_df(symbol)
        if df is not None and not df.empty:
            sig = strategy.analyze(symbol, df)
            if sig:
                logger.info(f"Procesando señal para {symbol}...")
                success = await executor.try_execute_signal(sig)
                if success:
                    count_opened += 1
                    logger.info(f"Operación {count_opened} abierta exitosamente.")
                else:
                    logger.warning(f"No se pudo abrir operación para {symbol} (posiblemente bloqueada por límite).")
        
        await asyncio.sleep(0.5)

if __name__ == '__main__':
    asyncio.run(main())
