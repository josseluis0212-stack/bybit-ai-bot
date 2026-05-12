"""
LRMC PRO — Market Scanner
Escanea los pares BTC, ETH y top altcoins líquidos en M1
usando la estrategia Fibonacci Cycle (13/34/89).
"""
import asyncio
import logging
import pandas as pd
from api.bybit_client import bybit_client
from strategy.ema_strategy import ema_strategy

logger = logging.getLogger(__name__)

TIMEFRAME      = "1"    # M1 en Bybit (minutos)
CANDLES_NEEDED = 150    # Aumentado para satisfacer EMA 100 (mínimo 120 velas)
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
        """Descarga velas M5 y M1, aplica filtro de tendencia M5 y analiza con la estrategia."""
        try:
            # 1. Filtro de tendencia M5 (EMA 9 vs EMA 21)
            df_m5 = await asyncio.to_thread(self._get_klines, symbol, "5")
            if df_m5 is None or len(df_m5) < 30:
                return None
            
            ema_fast_m5 = df_m5['close'].ewm(span=13, adjust=False).mean().iloc[-1]
            ema_mid_m5 = df_m5['close'].ewm(span=34, adjust=False).mean().iloc[-1]
            trend_m5 = "BULLISH" if ema_fast_m5 > ema_mid_m5 else "BEARISH"

            # 2. Obtener y analizar velas M1
            df_m1 = await asyncio.to_thread(self._get_klines, symbol, "1")
            if df_m1 is None or len(df_m1) < CANDLES_NEEDED:
                return None
                
            signal = ema_strategy.analyze(df_m1, symbol)
            
            # 3. Filtrar señal M1 según tendencia M5
            if signal:
                if signal["signal"] == "LONG" and trend_m5 != "BULLISH":
                    logger.debug(f"[Scanner] {symbol} LONG rechazado por filtro M5 (Tendencia {trend_m5})")
                    return None
                if signal["signal"] == "SHORT" and trend_m5 != "BEARISH":
                    logger.debug(f"[Scanner] {symbol} SHORT rechazado por filtro M5 (Tendencia {trend_m5})")
                    return None
                
                logger.info(f"[Scanner] {symbol} {signal['signal']} validado por filtro de tendencia M5 ({trend_m5})")
                
            return signal
        except Exception as e:
            logger.debug(f"[Scanner] {symbol} error: {e}")
            return None

    def _get_klines(self, symbol: str, interval: str = TIMEFRAME) -> pd.DataFrame | None:
        """Obtiene velas de Bybit y retorna DataFrame OHLCV."""
        try:
            resp = bybit_client.get_klines(
                symbol=symbol,
                interval=interval,
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
