"""
LRMC PRO — Market Scanner
Escanea los pares BTC, ETH y top altcoins líquidos en M5
usando la estrategia LRMC (Liquidity Reversion + Momentum Continuation).
"""
import asyncio
import logging
import pandas as pd
from api.bybit_client import bybit_client
from strategy.lrmc_strategy import lrmc_strategy

logger = logging.getLogger(__name__)

# Pares fijos de alta liquidez para LRMC PRO
LRMC_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
    "LINKUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT",
    "ATOMUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT",  "SEIUSDT", "SUIUSDT", "TIAUSDT",
]

TIMEFRAME    = "5"    # M5 en Bybit (minutos)
CANDLES_NEEDED = 60   # Mínimo de velas para análisis confiable


class LRMCScanner:
    """
    Escanea todos los pares definidos en LRMC_SYMBOLS,
    obtiene velas M5 y aplica la estrategia LRMC PRO.
    """

    async def scan_market(self) -> list[dict]:
        """
        Retorna lista de señales válidas encontradas.
        Cada señal incluye symbol, signal, entry_price, sl, tp1, tp2, tp3.
        """
        signals = []
        tasks = [self._analyze_symbol(sym) for sym in LRMC_SYMBOLS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(LRMC_SYMBOLS, results):
            if isinstance(result, Exception):
                logger.debug(f"[Scanner] Error {sym}: {result}")
                continue
            if result is not None:
                signals.append(result)

        logger.info(f"[Scanner] LRMC scan completo — {len(signals)} señal(es) encontrada(s)")
        return signals

    async def _analyze_symbol(self, symbol: str) -> dict | None:
        """Descarga velas M5 y analiza con LRMC strategy."""
        try:
            df = await asyncio.to_thread(self._get_klines, symbol)
            if df is None or len(df) < CANDLES_NEEDED:
                return None
            return lrmc_strategy.analyze(df, symbol)
        except Exception as e:
            logger.debug(f"[Scanner] {symbol} error: {e}")
            return None

    def _get_klines(self, symbol: str) -> pd.DataFrame | None:
        """Obtiene velas M5 de Bybit y retorna DataFrame OHLCV."""
        try:
            resp = bybit_client.get_klines(
                symbol=symbol,
                interval=TIMEFRAME,
                limit=CANDLES_NEEDED + 10,
            )
            if not resp or resp.get("retCode") != 0:
                return None

            raw = resp["result"]["list"]
            if not raw:
                return None

            # Bybit retorna en orden descendente (más reciente primero)
            df = pd.DataFrame(raw, columns=[
                "timestamp", "open", "high", "low", "close", "volume", "turnover"
            ])
            df = df.iloc[::-1].reset_index(drop=True)  # Cronológico
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.dropna(inplace=True)
            return df

        except Exception as e:
            logger.debug(f"[Scanner] klines {symbol}: {e}")
            return None


# Instancia global
market_scanner = LRMCScanner()
