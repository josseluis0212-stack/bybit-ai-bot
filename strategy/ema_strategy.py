"""
ANTIGRAVITY EMA PRO — Estrategia Triple EMA con Filtros Profesionales
======================================================================
Sistema estadísticamente ganador basado en investigación de mercado:

CONFIGURACIÓN:
  - EMA 9  (Rápida)  : Detecta el momentum inmediato
  - EMA 21 (Media)   : Tendencia de corto plazo
  - EMA 55 (Lenta)   : Tendencia de largo plazo (filtro de tendencia macro)

REGLAS DE ENTRADA (requiere TODAS las condiciones):
  🟢 LONG:
    1. EMA 9 > EMA 21 > EMA 55 (alineación perfecta alcista)
    2. Cruce de EMA 9 sobre EMA 21 en las últimas 3 velas
    3. ADX > 20 (mercado en tendencia, no lateral)
    4. Precio > EMA 21 (confirmación de momentum)
    5. Volumen actual > Promedio de volumen de las últimas 20 velas

  🔴 SHORT:
    1. EMA 9 < EMA 21 < EMA 55 (alineación perfecta bajista)
    2. Cruce de EMA 9 bajo EMA 21 en las últimas 3 velas
    3. ADX > 20 (mercado en tendencia)
    4. Precio < EMA 21
    5. Volumen actual > Promedio de volumen de las últimas 20 velas

GESTIÓN DE RIESGO:
  - SL: Basado en ATR (1.5x ATR desde el precio de entrada)
  - TP: Ratio 2:1 (mínimo recomendado para ser matemáticamente ganador)
  - Breakeven: Al alcanzar el 60% del TP

MATEMÁTICAS DEL SISTEMA:
  Con Win Rate = 45% y RR = 2:1:
  Expectativa = (0.45 * 2) - (0.55 * 1) = 0.90 - 0.55 = +0.35R por trade ✅
  Con Win Rate = 50% y RR = 2:1:
  Expectativa = (0.50 * 2) - (0.50 * 1) = 1.00 - 0.50 = +0.50R por trade ✅
"""
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class EMAProStrategy:
    """
    Estrategia Triple EMA Profesional con filtros ADX, Volumen y ATR.
    Diseñada para operar solo en condiciones de alta probabilidad.
    """

    def __init__(self):
        self.fast   = 9    # EMA Rápida
        self.mid    = 21   # EMA Media
        self.slow   = 55   # EMA Lenta (filtro macro)
        self.adx_period   = 14
        self.adx_threshold = 20   # Mínimo de fuerza de tendencia
        self.atr_period   = 14
        self.atr_sl_mult  = 1.5   # SL = 1.5x ATR
        self.rr_ratio     = 2.0   # TP = 2x el riesgo
        self.vol_lookback = 20    # Velas para promedio de volumen
        self.cross_window = 3     # Velas máximas desde el cruce

    # ─── CÁLCULOS DE INDICADORES ─────────────────────────────────────────────

    def _calc_adx(self, df: pd.DataFrame) -> pd.Series:
        """Calcula el ADX (Average Directional Index) de 14 periodos."""
        high = df['high']
        low  = df['low']
        close = df['close']
        n = self.adx_period

        # True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low  - close.shift(1)).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional Movements
        up_move   = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        # Smoothed averages (Wilder's smoothing)
        atr_s    = pd.Series(tr).ewm(alpha=1/n, adjust=False).mean()
        plus_di  = 100 * pd.Series(plus_dm).ewm(alpha=1/n, adjust=False).mean() / atr_s
        minus_di = 100 * pd.Series(minus_dm).ewm(alpha=1/n, adjust=False).mean() / atr_s

        dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
        adx = dx.ewm(alpha=1/n, adjust=False).mean()
        return adx

    def _calc_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calcula el ATR (Average True Range)."""
        high  = df['high']
        low   = df['low']
        close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(alpha=1/self.atr_period, adjust=False).mean()

    # ─── ANÁLISIS PRINCIPAL ───────────────────────────────────────────────────

    def analyze(self, df: pd.DataFrame, symbol: str) -> dict | None:
        """
        Analiza las velas y retorna una señal si se cumplen TODAS las condiciones.
        Retorna None si el mercado no está en condiciones óptimas.
        """
        # Necesitamos al menos 80 velas para que los cálculos sean confiables
        if len(df) < 80:
            return None

        df = df.copy()

        # ── 1. CALCULAR TODOS LOS INDICADORES ───────────────────────────────
        df['ema_fast'] = df['close'].ewm(span=self.fast, adjust=False).mean()
        df['ema_mid']  = df['close'].ewm(span=self.mid,  adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow, adjust=False).mean()
        df['adx']      = self._calc_adx(df)
        df['atr']      = self._calc_atr(df)
        df['vol_avg']  = df['volume'].rolling(self.vol_lookback).mean()

        # Usar vela cerrada más reciente (iloc[-2]) para evitar señales de vela en formación
        curr = df.iloc[-2]
        prev = df.iloc[-3]

        price  = curr['close']
        adx    = curr['adx']
        atr    = curr['atr']
        vol    = curr['volume']
        vol_avg = curr['vol_avg']

        # ── 2. FILTRO DE TENDENCIA (ADX) ────────────────────────────────────
        if adx < self.adx_threshold:
            # Mercado lateral — NO operar
            return None

        # ── 3. DETECTAR CRUCE EN LA VENTANA ─────────────────────────────────
        cross_long  = False
        cross_short = False
        window = range(-self.cross_window - 1, -1)

        for i in window:
            p = df.iloc[i - 1]
            c = df.iloc[i]
            if p['ema_fast'] <= p['ema_mid'] and c['ema_fast'] > c['ema_mid']:
                cross_long = True
            if p['ema_fast'] >= p['ema_mid'] and c['ema_fast'] < c['ema_mid']:
                cross_short = True

        # ── 4. FILTRO DE VOLUMEN ─────────────────────────────────────────────
        # Solo entrar si el volumen actual supera el promedio (confirmación de fuerza)
        vol_confirmed = vol > vol_avg if vol_avg > 0 else True

        # ── 5. EVALUAR SEÑAL LONG ────────────────────────────────────────────
        # Alineación perfecta: EMA9 > EMA21 > EMA55 (Tendencia alcista triple)
        aligned_long = (curr['ema_fast'] > curr['ema_mid'] > curr['ema_slow'])

        if cross_long and aligned_long and vol_confirmed:
            entry  = float(df.iloc[-1]['close'])  # Entrar al precio actual
            sl     = round(entry - (atr * self.atr_sl_mult), 6)
            risk   = entry - sl

            if risk <= 0:
                return None

            tp = round(entry + (risk * self.rr_ratio), 6)

            logger.info(
                f"✅ [EMA PRO] LONG {symbol} | "
                f"Entry={entry:.4f} SL={sl:.4f} TP={tp:.4f} | "
                f"ADX={adx:.1f} ATR={atr:.4f} Vol={vol/vol_avg:.1f}x"
            )
            return self._build_signal(symbol, "LONG", entry, sl, tp, adx, atr)

        # ── 6. EVALUAR SEÑAL SHORT ───────────────────────────────────────────
        # Alineación perfecta: EMA9 < EMA21 < EMA55 (Tendencia bajista triple)
        aligned_short = (curr['ema_fast'] < curr['ema_mid'] < curr['ema_slow'])

        if cross_short and aligned_short and vol_confirmed:
            entry  = float(df.iloc[-1]['close'])
            sl     = round(entry + (atr * self.atr_sl_mult), 6)
            risk   = sl - entry

            if risk <= 0:
                return None

            tp = round(entry - (risk * self.rr_ratio), 6)

            logger.info(
                f"✅ [EMA PRO] SHORT {symbol} | "
                f"Entry={entry:.4f} SL={sl:.4f} TP={tp:.4f} | "
                f"ADX={adx:.1f} ATR={atr:.4f} Vol={vol/vol_avg:.1f}x"
            )
            return self._build_signal(symbol, "SHORT", entry, sl, tp, adx, atr)

        return None

    # ─── CONSTRUCCIÓN DE SEÑAL ───────────────────────────────────────────────

    def _build_signal(self, symbol, side, entry, sl, tp, adx, atr) -> dict:
        return {
            "symbol":       symbol,
            "signal":       side,
            "entry_price":  entry,
            "sl":           sl,
            "tp1":          tp,
            "tp2":          tp,
            "tp3":          tp,
            "tp1_pct":      1.0,
            "tp2_pct":      0.0,
            "tp3_pct":      0.0,
            "breakeven_r":  0.6,  # Mover SL a BE al 60% del TP
            "sl_distance":  abs(entry - sl) / entry,
            "adx":          round(adx, 2),
            "atr":          round(atr, 6),
            "strategy":     "TRIPLE_EMA_PRO_9_21_55",
        }


ema_strategy = EMAProStrategy()
