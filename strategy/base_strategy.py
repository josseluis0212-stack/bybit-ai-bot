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
        self.min_rr_ratio = 1.5
        self.max_rr_ratio = 6.0 # Aumentado para mayor potencial institucional
        self.ob_limit = 5
        self.min_iss_long = 75.0
        self.min_iss_short = 85.0 # Filtro más estricto para evitar shorts débiles

    def calculate_iss(self, candle_ob, impulse_candle, volume_ma):
        """
        ISS = (Desplazamiento * 0.60) + (Volumen Relativo * 0.40)
        """
        # 1. DESPLAZAMIENTO (60%)
        displacement = abs(impulse_candle['close'] - candle_ob['close'])
        ob_range = candle_ob['high'] - candle_ob['low']
        displacement_ratio = displacement / ob_range if ob_range > 0 else 0
        displacement_score = min(displacement_ratio * 25, 100) # 4x OB range = 100 pts
        
        # 2. VOLUMEN RELATIVO (40%)
        relative_volume = impulse_candle['volume'] / volume_ma if volume_ma > 0 else 1
        volume_score = min((relative_volume - 1) * 50, 100) # 3x vol = 100 pts
        
        return (displacement_score * 0.6) + (volume_score * 0.4)

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

    def is_killzone(self):
        """
        Verifica si la hora actual está dentro de una Killzone Institucional (EST).
        London: 2:00 - 5:00 AM EST
        New York: 8:00 - 11:00 AM EST
        """
        from datetime import datetime
        import pytz
        
        if not settings.KILLZONE_FILTER:
            return True
            
        tz_est = pytz.timezone('US/Eastern')
        now_est = datetime.now(tz_est)
        hour = now_est.hour
        
        is_london = 2 <= hour < 5
        is_ny = 8 <= hour < 11
        
        return is_london or is_ny

    def get_htf_trend(self, df_htf):
        """
        Determina la tendencia en temporalidad superior (1H) usando EMA 200.
        """
        if df_htf is None or len(df_htf) < 200:
            return "NEUTRAL"
            
        df_htf['close'] = pd.to_numeric(df_htf['close'], errors='coerce')
        ema_200 = df_htf['close'].ewm(span=200, adjust=False).mean().iloc[-1]
        current_price = df_htf['close'].iloc[-1]
        
        if current_price > ema_200:
            return "BULLISH"
        elif current_price < ema_200:
            return "BEARISH"
        return "NEUTRAL"

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame = None):
        if len(df) < 50: return None
        
        # Filtro de Killzone
        if not self.is_killzone():
            # logger.info(f"Omitiendo {symbol} - Fuera de Killzone Institucional")
            return None
            
        # Filtro de Tendencia HTF
        htf_trend = "NEUTRAL"
        if settings.HTF_CONFLUENCE and df_htf is not None:
            htf_trend = self.get_htf_trend(df_htf)

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

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
        
        for i in range(len(df)):
            if df.iloc[i]['high_fractal'] == 1: last_highs.append(df.iloc[i]['high'])
            if df.iloc[i]['low_fractal'] == 1: last_lows.append(df.iloc[i]['low'])

        if not last_highs or not last_lows: return None
        
        market_range_high = max(last_highs[-5:])
        market_range_low = min(last_lows[-5:])
        equilibrium = (market_range_high + market_range_low) / 2

        # 2. IDENTIFICAR ORDER BLOCKS INSTITUCIONALES (ISS > 70)
        for i in range(self.swing_period + 1, len(df)):
            current_high = last_highs[-1] if last_highs else None
            current_low = last_lows[-1] if last_lows else None

            # Bullish OB (BOS)
            if current_high and df.iloc[i]['close'] > current_high:
                for j in range(i-1, max(0, i-15), -1):
                    if df.iloc[j]['close'] < df.iloc[j]['open']:
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        iss = self.calculate_iss(df.iloc[j], df.iloc[i], df.iloc[i]['vol_ma'])
                        if iss >= self.min_iss_long and has_fvg:
                            ob = {'low': df.iloc[j]['low'], 'high': df.iloc[j]['high'], 'index': j, 'iss': iss, 'type': 'BULLISH', 'fvg': True}
                            if not bull_obs or bull_obs[-1]['index'] != j: bull_obs.append(ob)
                        break

            # Bearish OB (BOS)
            if current_low and df.iloc[i]['close'] < current_low:
                for j in range(i-1, max(0, i-15), -1):
                    if df.iloc[j]['close'] > df.iloc[j]['open']:
                        has_fvg = any(idx == j or idx == j+1 for idx in fvg_indices)
                        iss = self.calculate_iss(df.iloc[j], df.iloc[i], df.iloc[i]['vol_ma'])
                        if iss >= self.min_iss_short and has_fvg:
                            ob = {'low': df.iloc[j]['low'], 'high': df.iloc[j]['high'], 'index': j, 'iss': iss, 'type': 'BEARISH', 'fvg': True}
                            if not bear_obs or bear_obs[-1]['index'] != j: bear_obs.append(ob)
                        break

        # 3. LÓGICA DE SNIPER (Inducement + OTE)
        current = df.iloc[-1]
        c_price = current['close']
        
        # --- LONG (Cazador) ---
        if c_price < equilibrium and c_price > current['ema_200']:
            for ob in reversed(bull_obs[-self.ob_limit:]):
                # Detectar Inducement (Precio barriendo liquidez previa cerca del OB)
                recent_lows = df['low'].iloc[-10:-1].min()
                liquidity_sweep = current['low'] < recent_lows
                
                # Zona de interés Sniper (Toque de OB o Zona OTE)
                if current['low'] <= ob['high'] and c_price > ob['low']:
                    # Confirmación MSS (Simplificada: Cierre anterior fue bajista, actual es alcista o fuerte)
                    mss = df.iloc[-2]['close'] < df.iloc[-2]['open'] and c_price > df.iloc[-2]['high']
                    
                    # PD Array Check: Longs only in Discount (< 50% of recent range)
                    is_discount = c_price < equilibrium
                    
                    # HTF Confluence Check
                    htf_ok = (htf_trend == "BULLISH") if settings.HTF_CONFLUENCE else True

                    if (liquidity_sweep or mss) and is_discount and htf_ok:
                        sl = min(ob['low'], current['low']) - (current['atr'] * 0.3)
                        target_tp = market_range_high
                        rr = (target_tp - c_price) / (c_price - sl) if (c_price - sl) > 0 else 0
                        
                        if rr >= self.min_rr_ratio:
                            final_tp = min(target_tp, c_price + (c_price - sl) * self.max_rr_ratio)
                            return {
                                "symbol": symbol, "signal": "LONG", "entry_price": c_price, "sl": sl, "tp": final_tp,
                                "info": f"HUNTER Sniper (ISS: {ob['iss']:.1f}). HTF: {htf_trend}. PD: Discount"
                            }

        # --- SHORT (Cazador) ---
        if c_price > equilibrium and c_price < current['ema_200']:
            for ob in reversed(bear_obs[-self.ob_limit:]):
                recent_highs = df['high'].iloc[-10:-1].max()
                liquidity_sweep = current['high'] > recent_highs
                
                if current['high'] >= ob['low'] and c_price < ob['high']:
                    mss = df.iloc[-2]['close'] > df.iloc[-2]['open'] and c_price < df.iloc[-2]['low']
                    
                    # PD Array Check: Shorts only in Premium (> 50% of recent range)
                    is_premium = c_price > equilibrium
                    
                    # HTF Confluence Check
                    htf_ok = (htf_trend == "BEARISH") if settings.HTF_CONFLUENCE else True

                    if (liquidity_sweep or mss) and is_premium and htf_ok:
                        sl = max(ob['high'], current['high']) + (current['atr'] * 0.3)
                        target_tp = market_range_low
                        rr = (c_price - target_tp) / (sl - c_price) if (sl - c_price) > 0 else 0
                        
                        if rr >= self.min_rr_ratio:
                            final_tp = max(target_tp, c_price - (sl - c_price) * self.max_rr_ratio)
                            return {
                                "symbol": symbol, "signal": "SHORT", "entry_price": c_price, "sl": sl, "tp": final_tp,
                                "info": f"HUNTER Sniper (ISS: {ob['iss']:.1f}). HTF: {htf_trend}. PD: Premium"
                            }

        return None

strategy = InstitutionalSMCStrategy()
