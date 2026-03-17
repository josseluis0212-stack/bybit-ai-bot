import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class OrderBlockStrategy:
    """
    Estrategia basada en Conceptos de Smart Money (SMC).
    Identifica Quiebres de Estructura (BOS) y Order Blocks (OB).
    
    Lógica:
    1. Identifica Fractales (máximos y mínimos locales).
    2. Detecta el quiebre de estos fractales (BOS).
    3. Identifica el Order Block (la última vela contraria al movimiento que causó el BOS).
    4. Entra cuando el precio 'mitiga' (regresa a) la zona del OB.
    """

    def __init__(self):
        self.swing_period = 5  # Ventana para fractales
        self.rr_ratio = 3.0     # Ratio Riesgo/Beneficio
        self.ob_limit = 3       # Máximo de OBs activos por dirección

    def analyze(self, symbol: str, df: pd.DataFrame):
        """
        Analiza klines y busca señales basadas en Order Blocks.
        """
        if len(df) < 50:
            return None

        # Asegurar tipos numéricos
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # 1. Identificar fractales para determinar BOS
        # fractal = máximo/mínimo mayor que los 'n' anteriores y posteriores
        df['high_fractal'] = df['high'].rolling(window=self.swing_period*2+1, center=True).apply(
            lambda x: 1 if x.iloc[self.swing_period] == x.max() else 0, raw=False
        )
        df['low_fractal'] = df['low'].rolling(window=self.swing_period*2+1, center=True).apply(
            lambda x: 1 if x.iloc[self.swing_period] == x.min() else 0, raw=False
        )

        bull_obs = []
        bear_obs = []
        last_high = None
        last_low = None

        # Procesar histórica para encontrar OBs vigentes
        # (Se podría optimizar, pero para 250 velas es rápido)
        for i in range(self.swing_period + 1, len(df)):
            # Actualizar fractales confirmados
            if df.iloc[i - self.swing_period]['high_fractal'] == 1:
                last_high = df.iloc[i - self.swing_period]['high']
            if df.iloc[i - self.swing_period]['low_fractal'] == 1:
                last_low = df.iloc[i - self.swing_period]['low']

            # Detectar BOS Alcista -> Crea Bullish OB (Zonas de Compra)
            if last_high and df.iloc[i]['close'] > last_high:
                # Buscar la última vela bajista (OB) antes del inicio del movimiento fuerte
                for j in range(i-1, max(0, i-20), -1):
                    if df.iloc[j]['close'] < df.iloc[j]['open']:
                        ob = {
                            'low': df.iloc[j]['low'],
                            'high': df.iloc[j]['high'],
                            'index': j,
                            'type': 'BULLISH'
                        }
                        if not bull_obs or bull_obs[-1]['index'] != j:
                            bull_obs.append(ob)
                        last_high = None # BOS consumido
                        break

            # Detectar BOS Bajista -> Crea Bearish OB (Zonas de Venta)
            if last_low and df.iloc[i]['close'] < last_low:
                for j in range(i-1, max(0, i-20), -1):
                    if df.iloc[j]['close'] > df.iloc[j]['open']:
                        ob = {
                            'low': df.iloc[j]['low'],
                            'high': df.iloc[j]['high'],
                            'index': j,
                            'type': 'BEARISH'
                        }
                        if not bear_obs or bear_obs[-1]['index'] != j:
                            bear_obs.append(ob)
                        last_low = None
                        break

        # 2. EVALUACIÓN DE SEÑAL ACTUAL (Mitigación)
        current = df.iloc[-1]
        c_price = current['close']

        # Evaluar LONG: El precio regresa a un Bullish OB reciente
        for ob in reversed(bull_obs[-self.ob_limit:]):
            # Condición: El precio toca la zona alta del OB y se mantiene arriba del bajo
            if current['low'] <= ob['high'] and c_price > ob['low']:
                # Calcular SL/TP profesional
                sl = ob['low'] - (ob['high'] - ob['low']) * 0.1 # Un poco debajo del OB
                diff = c_price - sl
                tp = c_price + (diff * self.rr_ratio)
                
                return {
                    "symbol": symbol,
                    "signal": "LONG",
                    "entry_price": c_price,
                    "sl": sl,
                    "tp": tp,
                    "info": f"OB Bullish Mitigado (Index {ob['index']})"
                }

        # Evaluar SHORT: El precio regresa a un Bearish OB reciente
        for ob in reversed(bear_obs[-self.ob_limit:]):
            if current['high'] >= ob['low'] and c_price < ob['high']:
                sl = ob['high'] + (ob['high'] - ob['low']) * 0.1
                diff = sl - c_price
                tp = c_price - (diff * self.rr_ratio)

                return {
                    "symbol": symbol,
                    "signal": "SHORT",
                    "entry_price": c_price,
                    "sl": sl,
                    "tp": tp,
                    "info": f"OB Bearish Mitigado (Index {ob['index']})"
                }

        return None

strategy = OrderBlockStrategy()
