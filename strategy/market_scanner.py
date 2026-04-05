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
        Rastrea todos los pares buscando las mejores señales de reversión.
        """
        logger.info("Iniciando escaneo de alta frecuencia Hyper-Quant...")
        
        tickers = bybit_client.get_tickers()
        if not tickers:
            logger.error("No se pudieron cargar los tickers. Reintentando luego...")
            return []
            
        # Filtrar por volumen para asegurar liquidez (mínimo 1M turnover si hay muchos)
        # Pero escaneamos por prioridad de volumen primero
        tickers = sorted(tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
        
        valid_signals = []
        # Para evitar excesivo lag, escaneamos los Top 100 por volumen. 
        # Bybit suele tener 200+, pero los últimos 100 suelen tener poco volumen para scalping a 1m.
        for item in tickers[:80]: # Reducimos ligeramente para ser mas veloces en el loop de 60s
            symbol = item['symbol']
            
            # API Rate Limit mitigation
            await asyncio.sleep(0.05) # Reducido a 0.05 para acelerar el escaneo total (~4-5s total)
            
            df = await self.get_klines_as_df(symbol)
            if df is not None and not df.empty:
                signal_data = strategy.analyze(symbol, df)
                if signal_data:
                    logger.info(f"🚨 SEÑAL HYPER: {signal_data['signal']} en {symbol} | Precio: {signal_data['entry_price']}")
                    valid_signals.append(signal_data)
                    
        return valid_signals

market_scanner = MarketScanner()
