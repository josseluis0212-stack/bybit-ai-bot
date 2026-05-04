"""
ANTIGRAVITY EMA PRO v2 — Estrategia Triple EMA Profesional
=============================================================
EMA 9 / 21 / 100 con filtros ADX, RSI y ATR profundo.

MATEMÁTICAS GANADORAS:
  - SL: 3x ATR  → lejos del ruido
  - TP: 6x ATR  → ratio 2:1 real
  - Trailing Stop: cierra cuando EMA9 cruza de vuelta EMA21
  - Breakeven: entrada + comisión cuando se alcanza 40% del TP
  - RSI: no entra si RSI > 65 (long) o RSI < 35 (short)
"""
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class EMAProStrategy:

    def __init__(self):
        self.fast        = 9    # EMA Rápida
        self.mid         = 21   # EMA Media
        self.slow        = 100  # EMA Lenta — filtro macro
        self.adx_period  = 14
        self.adx_min     = 20   # Fuerza de tendencia mínima
        self.atr_period  = 14
        self.atr_sl_mult = 3.0  # SL = 3x ATR (lejos del ruido)
        self.rr_ratio    = 2.0  # TP = 2x el riesgo → 6x ATR
        self.rsi_period  = 14
        self.rsi_ob      = 65   # RSI overbought (no comprar arriba de esto)
        self.rsi_os      = 35   # RSI oversold   (no vender abajo de esto)
        self.vol_window  = 20
        self.cross_window = 4   # Velas máximas desde el cruce

    # ─── INDICADORES ─────────────────────────────────────────────────────────

    def _calc_atr(self, df):
        high = df['high']; low = df['low']; close = df['close']
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(alpha=1/self.atr_period, adjust=False).mean()

    def _calc_adx(self, df):
        high = df['high']; low = df['low']; close = df['close']
        n = self.adx_period
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        up   = high - high.shift(1)
        dn   = low.shift(1) - low
        pdm  = np.where((up > dn) & (up > 0), up, 0.0)
        ndm  = np.where((dn > up) & (dn > 0), dn, 0.0)
        atr_s  = pd.Series(tr).ewm(alpha=1/n, adjust=False).mean()
        pdi    = 100 * pd.Series(pdm).ewm(alpha=1/n, adjust=False).mean() / (atr_s + 1e-10)
        ndi    = 100 * pd.Series(ndm).ewm(alpha=1/n, adjust=False).mean() / (atr_s + 1e-10)
        dx     = 100 * (pdi - ndi).abs() / (pdi + ndi + 1e-10)
        return dx.ewm(alpha=1/n, adjust=False).mean()

    def _calc_rsi(self, df):
        delta = df['close'].diff()
        gain  = delta.clip(lower=0).ewm(alpha=1/self.rsi_period, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(alpha=1/self.rsi_period, adjust=False).mean()
        rs    = gain / (loss + 1e-10)
        return 100 - (100 / (1 + rs))

    # ─── ANÁLISIS PRINCIPAL ───────────────────────────────────────────────────

    def analyze(self, df: pd.DataFrame, symbol: str) -> dict | None:
        if len(df) < 120:   # Necesitamos bastantes velas para EMA100
            return None

        df = df.copy()

        # Indicadores
        df['ema_fast'] = df['close'].ewm(span=self.fast, adjust=False).mean()
        df['ema_mid']  = df['close'].ewm(span=self.mid,  adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow, adjust=False).mean()
        df['atr']      = self._calc_atr(df)
        df['adx']      = self._calc_adx(df)
        df['rsi']      = self._calc_rsi(df)
        df['vol_avg']  = df['volume'].rolling(self.vol_window).mean()

        # Usar vela cerrada (iloc[-2])
        curr = df.iloc[-2]
        adx  = curr['adx']
        rsi  = curr['rsi']
        atr  = curr['atr']
        vol  = curr['volume']
        vol_avg = curr['vol_avg']

        # ── FILTRO 1: Tendencia (ADX) ────────────────────────────────────────
        if adx < self.adx_min:
            return None   # Mercado lateral

        # ── FILTRO 2: Volumen ────────────────────────────────────────────────
        if vol_avg > 0 and vol < vol_avg * 0.8:
            return None   # Volumen insuficiente

        # ── DETECTAR CRUCE RECIENTE ──────────────────────────────────────────
        cross_up = cross_dn = False
        for i in range(-self.cross_window - 1, -1):
            p = df.iloc[i - 1]; c = df.iloc[i]
            if p['ema_fast'] <= p['ema_mid'] and c['ema_fast'] > c['ema_mid']:
                cross_up = True
            if p['ema_fast'] >= p['ema_mid'] and c['ema_fast'] < c['ema_mid']:
                cross_dn = True

        # ── SEÑAL LONG ───────────────────────────────────────────────────────
        # EMA9 > EMA21 > EMA100 + cruce reciente + RSI no sobrecomprado
        if (cross_up
                and curr['ema_fast'] > curr['ema_mid'] > curr['ema_slow']
                and rsi < self.rsi_ob):
            entry = float(df.iloc[-1]['close'])
            sl    = round(entry - atr * self.atr_sl_mult, 8)
            risk  = entry - sl
            if risk <= 0: return None
            tp    = round(entry + risk * self.rr_ratio, 8)
            # Breakeven: entrada + 0.05% (cubre comisiones)
            be    = round(entry * 1.0005, 8)
            logger.info(f"✅ [EMA PRO] LONG {symbol} | E={entry:.4f} SL={sl:.4f} TP={tp:.4f} ADX={adx:.1f} RSI={rsi:.1f}")
            return self._sig(symbol, "LONG", entry, sl, tp, be, atr, adx, rsi)

        # ── SEÑAL SHORT ──────────────────────────────────────────────────────
        # EMA9 < EMA21 < EMA100 + cruce reciente + RSI no sobrevendido
        if (cross_dn
                and curr['ema_fast'] < curr['ema_mid'] < curr['ema_slow']
                and rsi > self.rsi_os):
            entry = float(df.iloc[-1]['close'])
            sl    = round(entry + atr * self.atr_sl_mult, 8)
            risk  = sl - entry
            if risk <= 0: return None
            tp    = round(entry - risk * self.rr_ratio, 8)
            be    = round(entry * 0.9995, 8)
            logger.info(f"✅ [EMA PRO] SHORT {symbol} | E={entry:.4f} SL={sl:.4f} TP={tp:.4f} ADX={adx:.1f} RSI={rsi:.1f}")
            return self._sig(symbol, "SHORT", entry, sl, tp, be, atr, adx, rsi)

        return None

    def should_trail_close(self, df: pd.DataFrame, side: str) -> bool:
        """
        Trailing Stop por EMA: cierra cuando EMA9 cruza de vuelta a EMA21.
        Llama esto en cada ciclo de monitoreo.
        """
        if len(df) < 30: return False
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=self.fast, adjust=False).mean()
        df['ema_mid']  = df['close'].ewm(span=self.mid,  adjust=False).mean()
        curr = df.iloc[-1]; prev = df.iloc[-2]
        if side == "LONG":
            # Cerrar LONG si EMA9 vuelve a cruzar por debajo de EMA21
            return prev['ema_fast'] >= prev['ema_mid'] and curr['ema_fast'] < curr['ema_mid']
        else:
            # Cerrar SHORT si EMA9 vuelve a cruzar por encima de EMA21
            return prev['ema_fast'] <= prev['ema_mid'] and curr['ema_fast'] > curr['ema_mid']

    def _sig(self, symbol, side, entry, sl, tp, breakeven, atr, adx, rsi):
        return {
            "symbol":      symbol,
            "signal":      side,
            "entry_price": entry,
            "sl":          sl,
            "tp1":         tp, "tp2": tp, "tp3": tp,
            "tp1_pct":     1.0, "tp2_pct": 0.0, "tp3_pct": 0.0,
            "breakeven_price": breakeven,
            "sl_distance": abs(entry - sl) / entry,
            "atr":         round(atr, 8),
            "adx":         round(adx, 2),
            "rsi":         round(rsi, 2),
            "strategy":    "TRIPLE_EMA_PRO_9_21_100",
        }


ema_strategy = EMAProStrategy()
