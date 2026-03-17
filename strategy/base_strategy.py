import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class InstitutionalSMCStrategy:
    """
    Estrategia de Conceptos de Smart Money (SMC) de Nivel Institucional.
    Basada en metodologías ICT (Inner Circle Trader).
    """

    def __init__(self):
        self.swing_period = 5
        self.fvg_min_size_pct = 0.05
        self.rr_ratio = 3.0
        self.ob_limit = 3

    def identify_fvg(self, df):
        """Identifica Fair Value Gaps (FVG) en el DataFrame."""
        bull_fvg = []
        bear_fvg = []
        
        for i in range(2, len(df)):
            # Bullish FVG
            if df.iloc[i]['low'] > df.iloc[i-2]['high']:
                gap = df.iloc[i]['low'] - df.iloc[i-2]['high']
                if gap > (df.iloc[i]['close'] * self.fvg_min_size_pct / 100):
                    bull_fvg.append({'top': df.iloc[i]['low'], 'bottom': df.iloc[i-2]['high'], 'index': i-1})
            
            # Bearish FVG
            if df.iloc[i]['high'] < df.iloc[i-2]['low']:
                gap = df.iloc[i-2]['low'] - df.iloc[i]['high']
                if gap > (df.iloc[i]['close'] * self.fvg_min_size_pct / 100):
                    bear_fvg.append({'top': df.iloc[i-2]['low'], 'bottom': df.iloc[i]['high'], 'index': i-1})
        
        return bull_fvg, bear_fvg

    def calculate_rsi(self, df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def analyze(self, symbol: str, df: pd.DataFrame):
        if len(df) < 200: # Necesitamos 200 para la EMA
            return None

        # Asegurar tipos numéricos
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Indicadores de Confluencia
        df['vol_ma'] = df['volume'].rolling(window=20).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['rsi'] = self.calculate_rsi(df)

        # 1. Identificar fractales (Swing Points)
        df['high_fractal'] = df['high'].rolling(window=self.swing_period*2+1, center=True).apply(
            lambda x: 1 if x.iloc[self.swing_period] == x.max() else 0, raw=False
        )
        df['low_fractal'] = df['low'].rolling(window=self.swing_period*2+1, center=True).apply(
            lambda x: 1 if x.iloc[self.swing_period] == x.min() else 0, raw=False
        )

        # 2. Identificar FVGs
        bull_fvgs, bear_fvgs = self.identify_fvg(df)
        fvg_indices = [f['index'] for f in bull_fvgs + bear_fvgs]

        bull_obs, bear_obs = [], []
        last_high, last_low = None, None

        for i in range(self.swing_period + 1, len(df)):
            if df.iloc[i - self.swing_period]['high_fractal'] == 1:
                last_high = df.iloc[i - self.swing_period]['high']
            if df.iloc[i - self.swing_period]['low_fractal'] == 1:
                last_low = df.iloc[i - self.swing_period]['low']

            is_institutional = df.iloc[i]['volume'] > (df.iloc[i]['vol_ma'] * 1.2)
            
            if last_high and df.iloc[i]['close'] > last_high:
                for j in range(i-1, max(0, i-20), -1):
                    if df.iloc[j]['close'] < df.iloc[j]['open']:
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        ob = {
                            'low': df.iloc[j]['low'],
                            'high': df.iloc[j]['high'],
                            'index': j,
                            'valid': has_fvg and is_institutional,
                            'type': 'BULLISH'
                        }
                        if not bull_obs or bull_obs[-1]['index'] != j:
                            bull_obs.append(ob)
                        last_high = None
                        break

            if last_low and df.iloc[i]['close'] < last_low:
                for j in range(i-1, max(0, i-20), -1):
                    if df.iloc[j]['close'] > df.iloc[j]['open']:
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        ob = {
                            'low': df.iloc[j]['low'],
                            'high': df.iloc[j]['high'],
                            'index': j,
                            'valid': has_fvg and is_institutional,
                            'type': 'BEARISH'
                        }
                        if not bear_obs or bear_obs[-1]['index'] != j:
                            bear_obs.append(ob)
                        last_low = None
                        break

        # 3. FILTRADO FINAL DE SEÑAL
        current = df.iloc[-1]
        c_price = current['close']
        c_ema = current['ema_200']
        c_rsi = current['rsi']

        # LONG (Mitigación de OB Bull validado + Filtro Tendencia)
        for ob in reversed(bull_obs[-self.ob_limit:]):
            if not ob['valid']: continue
            
            # Confluencia: Sobre EMA 200 y RSI no sobrecomprado
            if c_price > c_ema and c_rsi < 70:
                if current['low'] <= ob['high'] and c_price > ob['low']:
                    sl = ob['low'] - (ob['high'] - ob['low']) * 0.15
                    tp = c_price + (c_price - sl) * self.rr_ratio
                    return {
                        "symbol": symbol,
                        "signal": "LONG",
                        "entry_price": c_price,
                        "sl": sl,
                        "tp": tp,
                        "info": f"SMC LONG: OB + FVG + Vol + EMA (+)"
                    }

        # SHORT (Mitigación de OB Bear validado + Filtro Tendencia)
        for ob in reversed(bear_obs[-self.ob_limit:]):
            if not ob['valid']: continue
            
            # Confluencia: Bajo EMA 200 y RSI no sobrevendido
            if c_price < c_ema and c_rsi > 30:
                if current['high'] >= ob['low'] and c_price < ob['high']:
                    sl = ob['high'] + (ob['high'] - ob['low']) * 0.15
                    tp = c_price - (sl - c_price) * self.rr_ratio
                    return {
                        "symbol": symbol,
                        "signal": "SHORT",
                        "entry_price": c_price,
                        "sl": sl,
                        "tp": tp,
                        "info": f"SMC SHORT: OB + FVG + Vol + EMA (-)"
                    }

        return None

strategy = InstitutionalSMCStrategy()
