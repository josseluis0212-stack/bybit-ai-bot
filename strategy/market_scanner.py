import pandas as pd
import asyncio
import logging
import time
from api.bybit_client import bybit_client
from strategy.base_strategy import strategy
from risk_management.risk_manager import risk_manager

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(self):
        self.timeframe = "15" # 15 minutos por defecto para intradía
        self.limit = 250 # Necesitamos al menos 200 velas para la EMA 200
        
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
        Rastrea todos los pares buscando señales.
        """
        logger.info("Iniciando escaneo completo del mercado...")
        valid_signals = []
        
        tickers = bybit_client.get_tickers()
        if not tickers:
            logger.error("No se pudieron cargar los tickers. Reintentando luego...")
            return []
            
        # Ordenar por volumen (turnover24h) descendente para escanear los más relevantes primero
        tickers = sorted(tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
        
        # Analizar todos en lugar de limitar a 50
        valid_signals = []
        for item in tickers:
            symbol = item['symbol']
            
            # API Rate Limit mitigation (pequeña pausa)
            await asyncio.sleep(0.1)
            
            df = await self.get_klines_as_df(symbol)
            if df is not None and not df.empty:
                signal_data = strategy.analyze(symbol, df)
                if signal_data:
                    logger.info(f"🚨 SEÑAL ENCONTRADA: {signal_data['signal']} en {symbol} a {signal_data['entry_price']}")
                    valid_signals.append(signal_data)
                    
        return valid_signals

market_scanner = MarketScanner()
