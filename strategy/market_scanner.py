import pandas as pd
import asyncio
import logging
import time
from api.bybit_client import bybit_client
from strategy.base_strategy import strategy
from ta.trend import EMAIndicator

logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(self):
        self.exec_tf = "5"  # 5 minutos para ejecución
        self.bias_tf = "15" # 15 minutos para Filtro HTF (EMA 100)
        self.limit = 150    # Aumentado para asegurar datos para EMA 100

    async def get_klines(self, symbol, interval):
        try:
            resp = bybit_client.session.get_kline(
                category="linear", symbol=symbol, interval=interval, limit=self.limit
            )
            if resp and resp.get("retCode") == 0:
                data = resp["result"]["list"]
                df = pd.DataFrame(
                    data,
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
            # Filtro de Spread Profesional (< 0.1%)
            bid = float(item.get("bid1Price", 0))
            ask = float(item.get("ask1Price", 0))
            if bid > 0:
                spread_pct = (ask - bid) / bid
                if spread_pct > 0.001: 
                    return None

            # 1. Obtener datos de 15m para Bias (HTF)
            df_bias = await self.get_klines(symbol, self.bias_tf)
            if df_bias is None or len(df_bias) < 101: return None
            
            # Calcular EMA 100 en 15m
            ema_series = EMAIndicator(close=df_bias["close"], window=100).ema_indicator()
            if ema_series.empty or pd.isna(ema_series.iloc[-1]):
                return None
                
            ema_100_15m = float(ema_series.iloc[-1])
            price_now = float(df_bias["close"].iloc[-1])
            htf_bias = "LONG" if price_now > ema_100_15m else "SHORT"

            # 2. Obtener datos de 5m para Ejecución
            df_exec = await self.get_klines(symbol, self.exec_tf)
            if df_exec is None or len(df_exec) < 50: return None

            # Pasar el bias HTF a la estrategia
            signal = strategy.analyze_symbol(symbol, df_exec, htf_bias=htf_bias)
            if signal:
                return signal
            return None
        except Exception:
            return None

    async def scan_market(self):
        try:
            tickers = bybit_client.get_tickers()
            if not tickers: return []
            
            # Filtro de volumen institucional ($30M+)
            active_symbols = [
                t for t in tickers 
                if float(t.get("turnover24h", 0)) > 30000000 
                and t["symbol"].endswith("USDT")
            ]
            
            logger.info(f"🔍 Escaneando {len(active_symbols)} pares (Bias HTF 15m + Exec 5m)...")
            
            tasks = [self.analyze_symbol(item) for item in active_symbols]
            results = await asyncio.gather(*tasks)
            
            signals = [r for r in results if r is not None]
            logger.info(f"✅ Escaneo completado. Señales detectadas: {len(signals)}")
            return signals
        except Exception as e:
            logger.error(f"Error en scan: {e}")
            return []

market_scanner = MarketScanner()
