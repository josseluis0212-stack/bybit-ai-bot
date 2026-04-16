import asyncio
import pandas as pd
import logging
import sys
import os

# Añadir el path del proyecto para importar los módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'trading-bot-pro')))

from strategy.base_strategy import strategy
from api.bybit_client import bybit_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_logic():
    symbol = "SOLUSDT"
    logger.info(f"🧪 Probando Lógica V9.2 en {symbol}...")
    
    # Simular dataframes
    from strategy.market_scanner import MarketScanner
    scanner = MarketScanner()
    
    df_1m = await scanner.get_klines_as_df(symbol, interval="1")
    df_15m = await scanner.get_klines_as_df(symbol, interval="15")
    df_1h = await scanner.get_klines_as_df(symbol, interval="60")
    
    if df_1m is not None and df_15m is not None and df_1h is not None:
        logger.info(f"✅ Datos obtenidos. Procesando señales...")
        
        # Simular lo que hace el MarketScanner 9.2
        import ta
        ema_1h = ta.trend.ema_indicator(df_1h['close'], window=100)
        last_price_1h = df_1h.iloc[-30:]['close'].mean() # Poner algo de contexto
        last_ema_1h = ema_1h.iloc[-1]
        macro_trend = "LONG" if df_1h.iloc[-1]['close'] > last_ema_1h else "SHORT"
        
        logger.info(f"Tendencia 1H: {macro_trend} (Price: {df_1h.iloc[-1]['close']:.2f}, EMA100: {last_ema_1h:.2f})")
        
        signal = strategy.analyze(symbol, df_1m, df_15m)
        
        if signal:
            logger.info(f"🎯 ¡SEÑAL DETECTADA!")
            logger.info(f"Tipo: {signal['signal']}")
            logger.info(f"Razón: {signal['reason']}")
            logger.info(f"Bias Estrategia: {signal['bias']}")
            
            if signal['bias'] == macro_trend:
                logger.info("🔥 ALINEACIÓN TOTAL CON 1H: Operación Válida.")
            else:
                logger.info("❌ FILTRADA por 1H: Operación Ignorada (Macro en contra).")
        else:
            logger.info("ℹ️ No se detectó señal en este momento (Filtros V9.2 Activos).")
            # Mostrar métricas actuales para depuración
            curr = df_1m.iloc[-1]
            adx = curr.get('adx', 0)
            vol = curr.get('volume', 0)
            vol_avg = df_1m['volume'].rolling(window=10).mean().iloc[-1]
            logger.info(f"Métricas actuales: ADX: {adx:.1f} (Min 20) | Vol: {vol/vol_avg:.1f}x (Min 1.5x)")

if __name__ == "__main__":
    asyncio.run(test_logic())
