"""
LRMC PRO — Liquidity Reversion + Momentum Continuation
Estrategia basada en estructura de precio puro (sin indicadores clásicos).
Detecta barridas de liquidez y entra en reversión con gestión dinámica.
"""
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ─── PARÁMETROS CONFIGURABLES ─────────────────────────────────────────────────
SWEEP_LOOKBACK       = 15    # Velas para detectar el extremo barrido
WICK_RATIO_MIN       = 0.50  # Mecha mínima 50% del rango total
ACTIVE_RANGE_WINDOW  = 10    # Velas para filtro de mercado activo
PASSIVE_RANGE_WINDOW = 30    # Ventana larga para comparar actividad
MIN_MOVE_PCT         = 0.008 # Movimiento previo mínimo 0.8%
MAX_CONSEC_LOSSES    = 3     # Bloqueo tras N pérdidas seguidas
TP1_R                = 1.5
TP2_R                = 2.5
TP3_R                = 4.0
TP1_PCT              = 0.50  # Cerrar 50% en TP1
TP2_PCT              = 0.30  # Cerrar 30% en TP2
TP3_PCT              = 0.20  # Dejar correr 20% hasta TP3
BREAKEVEN_AT_R       = 1.0   # Mover SL a BE cuando llega a 1R
STAGNATION_CANDLES   = 10    # Candles sin movimiento → cerrar


