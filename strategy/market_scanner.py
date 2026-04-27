import pandas as pd
import asyncio
import logging
import time
from api.bybit_client import bybit_client
from strategy.base_strategy import strategy

logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(self):
        self.exec_tf = "1"  # 1 minuto para ejecución
        self.bias_tf = "15"  # 15 minutos para tendencia
        self.limit = 120

    async def get_klines(self, symbol, interval):
        try:
            response = await bybit_client.get_klines_async(
                symbol=symbol, interval=interval, limit=self.limit
            )
            if response and response.get("retCode") == 0:
                list_data = response["result"]["list"]
                if not list_data:
                    return None
                df = pd.DataFrame(
                    list_data,
                    columns=[
                        "timestamp",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "turnover",
                    ],
                )
                df = df.iloc[::-1].reset_index(drop=True)
                return df
            return None
        except Exception as e:
            return None

    async def analyze_symbol(self, item):
        symbol = item["symbol"]
        try:
            df_exec = await self.get_klines(symbol, self.exec_tf)
            if df_exec is None or len(df_exec) < 50:
                return None

            signal = strategy.analyze(symbol, df_exec)
            if signal:
                logger.info(
                    f"SEÑAL: {signal['signal']} {symbol} @ {signal['entry_price']:.6f}"
                )
                return signal
            return None
        except Exception as e:
            return None

    async def scan_market(self):
        logger.info("Escaneo GLOBAL iniciado...")
        start = time.time()

        tickers = bybit_client.get_tickers()
        if not tickers:
            return []

        tickers = [t for t in tickers if float(t.get("turnover24h", 0)) >= 30000000]
        tickers = sorted(
            tickers, key=lambda x: float(x.get("turnover24h", 0)), reverse=True
        )[:100]
        logger.info(f"Analizando {len(tickers)} pares...")

        semaphore = asyncio.Semaphore(20)

        async def bounded_analyze(item):
            async with semaphore:
                return await self.analyze_symbol(item)

        tasks = [bounded_analyze(item) for item in tickers]
        results = await asyncio.gather(*tasks)

        signals = [r for r in results if r is not None]

        elapsed = time.time() - start
        logger.info(f"Escaneo completado en {elapsed:.1f}s. Señales: {len(signals)}")

        return signals


market_scanner = MarketScanner()
