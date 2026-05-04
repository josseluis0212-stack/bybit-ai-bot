"""
LRMC PRO — Market Scanner
Escanea los pares BTC, ETH y top altcoins líquidos en M1
usando la estrategia EMA Crossover (9/21).
"""
import asyncio
import logging
import pandas as pd
from api.bybit_client import bybit_client
from strategy.ema_strategy import ema_strategy

logger = logging.getLogger(__name__)

TIMEFRAME      = "1"    # M1 en Bybit (minutos)
CANDLES_NEEDED = 100    # Triple EMA Pro requiere mínimo 80 velas
TOP_COINS_LIMIT = 70    # Límite de monedas a escanear (Top por volumen)


class LRMCScanner:
    """
    Escanea todos los pares definidos en LRMC_SYMBOLS,
    obtiene velas M5 y aplica la estrategia LRMC PRO.
    """

    async def scan_market(self) -> list[dict]:
        """
        Retorna lista de señales válidas encontradas.
        """
        # Obtener Top monedas dinámicamente
        tickers = bybit_client.get_tickers()
        if not tickers:
            logger.error("[Scanner] No se pudieron obtener tickers de Bybit")
            return []

        # Ordenar por volumen 24h descendente y tomar las top
        sorted_tickers = sorted(tickers, key=lambda x: float(x.get('turnover24h', 0)), reverse=True)
        symbols = [t['symbol'] for t in sorted_tickers[:TOP_COINS_LIMIT]]

        signals = []
        tasks = [self._analyze_symbol(sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"[Scanner] Error critico en {sym}: {result}")
                continue
            if result is not None:
                signals.append(result)
            elif sym == "BTCUSDT":
                logger.info(f"[Scanner] BTC analizado sin señal (OK)")

        logger.info(f"[Scanner] EMA scan completo — {len(signals)} señal(es) encontrada(s) en {len(symbols)} monedas")
        return signals

    async def _analyze_symbol(self, symbol: str) -> dict | None:
        """Descarga velas M5 y analiza con LRMC strategy."""
        try:
            df = await asyncio.to_thread(self._get_klines, symbol)
            if df is None or len(df) < CANDLES_NEEDED:
                return None
            return ema_strategy.analyze(df, symbol)
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
            # Forzar conversión y asegurar orden cronológico (Viejo -> Nuevo)
            df['timestamp'] = pd.to_numeric(df['timestamp'])
            df = df.sort_values('timestamp', ascending=True).reset_index(drop=True)
            
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df.dropna(inplace=True)
            return df

        except Exception as e:
            logger.warning(f"[Scanner] Error en klines de {symbol}: {e}")
            return None


# Instancia global
market_scanner = LRMCScanner()
