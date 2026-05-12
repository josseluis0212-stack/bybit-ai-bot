
import asyncio
import pandas as pd
from api.bybit_client import bybit_client
from strategy.ema_strategy import ema_strategy
from strategy.market_scanner import market_scanner
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Diagnostic")

async def diagnostic():
    logger.info("🕵️ Iniciando Diagnóstico de Señales EMA...")
    tickers = bybit_client.get_tickers()
    if not tickers:
        logger.error("No se pudieron obtener tickers")
        return

    sorted_tickers = sorted(tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
    symbols = [t['symbol'] for t in sorted_tickers[:20]] # Probamos solo el top 20 para rapidez

    for symbol in symbols:
        logger.info(f"Analizando {symbol}...")
        df_m1 = market_scanner._get_klines(symbol, "1")
        df_m5 = market_scanner._get_klines(symbol, "5")

        if df_m1 is None or len(df_m1) < 120:
            logger.warning(f"{symbol}: No hay suficientes velas M1")
            continue
        
        # 1. Verificar Indicadores EMA
        df_m1['ema_fast'] = df_m1['close'].ewm(span=9, adjust=False).mean()
        df_m1['ema_mid']  = df_m1['close'].ewm(span=21,  adjust=False).mean()
        df_m1['ema_slow'] = df_m1['close'].ewm(span=89, adjust=False).mean()
        curr = df_m1.iloc[-2]
        
        logger.info(f"   {symbol} M1: EMA9={curr['ema_fast']:.4f}, EMA21={curr['ema_mid']:.4f}, EMA89={curr['ema_slow']:.4f}")
        
        # 2. Verificar Alineación
        aligned_long = curr['ema_fast'] > curr['ema_mid'] > curr['ema_slow']
        aligned_short = curr['ema_fast'] < curr['ema_mid'] < curr['ema_slow']
        logger.info(f"   Alineación: {'LONG' if aligned_long else 'SHORT' if aligned_short else 'NINGUNA'}")

        # 3. Verificar Cruce (últimas 4 velas)
        cross_up = False
        for i in range(-5, -1):
            p = df_m1.iloc[i-1]; c = df_m1.iloc[i]
            if p['ema_fast'] <= p['ema_mid'] and c['ema_fast'] > c['ema_mid']: cross_up = True
        logger.info(f"   Cruce UP (últimas 4): {cross_up}")

        # 4. Filtro M5
        ema_fast_m5 = df_m5['close'].ewm(span=9, adjust=False).mean().iloc[-2]
        ema_mid_m5 = df_m5['close'].ewm(span=21, adjust=False).mean().iloc[-2]
        trend_m5 = "BULLISH" if ema_fast_m5 > ema_mid_m5 else "BEARISH"
        logger.info(f"   Filtro M5: {trend_m5}")

        # 5. ADX y Volumen
        from strategy.ema_strategy import ema_strategy
        df_m1['adx'] = ema_strategy._calc_adx(df_m1)
        df_m1['vol_avg'] = df_m1['volume'].rolling(25).mean()
        curr = df_m1.iloc[-2]
        logger.info(f"   ADX: {curr['adx']:.1f} (Min 20), Vol: {curr['volume']} (Avg {curr['vol_avg']:.1f})")

        sig = ema_strategy.analyze(df_m1, symbol)
        if sig:
            logger.info(f"🚀 SEÑAL ENCONTRADA EN ESTRATEGIA: {sig['signal']}")
        else:
            logger.info("❌ No hay señal EMA completa.")

if __name__ == "__main__":
    asyncio.run(diagnostic())
