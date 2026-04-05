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
        self.limit = 400 # Suficiente para VWAP y Bollinger 200 si se requiere
        
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
        Rastrea TODO el mercado USDT Perpetual procesando monedas en paralelo.
        """
        logger.info("🌍 Iniciando ESCANEO GLOBAL Hyper-Quant (Todas las monedas)...")
        
        tickers = bybit_client.get_tickers()
        if not tickers:
            logger.error("No se pudieron cargar los tickers. Reintentando...")
            return []
            
        # 1. Filtro de Seguridad: Al menos $50,000 USD de volumen (turnover24h)
        # Esto evita "slippage" destructivo en monedas muertas.
        valid_tickers = [t for t in tickers if float(t.get('turnover24h', 0)) > 50000]
        
        # 2. Ordenar por Volumen de mayor a menor
        valid_tickers = sorted(valid_tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
        
        logger.info(f"Escaneando {len(valid_tickers)} monedas líquidas de {len(tickers)} totales.")
        
        # 3. Procesamiento en Paralelo con Semáforo (30 trabajadores concurrentes)
        # Esto previene bloqueos de IP por Bybit mientras acelera el escaneo 10x.
        semaphore = asyncio.Semaphore(30)
        
        async def scan_symbol(item):
            async with semaphore:
                symbol = item['symbol']
                # Pequeña pausa para no saturar CPU local
                await asyncio.sleep(0.01)
                
                df = await self.get_klines_as_df(symbol)
                if df is not None and not df.empty:
                    return strategy.analyze(symbol, df)
                return None

        # Lanzar todas las tareas concurrentemente
        tasks = [scan_symbol(item) for item in valid_tickers]
        results = await asyncio.gather(*tasks)
        
        # Filtrar resultados que no sean None (señales reales)
        valid_signals = [res for res in results if res is not None]
        
        if valid_signals:
            logger.info(f"🎯 Escaneo Global completado. ¡{len(valid_signals)} señales detectadas!")
        else:
            logger.info("Escaneo Global completado. Sin señales en este ciclo.")

        return valid_signals

market_scanner = MarketScanner()
