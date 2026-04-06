import pandas as pd
import asyncio
import logging
import time
from api.bybit_client import bybit_client
from strategy.base_strategy import strategy

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(self):
        self.timeframe = "1" # Scalping Ultra-rápido de 1 Minuto
        self.limit = 60 # Suficiente para Bollinger 20, MFI 14 y ATR 14.
        
    async def get_klines_as_df(self, symbol):
        """
        Obtiene velas históricas de Bybit y las convierte a Pandas DataFrame.
        """
        try:
            response = bybit_client.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=self.timeframe,
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
            logger.error(f"Error obteniendo klines para {symbol}: {e}")
            return None

    async def scan_market(self):
        """
        Rastrea el mercado USDT Perpetual con filtros avanzados de liquidez y tendencia.
        """
        logger.info("🌍 Iniciando ESCANEO PROFESIONAL Ultra-V5 (SMC/FVG)...")
        
        tickers = bybit_client.get_tickers()
        if not tickers:
            logger.error("No se pudieron cargar los tickers.")
            return []
            
        # 1. Filtro de Liquidez Profesional: Al menos $10,000,000 USD de volumen diario
        # Esto reduce drásticamente el slippage y las trampas de baja liquidez.
        MIN_TURNOVER = 10_000_000
        valid_tickers = [t for t in tickers if float(t.get('turnover24h', 0)) > MIN_TURNOVER]
        
        # 2. Ordenar por Volumen
        valid_tickers = sorted(valid_tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
        
        logger.info(f"Escaneando {len(valid_tickers)} monedas de alta liquidez (> $10M).")
        
        semaphore = asyncio.Semaphore(20) # Reducimos concurrencia para evitar Rate Limits de Bybit
        
        async def scan_symbol(item):
            async with semaphore:
                symbol = item['symbol']
                await asyncio.sleep(0.05)
                
                # Obtener Marco de 1m (Ejecución) y 15m (Tendencia/Bias)
                df_1m = await self.get_klines_as_df(symbol, interval="1")
                df_15m = await self.get_klines_as_df(symbol, interval="15")
                
                if df_1m is not None and not df_1m.empty and df_15m is not None:
                    return strategy.analyze(symbol, df_1m, df_15m)
                return None

        tasks = [scan_symbol(item) for item in valid_tickers]
        results = await asyncio.gather(*tasks)
        
        valid_signals = [res for res in results if res is not None]
        
        if valid_signals:
            logger.info(f"🎯 Escaneo completado. ¡{len(valid_signals)} señales institucionales detectadas!")
        else:
            logger.info("Escaneo completado. Sin señales SMC/FVG en este ciclo.")

        return valid_signals

    async def get_klines_as_df(self, symbol, interval="1"):
        try:
            response = bybit_client.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=str(interval),
                limit=60
            )
            
            if response.get("retCode") == 0:
                list_data = response["result"]["list"]
                df = pd.DataFrame(list_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df = df.iloc[::-1].reset_index(drop=True)
                return df
            return None
        except Exception as e:
            logger.error(f"Error en klines {interval}m para {symbol}: {e}")
            return None

market_scanner = MarketScanner()
