import pandas as pd
import asyncio
import logging
import time
from api.bybit_client import bybit_client
from strategy.base_strategy import strategy

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(self):
        self.timeframe_exec = "1"
        self.timeframe_bias = "5"
        self.limit = 150 # Necesario para EMA 100 + margen de cálculo
        
    async def get_klines_as_df(self, symbol, interval="1"):
        """
        Obtiene velas históricas de Bybit y las convierte a Pandas DataFrame.
        """
        try:
            response = bybit_client.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=str(interval),
                limit=self.limit
            )
            
            if response.get("retCode") == 0:
                list_data = response["result"]["list"]
                
                # Bybit retorna [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                # En orden descendente (el más reciente es el index 0)
                df = pd.DataFrame(list_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                
                # Invertir el DataFrame para que la vela más antigua sea la primera
                df = df.iloc[::-1].reset_index(drop=True)
                return df
                
            return None
        except Exception as e:
            logger.error(f"Error obteniendo klines {interval}m para {symbol}: {e}")
            return None

    async def scan_market(self):
        """
        Rastrea el mercado USDT Perpetual con filtros avanzados de liquidez y tendencia (V6).
        """
        logger.info("🌍 Iniciando ESCANEO PROFESIONAL Ultra-V6 (Balanced SMC)...")
        
        tickers = bybit_client.get_tickers()
        if not tickers:
            logger.error("No se pudieron cargar los tickers.")
            return []
            
        # Filtro de Liquidez Profesional: Al menos $10,000,000 USD de volumen diario
        MIN_TURNOVER = 10_000_000
        valid_tickers = [t for t in tickers if float(t.get('turnover24h', 0)) > MIN_TURNOVER]
        
        # Ordenar por Volumen y tomar las top 70
        valid_tickers = sorted(valid_tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)[:70]
        
        logger.info(f"Escaneando {len(valid_tickers)} monedas de alta liquidez (> $10M).")
        
        semaphore = asyncio.Semaphore(20) # Concurrencia controlada
        
        async def scan_symbol(item):
            async with semaphore:
                symbol = item['symbol']
                await asyncio.sleep(0.02) # Pequeño delay adicional para rate limit
                
                # Obtener Marco de 1m (Ejecución) y 15m (Tendencia/Bias)
                df_1m = await self.get_klines_as_df(symbol, interval=self.timeframe_exec)
                df_15m = await self.get_klines_as_df(symbol, interval=self.timeframe_bias)
                
                if df_1m is not None and not df_1m.empty and df_15m is not None:
                    return strategy.analyze(symbol, df_1m, df_15m)
                return None

        tasks = [scan_symbol(item) for item in valid_tickers]
        results = await asyncio.gather(*tasks)
        
        valid_signals = [res for res in results if res is not None]
        
        if valid_signals:
            logger.info(f"🎯 Escaneo completado. ¡{len(valid_signals)} señales detectadas!")
        else:
            logger.info("Escaneo completado. Sin señales SMC/Pullback en este ciclo.")

        return valid_signals

market_scanner = MarketScanner()
