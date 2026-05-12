"""
LRMC PRO — Market Scanner
Escanea los pares top altcoins líquidos en M1 y M5
usando EMA PRO (M1) y LRMC PRO (M5) de forma independiente.
"""
import asyncio
import logging
import pandas as pd
from api.bybit_client import bybit_client
from strategy.ema_strategy import ema_strategy
from strategy.lrmc_strategy import lrmc_strategy

logger = logging.getLogger(__name__)

TIMEFRAME      = "1"    # M1 en Bybit (minutos)
CANDLES_NEEDED = 150    # Aumentado para satisfacer EMA 100 (mínimo 120 velas)
TOP_COINS_LIMIT = 70    # Límite de monedas a escanear (Top por volumen)


class LRMCScanner:
    """
    Escanea todos los pares definidos en LRMC_SYMBOLS,
    obtiene velas M5 y aplica las estrategias EMA PRO y LRMC PRO.
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
                if isinstance(result, list):
                    signals.extend(result)
                else:
                    signals.append(result)
            elif sym == "BTCUSDT":
                logger.debug(f"[Scanner] BTC analizado sin señal")

        logger.info(f"[Scanner] Doble Scan (EMA/LRMC) completo — {len(signals)} señal(es) encontrada(s)")
        return signals

    async def _analyze_symbol(self, symbol: str) -> list[dict] | None:
        """Descarga velas y analiza con ambas estrategias."""
        found_signals = []
        try:
            # 1. Obtener Velas M1 y M5
            df_m1 = await asyncio.to_thread(self._get_klines, symbol, "1")
            df_m5 = await asyncio.to_thread(self._get_klines, symbol, "5")
            
            if df_m1 is None or len(df_m1) < CANDLES_NEEDED:
                logger.warning(f"[Scanner] {symbol} M1 insuficiente: {len(df_m1) if df_m1 is not None else 0}/{CANDLES_NEEDED}")
                return None
            if df_m5 is None or len(df_m5) < 30:
                logger.warning(f"[Scanner] {symbol} M5 insuficiente: {len(df_m5) if df_m5 is not None else 0}/30")
                return None

            # --- ESTRATEGIA 1: EMA PRO (M1 Scalping) ---
            ema_sig = ema_strategy.analyze(df_m1, symbol)
            if ema_sig:
                found_signals.append(ema_sig)

            # --- ESTRATEGIA 2: LRMC PRO (M5 Sweep) ---
            lrmc_sig = lrmc_strategy.analyze(df_m5, symbol)
            if lrmc_sig:
                found_signals.append(lrmc_sig)

            return found_signals if found_signals else None
            
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
