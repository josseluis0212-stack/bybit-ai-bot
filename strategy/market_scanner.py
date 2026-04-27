import pandas as pd
import asyncio
import logging
import time
from api.bybit_client import bybit_client
from strategy.base_strategy import strategy
from config.settings import settings

logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(self):
        self.tf_ltf = "1"
        self.tf_htf = "15"
        self.limit_ltf = 150
        self.limit_htf = 150

    async def get_klines(self, symbol, interval, limit):
        try:
            resp = bybit_client.session.get_kline(
                category="linear", symbol=symbol, interval=interval, limit=limit
            )
            if resp and resp.get("retCode") == 0:
                data = resp["result"]["list"]
                df = pd.DataFrame(
                    data,
                    columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
                )
                df = df.iloc[::-1].reset_index(drop=True)
                numeric_cols = ['open', 'high', 'low', 'close', 'volume']
                for col in numeric_cols:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                return df.dropna(subset=numeric_cols)
            return None
        except Exception as e:
            logger.error(f"Error klines {symbol}: {e}")
            return None

    async def analyze_symbol(self, item):
        symbol = item["symbol"]
        try:
            # Filtro de volumen 24h USD
            turnover_24h = float(item.get("turnover24h", 0))
            if turnover_24h < settings.MIN_VOL_24H_USD:
                return None

            # Filtro de Spread
            bid = float(item.get("bid1Price", 0))
            ask = float(item.get("ask1Price", 0))
            if bid > 0:
                spread_pct = (ask - bid) / bid
                if spread_pct > 0.0015: 
                    return None

            # Obtener data LTF y HTF concurrente
            df_ltf, df_htf = await asyncio.gather(
                self.get_klines(symbol, self.tf_ltf, self.limit_ltf),
                self.get_klines(symbol, self.tf_htf, self.limit_htf)
            )

            if df_ltf is None or df_htf is None: return None
            if len(df_ltf) < 50 or len(df_htf) < 100: return None

            signal = strategy.analyze_symbol(symbol, df_ltf, df_htf)
            if signal:
                logger.info(f"[{symbol}] SEÑAL HYPER SCALPER V1 ENCONTRADA: {signal}")
                return signal

            return None
        except Exception as e:
            return None

    async def scan_market(self):
        try:
            tickers = bybit_client.get_tickers()
            if not tickers:
                return []

            valid_tickers = []
            for t in tickers:
                if t["symbol"].endswith("USDT") and float(t.get("turnover24h", 0)) >= settings.MIN_VOL_24H_USD:
                    valid_tickers.append(t)

            valid_tickers.sort(key=lambda x: float(x.get("turnover24h", 0)), reverse=True)
            top_tickers = valid_tickers[:settings.TOP_COINS_LIMIT]

            tasks = [self.analyze_symbol(t) for t in top_tickers]
            results = await asyncio.gather(*tasks)

            signals = [r for r in results if r is not None]
            return signals

        except Exception as e:
            logger.error(f"Scanner error: {e}")
            return []

market_scanner = MarketScanner()
