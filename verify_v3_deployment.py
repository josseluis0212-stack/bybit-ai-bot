import asyncio
import logging
from strategy.market_scanner import market_scanner
from execution_engine.executor import executor
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY_V3")

async def verify_one_cycle():
    logger.info("--- INICIANDO VERIFICACIÓN DE CICLO ÚNICO HYPER-QUANT V3 ---")
    
    # 1. Simular chequeo de posiciones
    logger.info("Paso 1: Verificando posiciones actuales...")
    await executor.check_open_positions()
    
    # 2. Escaneo de prueba (limitado a 5 pares para velocidad)
    logger.info("Paso 2: Escaneando una muestra del mercado...")
    # Modificamos temporalmente la lista para el test
    test_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT"]
    
    signals = []
    for symbol in test_symbols:
        logger.info(f"Analizando {symbol}...")
        # Obtenemos los klines y analizamos
        from api.bybit_client import bybit_client
        klines = bybit_client.get_klines(symbol, "1", limit=200)
        if klines:
            import pandas as pd
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            from strategy.base_strategy import strategy
            signal = strategy.analyze(symbol, df)
            if signal:
                logger.info(f"🎯 ¡SEÑAL DETECTADA! {symbol} -> {signal}")
                signals.append({'symbol': symbol, 'signal': signal, 'entry_price': df.iloc[-1]['close']})
    
    if not signals:
        logger.info("No se detectaron señales en esta muestra (lo cual es normal si el mercado no está en extremos).")
    else:
        logger.info(f"Se detectaron {len(signals)} señales. El motor de ejecución está LISTO.")

    logger.info("--- VERIFICACIÓN COMPLETADA ---")

if __name__ == "__main__":
    asyncio.run(verify_one_cycle())