class LRMCStrategy:
    """
    Liquidity Reversion + Momentum Continuation (LRMC PRO)
    
    Lógica:
    1. Detecta barrida de liquidez (sweep) en últimas SWEEP_LOOKBACK velas
    2. Verifica que la vela de rechazo tenga mecha válida (≥50% rango)
    3. Confirma que la siguiente vela cierre en dirección de reversión
    4. Aplica filtros de calidad (rango activo, movimiento previo)
    5. Gestión dinámica: BE en 1R, cierres parciales en TP1/TP2/TP3
    """

    def __init__(self):
        self.consecutive_losses = 0
        self.blocked = False

    # ─── API PÚBLICA ──────────────────────────────────────────────────────────

    def analyze(self, df: pd.DataFrame, symbol: str) -> dict | None:
        """
        Analiza un DataFrame OHLCV (M5) y retorna señal o None.
        
        Returns:
            dict con keys: signal, entry_price, sl, tp1, tp2, tp3,
                           sl_distance_pct, strategy, symbol
            None si no hay señal válida.
        """
        if self.blocked:
            logger.debug(f"[LRMC] {symbol} bloqueado por {MAX_CONSEC_LOSSES} pérdidas consecutivas")
            return None

        if len(df) < PASSIVE_RANGE_WINDOW + 5:
            return None

        df = df.copy().reset_index(drop=True)
        self._add_columns(df)

        # Filtros de calidad (DESACTIVADOS PARA PRUEBA)
        # if not self._filter_quality(df):
        #     return None

        # Detectar setup
        signal = self._detect_sweep_and_entry(df)
        if signal is None:
            return None

        direction, sl_price, entry_price = signal
        risk = abs(entry_price - sl_price)

        if risk <= 0:
            return None

        if direction == "LONG":
            tp1 = entry_price + risk * TP1_R
            tp2 = entry_price + risk * TP2_R
            tp3 = entry_price + risk * TP3_R
        else:
            tp1 = entry_price - risk * TP1_R
            tp2 = entry_price - risk * TP2_R
            tp3 = entry_price - risk * TP3_R

        sl_pct = risk / entry_price

        logger.info(
            f"[LRMC] ✅ SEÑAL {direction} {symbol} | Entry={entry_price:.4f} "
            f"SL={sl_price:.4f} TP1={tp1:.4f} TP2={tp2:.4f} TP3={tp3:.4f} | "
            f"SL%={sl_pct*100:.2f}%"
        )

        return {
            "symbol":        symbol,
            "signal":        direction,
            "entry_price":   entry_price,
            "sl":            sl_price,
            "tp1":           tp1,
            "tp2":           tp2,
            "tp3":           tp3,
            "tp1_pct":       TP1_PCT,
            "tp2_pct":       TP2_PCT,
            "tp3_pct":       TP3_PCT,
            "breakeven_r":   BREAKEVEN_AT_R,
            "sl_distance":   sl_pct,
            "strategy":      "LRMC_PRO_v1",
        }

    def register_loss(self):
        """Llamar cuando se cierra un trade con pérdida."""
        self.consecutive_losses += 1
        if self.consecutive_losses >= MAX_CONSEC_LOSSES:
            self.blocked = True
            logger.warning(f"[LRMC] ⛔ Bloqueado por {MAX_CONSEC_LOSSES} pérdidas consecutivas.")

    def register_win(self):
        """Llamar cuando se cierra un trade con ganancia."""
        self.consecutive_losses = 0
        self.blocked = False

    def unblock(self):
        """Reset manual del bloqueo."""
        self.consecutive_losses = 0
        self.blocked = False
        logger.info("[LRMC] 🔓 Bloqueo liberado manualmente.")

    # ─── DETECCIÓN DE BARRIDA ─────────────────────────────────────────────────

    def _detect_sweep_and_entry(self, df: pd.DataFrame):
        """
        Analiza las últimas velas buscando barrida + confirmación.
        Retorna (direction, sl_price, entry_price) o None.
        """
        n = len(df)
        # La señal requiere al menos 3 velas: barrida, rechazo, confirmación
        # Evaluamos si la antepenúltima + penúltima forman el setup
        # y la última es la confirmación

        # Índices: -3 = zona previa, -2 = vela de barrida/rechazo, -1 = confirmación
        if n < SWEEP_LOOKBACK + 3:
            return None

        # ── SETUP LONG (barrida bajista) ─────────────────────────────────────
        long_result = self._check_bullish_reversal(df)
        if long_result:
            return long_result

        # ── SETUP SHORT (barrida alcista) ─────────────────────────────────────
        short_result = self._check_bearish_reversal(df)
        if short_result:
            return short_result

        return None

    def _check_bullish_reversal(self, df: pd.DataFrame):
        """
        Barrida bajista → reversión alcista.
        Condiciones:
        1. Vela de barrida rompe el mínimo de las últimas SWEEP_LOOKBACK velas
        2. La misma vela CIERRA dentro del rango previo
        3. Mecha inferior ≥ 50% del rango de la vela
        4. Siguiente vela (confirmación) cierra alcista
        """
        sweep_candle = df.iloc[-2]   # vela de barrida
        confirm_candle = df.iloc[-1] # vela de confirmación
        lookback = df.iloc[-(SWEEP_LOOKBACK + 2):-2]

        prev_low = lookback["low"].min()
        prev_high = lookback["high"].max()
        prev_range_open = lookback.iloc[-1]["close"]  # último cierre antes de barrida

        # 1. Barrida: mínimo rompe el piso de las últimas N velas
        if sweep_candle["low"] >= prev_low:
            return None

        # --- FILTROS RELAJADOS PARA PRUEBA ---
        sl_price = sweep_candle["low"] * 0.9995
        entry_price = confirm_candle["close"]
        return ("LONG", sl_price, entry_price)

    def _check_bearish_reversal(self, df: pd.DataFrame):
        """
        Barrida alcista → reversión bajista.
        Condiciones inversas al bullish reversal.
        """
        sweep_candle = df.iloc[-2]
        confirm_candle = df.iloc[-1]
        lookback = df.iloc[-(SWEEP_LOOKBACK + 2):-2]

        prev_high = lookback["high"].max()

        # 1. Barrida: máximo rompe el techo
        if sweep_candle["high"] <= prev_high:
            return None

        # --- FILTROS RELAJADOS PARA PRUEBA ---
        sl_price = sweep_candle["high"] * 1.0005
        entry_price = confirm_candle["close"]
        return ("SHORT", sl_price, entry_price)

    # ─── FILTROS DE CALIDAD ───────────────────────────────────────────────────

    def _filter_quality(self, df: pd.DataFrame) -> bool:
        """
        Filtros PRO:
        1. Rango activo: avg_range(10) > avg_range(30)  → mercado con momentum
        2. Sin consolidación extrema (no velas todas pequeñas)
        3. Movimiento previo ≥ 0.8%
        """
        # Filtro 1: mercado activo
        short_avg = df["range"].iloc[-ACTIVE_RANGE_WINDOW:].mean()
        long_avg  = df["range"].iloc[-PASSIVE_RANGE_WINDOW:].mean()
        if short_avg <= long_avg:
            return False

        # Filtro 2: sin consolidación extrema
        # (si las últimas 5 velas tienen rango menor al 30% del promedio largo → skip)
        micro_avg = df["range"].iloc[-5:].mean()
        if micro_avg < long_avg * 0.3:
            return False

        # Filtro 3: movimiento previo ≥ 0.8%
        prev_move = df["prev_move_pct"].iloc[-1]
        if prev_move < MIN_MOVE_PCT:
            return False

        return True

    # ─── COLUMNAS AUXILIARES ──────────────────────────────────────────────────

    def _add_columns(self, df: pd.DataFrame):
        """Agrega columnas calculadas al DataFrame."""
        df["range"] = df["high"] - df["low"]
        # Movimiento previo: cambio % del cuerpo de las últimas 5 velas
        df["prev_move_pct"] = (
            (df["close"] - df["close"].shift(5)).abs() / df["close"].shift(5)
        ).fillna(0)


# Instancia global del estratega
lrmc_strategy = LRMCStrategy()
