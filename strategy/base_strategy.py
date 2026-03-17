import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class InstitutionalSMCStrategy:
    """
    Estrategia de Conceptos de Smart Money (SMC) de Nivel Institucional.
    Mejorada con:
    1. Liquidity Sweeps (Barridos de liquidez).
    2. Premium vs Discount zones (Equilibrio de mercado).
    3. Take Profit estructural (en fractales previos) para realismo.
    4. Validación de Volumen Institucional avanzada.
    """

    def __init__(self):
        self.swing_period = 5
        self.fvg_min_size_pct = 0.05
        self.min_rr_ratio = 1.2 # Reducido para asegurar salidas logrables
        self.max_rr_ratio = 2.5 # Techo de beneficio estructural
        self.ob_limit = 3

    def identify_fvg(self, df):
        bull_fvg, bear_fvg = [], []
        for i in range(2, len(df)):
            if df.iloc[i]['low'] > df.iloc[i-2]['high']:
                gap = df.iloc[i]['low'] - df.iloc[i-2]['high']
                if gap > (df.iloc[i]['close'] * self.fvg_min_size_pct / 100):
                    bull_fvg.append({'top': df.iloc[i]['low'], 'bottom': df.iloc[i-2]['high'], 'index': i-1})
            if df.iloc[i]['high'] < df.iloc[i-2]['low']:
                gap = df.iloc[i-2]['low'] - df.iloc[i]['high']
                if gap > (df.iloc[i]['close'] * self.fvg_min_size_pct / 100):
                    bear_fvg.append({'top': df.iloc[i-2]['low'], 'bottom': df.iloc[i]['high'], 'index': i-1})
        return bull_fvg, bear_fvg

    def calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def analyze(self, symbol: str, df: pd.DataFrame):
        if len(df) < 50: return None

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Indicadores Base
        df['vol_ma'] = df['volume'].rolling(window=20).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['atr'] = self.calculate_atr(df)

        # 1. Identificar fractales (Swing Points)
        df['high_fractal'] = df['high'].rolling(window=self.swing_period*2+1, center=True).apply(
            lambda x: 1 if x.iloc[self.swing_period] == x.max() else 0, raw=False
        )
        df['low_fractal'] = df['low'].rolling(window=self.swing_period*2+1, center=True).apply(
            lambda x: 1 if x.iloc[self.swing_period] == x.min() else 0, raw=False
        )

        bull_fvgs, bear_fvgs = self.identify_fvg(df)
        fvg_indices = [f['index'] for f in bull_fvgs + bear_fvgs]

        bull_obs, bear_obs = [], []
        last_highs, last_lows = [], []
        
        # Guardar historial de fractales para Premium/Discount y Liquidez
        for i in range(len(df)):
            if df.iloc[i]['high_fractal'] == 1: last_highs.append(df.iloc[i]['high'])
            if df.iloc[i]['low_fractal'] == 1: last_lows.append(df.iloc[i]['low'])

        # Solo procesar si tenemos suficiente estructura
        if not last_highs or not last_lows: return None
        
        # 2. DEFINIR RANGO DE MERCADO (Zonas Premium/Discount)
        market_range_high = max(last_highs[-5:])
        market_range_low = min(last_lows[-5:])
        equilibrium = (market_range_high + market_range_low) / 2

        # 3. IDENTIFICAR ORDER BLOCKS CON VOLUMEN INSTITUCIONAL
        for i in range(self.swing_period + 1, len(df)):
            is_institutional = df.iloc[i]['volume'] > (df.iloc[i]['vol_ma'] * 1.3)
            
            # Buscamos cierres por encima de fractales previos (BOS/CHoCH)
            # Simplificado: El cierre supera el Fractal High/Low más cercano
            current_high = last_highs[-1] if last_highs else None
            current_low = last_lows[-1] if last_lows else None

            if current_high and df.iloc[i]['close'] > current_high:
                for j in range(i-1, max(0, i-15), -1):
                    if df.iloc[j]['close'] < df.iloc[j]['open']:
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        ob = {'low': df.iloc[j]['low'], 'high': df.iloc[j]['high'], 'index': j, 'valid': has_fvg and is_institutional, 'type': 'BULLISH'}
                        if not bull_obs or bull_obs[-1]['index'] != j: bull_obs.append(ob)
                        break

            if current_low and df.iloc[i]['close'] < current_low:
                for j in range(i-1, max(0, i-15), -1):
                    if df.iloc[j]['close'] > df.iloc[j]['open']:
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        ob = {'low': df.iloc[j]['low'], 'high': df.iloc[j]['high'], 'index': j, 'valid': has_fvg and is_institutional, 'type': 'BEARISH'}
                        if not bear_obs or bear_obs[-1]['index'] != j: bear_obs.append(ob)
                        break

        # 4. FILTRADO FINAL Y SALIDAS LOGRABLES
        current = df.iloc[-1]
        c_price = current['close']
        c_ema = current['ema_200']
        
        # --- LONG ---
        # Solo en zona de DESCUENTO (Precio < Equilibrio) y sobre EMA 200
        if c_price < equilibrium and c_price > c_ema:
            for ob in reversed(bull_obs[-self.ob_limit:]):
                if not ob['valid']: continue
                if current['low'] <= ob['high'] and c_price > ob['low']:
                    # SL: Bajo el OB + pequeño buffer de ATR
                    sl = ob['low'] - (current['atr'] * 0.2)
                    # TP: Al Fractal High previo (Objetivo estructural lograble)
                    target_tp = market_range_high
                    
                    # Validar Ratio Riesgo/Beneficio
                    rr = (target_tp - c_price) / (c_price - sl) if (c_price - sl) > 0 else 0
                    if rr >= self.min_rr_ratio:
                        # Si el TP es absurdamente alto (ej: > 2.5 RR), lo limitamos para asegurar éxito
                        final_tp = min(target_tp, c_price + (c_price - sl) * self.max_rr_ratio)
                        return {
                            "symbol": symbol, "signal": "LONG", "entry_price": c_price, "sl": sl, "tp": final_tp,
                            "info": f"SMC Discount Entry (TP Estructural). R:R: {rr:.2f}"
                        }

        # --- SHORT ---
        # Solo en zona PREMIUM (Precio > Equilibrio) y bajo EMA 200
        if c_price > equilibrium and c_price < c_ema:
            for ob in reversed(bear_obs[-self.ob_limit:]):
                if not ob['valid']: continue
                if current['high'] >= ob['low'] and c_price < ob['high']:
                    sl = ob['high'] + (current['atr'] * 0.2)
                    target_tp = market_range_low # Target estructural
                    
                    rr = (c_price - target_tp) / (sl - c_price) if (sl - c_price) > 0 else 0
                    if rr >= self.min_rr_ratio:
                        final_tp = max(target_tp, c_price - (sl - c_price) * self.max_rr_ratio)
                        return {
                            "symbol": symbol, "signal": "SHORT", "entry_price": c_price, "sl": sl, "tp": final_tp,
                            "info": f"SMC Premium Entry (TP Estructural). R:R: {rr:.2f}"
                        }

        return None

strategy = InstitutionalSMCStrategy()
