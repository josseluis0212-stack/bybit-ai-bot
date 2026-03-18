import pandas as pd
import asyncio
import logging
import time
from api.bybit_client import bybit_client
from strategy.base_strategy import strategy

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(self):
        self.timeframe = "15" # 15 minutos por defecto para intradía
        self.limit = 250 # Necesitamos al menos 200 velas para la EMA 200
        self.semaphore = asyncio.Semaphore(25) # Escaneo paralelo de 25 monedas a la vez (asíncrono)
        
    async def get_klines_as_df(self, symbol):
        """
        Obtiene velas históricas de Bybit y las convierte a Pandas DataFrame.
        """
        try:
            # Usar el nuevo método asíncrono para no saturar el pool de conexiones
            response = await bybit_client.get_klines_async(
                symbol=symbol,
                interval=self.timeframe,
                limit=self.limit
            )
            
            if response and response.get("retCode") == 0:
                list_data = response["result"]["list"]
                if not list_data: return None
                
                df = pd.DataFrame(list_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df = df.iloc[::-1].reset_index(drop=True)
                return df
                
            return None
        except Exception as e:
            # logger.error(f"Error klines {symbol}: {e}") # Evitar spam en logs masivos
            return None

    async def analyze_symbol(self, item):
        """Tarea individual para cada símbolo"""
        symbol = item['symbol']
        async with self.semaphore:
            df = await self.get_klines_as_df(symbol)
            if df is not None and not df.empty:
                try:
                    signal_data = strategy.analyze(symbol, df)
                    if signal_data:
                        logger.info(f"🚨 SEÑAL ENCONTRADA: {signal_data['signal']} en {symbol}")
                        return signal_data
                except Exception as e:
                    logger.error(f"Error analizando {symbol}: {e}")
            return None

    async def scan_market(self):
        """
        Rastrea el 100% de los pares USDT de Bybit buscando señales.
        Sin límites de cantidad, ordenado por volumen.
        """
        logger.info("Iniciando escaneo GLOBAL del mercado (Todas las monedas)...")
        start_time = time.time()
        
        tickers = bybit_client.get_tickers()
        if not tickers:
            logger.error("No se pudieron cargar los tickers.")
            return []
            
        # Ordenar por volumen (turnover24h) descendente
        tickers = sorted(tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
        total_pairs = len(tickers)
        logger.info(f"Analizando {total_pairs} pares USDT en paralelo...")

        # Lanzar tareas paralelas
        tasks = [self.analyze_symbol(item) for item in tickers]
        results = await asyncio.gather(*tasks)
        
        # Filtrar resultados válidos (quitar Nones)
        valid_signals = [sig for sig in results if sig is not None]
        
        end_time = time.time()
        logger.info(f"Escaneo global completado en {end_time - start_time:.2f}s. Encontradas {len(valid_signals)} señales.")
        
        return valid_signals

market_scanner = MarketScanner()
