import pandas as pd
import numpy as np
import logging
from config.settings import settings

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
        self.min_rr_ratio = 1.6 # Un poco más exigente para filtrar ruido
        self.max_rr_ratio = 3.5 # Reducido de 6.0 para mayor consistencia
        self.ob_limit = 5
        self.min_iss_long = 80.0 # Subido de 75 para filtrar señales débiles
        self.min_iss_short = 90.0 # Subido de 85 para filtrar señales débiles
        self.min_adx = 22.0 # Filtro de tendencia: Solo operamos con tendencia clara (> 22)

    def calculate_iss(self, candle_ob, impulse_candle, volume_ma):
        """
        ISS = (Desplazamiento * 0.60) + (Volumen Relativo * 0.40)
        """
        # 1. DESPLAZAMIENTO (60%) - Aumentamos exigencia (de 25 a 35)
        displacement = abs(impulse_candle['close'] - candle_ob['close'])
        ob_range = candle_ob['high'] - candle_ob['low']
        displacement_ratio = displacement / ob_range if ob_range > 0 else 0
        displacement_score = min(displacement_ratio * 35, 100) # Más difícil llegar a 100
        
        # 2. VOLUMEN RELATIVO (40%) - Aumentamos exigencia (de 50 a 60)
        relative_volume = impulse_candle['volume'] / volume_ma if volume_ma > 0 else 1
        volume_score = min((relative_volume - 1) * 60, 100)
        
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

    def identify_eqh_eql(self, df, threshold=0.03):
        """
        Identifica máximos y mínimos iguales (EQH/EQL) que actúan como imanes de liquidez.
        threshold: % de diferencia permitida para considerar 'iguales'.
        """
        eqh, eql = [], []
        highs = df[df['high_fractal'] == 1].tail(10)
        lows  = df[df['low_fractal'] == 1].tail(10)
        
        if len(highs) >= 2:
            for i in range(len(highs)):
                for j in range(i+1, len(highs)):
                    diff = abs(highs.iloc[i]['high'] - highs.iloc[j]['high']) / highs.iloc[i]['high'] * 100
                    if diff < threshold:
                        eqh.append({'price': (highs.iloc[i]['high'] + highs.iloc[j]['high'])/2})
        if len(lows) >= 2:
            for i in range(len(lows)):
                for j in range(i+1, len(lows)):
                    diff = abs(lows.iloc[i]['low'] - lows.iloc[j]['low']) / lows.iloc[i]['low'] * 100
                    if diff < threshold:
                        eql.append({'price': (lows.iloc[i]['low'] + lows.iloc[j]['low'])/2})
        return eqh, eql

    def calculate_vwap(self, df):
        """
        Calcula el Volume Weighted Average Price (VWAP) para la sesión actual.
        """
        v = df['volume']
        p = (df['high'] + df['low'] + df['close']) / 3
        vwap = (p * v).cumsum() / v.cumsum()
        return vwap

    def calculate_poc(self, df):
        """
        Identifica el Point of Control (POC) de las últimas 24-48 horas.
        """
        try:
            # Agrupar volumen por niveles de precio (bins de 0.1% del precio actual)
            current_price = df['close'].iloc[-1]
            bin_size = current_price * 0.001 
            
            df_bins = df.copy()
            df_bins['price_bin'] = (df_bins['close'] / bin_size).round() * bin_size
            vol_profile = df_bins.groupby('price_bin')['volume'].sum()
            
            if not vol_profile.empty:
                return vol_profile.idxmax()
        except:
            pass
        return df['close'].iloc[-1]

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
        # 0. CALCULAR INDICADORES ADICIONALES (VOLATILIDAD Y TENDENCIA)
        from ta.trend import ADXIndicator
        adx_ind = ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_ind.adx()
        
        current_adx = df['adx'].iloc[-1]
        if current_adx < self.min_adx:
            # logger.info(f"Omitiendo {symbol} - Baja volatilidad (ADX: {current_adx:.1f})")
            return None

        # --- INTELIGENCIA QUANTUM (VWAP & POC) ---
        df['vwap'] = self.calculate_vwap(df)
        current_vwap = df['vwap'].iloc[-1]
        poc_level = self.calculate_poc(df)
        
        # Filtro de Régimen de Mercado (Desviación Estándar)
        vol_std = df['close'].rolling(window=20).std().iloc[-1]
        avg_std = df['close'].rolling(window=100).std().mean()
        market_regime = "NORMAL"
        if vol_std > avg_std * 2.5: # Volatilidad extrema (Caos)
            market_regime = "CHAOTIC"
            return None # Evitamos operar en caos

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

        # Identificar Liquidez EQH/EQL (Imanes)
        eqh, eql = self.identify_eqh_eql(df)
        
        # TP MÁS PRECISO: Usamos el fractal más reciente (liquidez inmediata) 
        # en lugar del máximo de los últimos 5 ciclos (que suele ser inalcanzable).
        market_range_high = last_highs[-1] 
        market_range_low = last_lows[-1]
        
        # El equilibrio se calcula sobre un rango un poco mayor para filtrar zonas Premium/Discount reales
        equilibrium = (max(last_highs[-5:]) + min(last_lows[-5:])) / 2

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

        # --- LÓGICA DE BREAKER BLOCKS (NUEVO v3.0) ---
        breakers = []
        for ob in bull_obs[-3:]: # Revisar OB alcistas rotos (Bearish Breakers)
            if c_price < ob['low']:
                breakers.append({'price': (ob['low']+ob['high'])/2, 'type': 'BEARISH_BREAKER', 'iss': ob['iss']})
        for ob in bear_obs[-3:]: # Revisar OB bajistas rotos (Bullish Breakers)
            if c_price > ob['high']:
                breakers.append({'price': (ob['low']+ob['high'])/2, 'type': 'BULLISH_BREAKER', 'iss': ob['iss']})

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
                    
                    # QUANTUM FILTER: Solo compras debajo del VWAP (Precio infravalorado)
                    is_undervalued = c_price < current_vwap
                    
                    # HTF Confluence Check
                    htf_ok = (htf_trend == "BULLISH") if settings.HTF_CONFLUENCE else True

                    if (liquidity_sweep or mss) and is_discount and is_undervalued and htf_ok:
                        # OTE 70.5% Refinement: Ajustar entrada si estamos cerca del nivel OTE
                        ote_705 = ob['high'] - (ob['high'] - ob['low']) * 0.705
                        entry_price = min(c_price, ote_705) if c_price > ote_705 else c_price

                        # SL SEGURO: 0.8 * ATR
                        sl = min(ob['low'], current['low']) - (current['atr'] * 0.8)
                        
                        # TP IMÁN: Si hay EQH arriba, ese es nuestro objetivo primario
                        target_tp = eqh[0]['price'] if eqh else market_range_high
                        
                        rr = (target_tp - entry_price) / (entry_price - sl) if (entry_price - sl) > 0 else 0
                        
                        if rr >= self.min_rr_ratio:
                            dist = target_tp - entry_price
                            final_tp = min(target_tp, entry_price + dist * 0.95)
                            max_tp = entry_price + (entry_price - sl) * self.max_rr_ratio
                            final_tp = min(final_tp, max_tp)
                            
                            return {
                                "symbol": symbol, "signal": "LONG", "entry_price": entry_price, "sl": sl, "tp": final_tp,
                                "info": f"QUANTUM v4.0 (ISS: {ob['iss']:.1f}). POC: {poc_level:.2f}"
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
                    
                    # QUANTUM FILTER: Solo ventas arriba del VWAP (Precio sobrevalorado)
                    is_overvalued = c_price > current_vwap
                    
                    # HTF Confluence Check
                    htf_ok = (htf_trend == "BEARISH") if settings.HTF_CONFLUENCE else True

                    if (liquidity_sweep or mss) and is_premium and is_overvalued and htf_ok:
                        # OTE 70.5% Refinement
                        ote_705 = ob['low'] + (ob['high'] - ob['low']) * 0.705
                        entry_price = max(c_price, ote_705) if c_price < ote_705 else c_price

                        # SL SEGURO: 0.8 * ATR
                        sl = max(ob['high'], current['high']) + (current['atr'] * 0.8)
                        
                        # TP IMÁN: Si hay EQL abajo, ese es nuestro objetivo
                        target_tp = eql[0]['price'] if eql else market_range_low
                        
                        rr = (entry_price - target_tp) / (sl - entry_price) if (sl - entry_price) > 0 else 0
                        
                        if rr >= self.min_rr_ratio:
                            dist = entry_price - target_tp
                            final_tp = max(target_tp, entry_price - dist * 0.95)
                            max_tp = entry_price - (sl - entry_price) * self.max_rr_ratio
                            final_tp = max(final_tp, max_tp)
                            
                            return {
                                "symbol": symbol, "signal": "SHORT", "entry_price": entry_price, "sl": sl, "tp": final_tp,
                                "info": f"QUANTUM v4.0 (ISS: {ob['iss']:.1f}). POC: {poc_level:.2f}"
                            }

        # --- LÓGICA DE BREAKER ENTRIES (NUEVO v3.0) ---
        for brk in breakers:
            if brk['type'] == 'BULLISH_BREAKER':
                # El precio debe estar en retesteo del Breaker
                if current['low'] <= brk['price'] * 1.001 and c_price > brk['price']:
                    sl = current['low'] - (current['atr'] * 0.8)
                    target_tp = eqh[0]['price'] if eqh else market_range_high
                    rr = (target_tp - c_price) / (c_price - sl) if (c_price - sl) > 0 else 0
                    if rr >= self.min_rr_ratio:
                        return {
                            "symbol": symbol, "signal": "LONG", "entry_price": c_price, "sl": sl, "tp": target_tp,
                            "info": f"HUNTER v3.0 BREAKER (ISS: {brk['iss']:.1f})"
                        }
            elif brk['type'] == 'BEARISH_BREAKER':
                if current['high'] >= brk['price'] * 0.999 and c_price < brk['price']:
                    sl = current['high'] + (current['atr'] * 0.8)
                    target_tp = eql[0]['price'] if eql else market_range_low
                    rr = (c_price - target_tp) / (sl - c_price) if (sl - c_price) > 0 else 0
                    if rr >= self.min_rr_ratio:
                        return {
                            "symbol": symbol, "signal": "SHORT", "entry_price": c_price, "sl": sl, "tp": target_tp,
                            "info": f"HUNTER v3.0 BREAKER (ISS: {brk['iss']:.1f})"
                        }

        return None

strategy = InstitutionalSMCStrategy()
