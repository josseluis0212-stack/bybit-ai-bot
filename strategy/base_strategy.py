import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant V3: Estrategia Autónoma de Reversión Vectorizada (VMR).
    Optimizado para marcos de 1 minuto y alta frecuencia.
    
    Lógica:
    1. Identifica extremos de volatilidad usando Bandas de Bollinger a 2.5 desviaciones.
    2. Filtra por flujo de dinero institucional (MFI) para detectar clímax de compras/ventas.
    3. Usa VWAP como ancla de 'Valor Justo' para asegurar que operamos hacia la media.
    4. Gestión de Riesgo dinámica basada en ATR.
    """

    def __init__(self):
        self.bb_window = 20
        self.bb_dev = 2.0
        self.mfi_period = 14
        self.mfi_oversold = 30
        self.mfi_overbought = 70
        self.atr_period = 14
        self.atr_sl_multiplier = 1.5
        self.atr_tp_multiplier = 2.2 # R/R ~1.5

    def calculate_vwap(self, df):
        """Calcula el VWAP sesional (simplificado para el DF actual)"""
        v = df['volume'].values
        tp = (df['high'] + df['low'] + df['close']).values / 3
        cumsum_v = v.cumsum()
        return np.divide((tp * v).cumsum(), cumsum_v, out=np.zeros_like(cumsum_v), where=cumsum_v!=0)

    def analyze(self, symbol: str, df: pd.DataFrame):
        if len(df) < self.bb_window + 1:
            return None

        # Asegurar tipos numéricos
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        try:
            # Bandas de Bollinger (Configuración Extrema)
            indicator_bb = ta.volatility.BollingerBands(
                close=df['close'], window=self.bb_window, window_dev=self.bb_dev
            )
            df['bb_high'] = indicator_bb.bollinger_hband()
            df['bb_low'] = indicator_bb.bollinger_lband()
            df['bb_mid'] = indicator_bb.bollinger_mavg()

            # Money Flow Index (Exhaustión de Volumen)
            from ta.volume import MFIIndicator
            df['mfi'] = MFIIndicator(
                high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], window=self.mfi_period
            ).money_flow_index()

            # ATR para Riesgo
            df['atr'] = ta.volatility.average_true_range(
                high=df['high'], low=df['low'], close=df['close'], window=self.atr_period
            )

            # VWAP (Valor Justo)
            df['vwap'] = self.calculate_vwap(df)

        except Exception as e:
            logger.error(f"Error en indicadores para {symbol}: {e}")
            return None

        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        if pd.isna(current['bb_high']) or pd.isna(current['mfi']) or pd.isna(current['atr']):
            return None

        price = current['close']
        vwap = current['vwap']
        mfi = current['mfi']
        atr = current['atr']
        
        signal = None
        sl_price = None
        tp_price = None

        # --- Lógica de LONG (Reversión al Alza) ---
        # Condición: El precio rompió la banda inferior y el MFI indica pánico vendedor (sobrevendido)
        # Filtro: Solo entramos si estamos por debajo del VWAP (comprando barato)
        if price < vwap:
            if (prev['close'] < prev['bb_low'] or current['low'] < current['bb_low']) and mfi < self.mfi_oversold:
                # Gatillo: Vela actual cierra por encima de la media de la vela anterior o muestra rechazo
                if price > prev['low']:
                    signal = "LONG"
                    sl_price = price - (atr * self.atr_sl_multiplier)
                    tp_price = price + (atr * self.atr_tp_multiplier)

        # --- Lógica de SHORT (Reversión a la Baja) ---
        # Condición: El precio rompió la banda superior y el MFI indica euforia compradora (sobrecomprado)
        # Filtro: Solo entramos si estamos por encima del VWAP (vendiendo caro)
        elif price > vwap:
            if (prev['close'] > prev['bb_high'] or current['high'] > current['bb_high']) and mfi > self.mfi_overbought:
                # Gatillo: Rechazo en la parte superior
                if price < prev['high']:
                    signal = "SHORT"
                    sl_price = price + (atr * self.atr_sl_multiplier)
                    tp_price = price - (atr * self.atr_tp_multiplier)

        if signal:
            # Validación final: No entrar si el SL es absurdo o el TP está demasiado cerca
            if abs(price - sl_price) / price < 0.001: # Menos de 0.1% es ruido
                return None

            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": price,
                "sl": sl_price,
                "tp": tp_price,
                "atr": atr,
                "vwap": vwap
            }

        return None

strategy = HyperQuantStrategy()
