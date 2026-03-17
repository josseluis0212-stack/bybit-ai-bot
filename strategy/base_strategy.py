import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class InstitutionalSMCStrategy:
    """
    Estrategia de Conceptos de Smart Money (SMC) de Nivel Institucional.
    Basada en metodologías ICT (Inner Circle Trader).
    
    Componentes:
    1. Liquidity Sweep: Tomar liquidez de altos/bajos previos.
    2. CHoCH (Change of Character): Cambio de tendencia estructural.
    3. FVG (Fair Value Gap): Desequilibrio que valida el movimiento.
    4. Order Block (OB): Zona de entrada institucional.
    """

    def __init__(self):
        self.swing_period = 5
        self.fvg_min_size_pct = 0.05 # Tamaño mínimo del FVG relativo al precio
        self.rr_ratio = 3.0
        self.ob_limit = 3

    def identify_fvg(self, df):
        """Identifica Fair Value Gaps (FVG) en el DataFrame"""
        bull_fvg = []
        bear_fvg = []
        
        # Un FVG es un hueco entre la mecha de la vela 1 y la vela 3
        for i in range(2, len(df)):
            # Bullish FVG (Gap al alza)
            # El bajo de la vela i es mayor que el alto de la vela i-2
            if df.iloc[i]['low'] > df.iloc[i-2]['high']:
                gap = df.iloc[i]['low'] - df.iloc[i-2]['high']
                if gap > (df.iloc[i]['close'] * self.fvg_min_size_pct / 100):
                    bull_fvg.append({
                        'top': df.iloc[i]['low'],
                        'bottom': df.iloc[i-2]['high'],
                        'index': i-1
                    })
            
            # Bearish FVG (Gap a la baja)
            # El alto de la vela i es menor que el bajo de la vela i-2
            if df.iloc[i]['high'] < df.iloc[i-2]['low']:
                gap = df.iloc[i-2]['low'] - df.iloc[i]['high']
                if gap > (df.iloc[i]['close'] * self.fvg_min_size_pct / 100):
                    bear_fvg.append({
                        'top': df.iloc[i-2]['low'],
                        'bottom': df.iloc[i]['high'],
                        'index': i-1
                    })
        return bull_fvg, bear_fvg

    def analyze(self, symbol: str, df: pd.DataFrame):
        if len(df) < 50: return None

        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

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
        trend = "Neutral"

        for i in range(self.swing_period + 1, len(df)):
            # Actualizar fractales de referencia
            if df.iloc[i - self.swing_period]['high_fractal'] == 1:
                last_high = df.iloc[i - self.swing_period]['high']
            if df.iloc[i - self.swing_period]['low_fractal'] == 1:
                last_low = df.iloc[i - self.swing_period]['low']

            # Verificación de Liquidez (Sweep)
            # El precio supera el fractal anterior momentáneamente (mecha) pero cierra dentro o rompe fuerte
            
            # CHoCH/BOS Alcista
            if last_high and df.iloc[i]['close'] > last_high:
                # Si veníamos de tendencia bajista, esto es un CHoCH
                # Buscamos si hay un OB validado por un FVG cercano
                for j in range(i-1, max(0, i-20), -1):
                    if df.iloc[j]['close'] < df.iloc[j]['open']:
                        # Validar si este OB tiene un FVG justo después (desplazamiento institucional)
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        ob = {
                            'low': df.iloc[j]['low'],
                            'high': df.iloc[j]['high'],
                            'index': j,
                            'valid': has_fvg,
                            'type': 'BULLISH'
                        }
                        if not bull_obs or bull_obs[-1]['index'] != j:
                            bull_obs.append(ob)
                        last_high = None
                        break

            # CHoCH/BOS Bajista
            if last_low and df.iloc[i]['close'] < last_low:
                for j in range(i-1, max(0, i-20), -1):
                    if df.iloc[j]['close'] > df.iloc[j]['open']:
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        ob = {
                            'low': df.iloc[j]['low'],
                            'high': df.iloc[j]['high'],
                            'index': j,
                            'valid': has_fvg,
                            'type': 'BEARISH'
                        }
                        if not bear_obs or bear_obs[-1]['index'] != j:
                            bear_obs.append(ob)
                        last_low = None
                        break

        # 3. FILTRADO FINAL DE SEÑAL
        current = df.iloc[-1]
        c_price = current['close']

        # Entrar solo en OBs validados por FVG (Institutional Displacement)
        # LONG
        for ob in reversed(bull_obs[-self.ob_limit:]):
            if not ob['valid']: continue # Saltar si no tiene FVG (débil)
            
            # Condición de entrada: El precio regresa a la zona alta del OB (Mitigación)
            if current['low'] <= ob['high'] and c_price > ob['low']:
                sl = ob['low'] - (ob['high'] - ob['low']) * 0.1
                tp = c_price + (c_price - sl) * self.rr_ratio
                return {
                    "symbol": symbol,
                    "signal": "LONG",
                    "entry_price": c_price,
                    "sl": sl,
                    "tp": tp,
                    "info": f"OB Institucional validado con FVG (Index {ob['index']})"
                }

        # SHORT
        for ob in reversed(bear_obs[-self.ob_limit:]):
            if not ob['valid']: continue
            
            if current['high'] >= ob['low'] and c_price < ob['high']:
                sl = ob['high'] + (ob['high'] - ob['low']) * 0.1
                tp = c_price - (sl - c_price) * self.rr_ratio
                return {
                    "symbol": symbol,
                    "signal": "SHORT",
                    "entry_price": c_price,
                    "sl": sl,
                    "tp": tp,
                    "info": f"OB Institucional validado con FVG (Index {ob['index']})"
                }

        return None

strategy = InstitutionalSMCStrategy()
