import pandas as pd
import ta
import logging

logger = logging.getLogger(__name__)

class TrendPullbackStrategy:
    """
    Estrategia Cuantitativa de Tendencia y Retroceso (Trend-Pullback).
    
    Lógica de Compra (LONG):
    1. Filtro Macro: Precio actual > EMA 200 (Tendencia alcista mayor).
    2. Filtro Micro: EMA 21 > EMA 200.
    3. Gatillo: RSI (14) < 35 (Sobrevendido en una tendencia alcista).
    
    Lógica de Venta (SHORT):
    1. Filtro Macro: Precio actual < EMA 200 (Tendencia bajista mayor).
    2. Filtro Micro: EMA 21 < EMA 200.
    3. Gatillo: RSI (14) > 65 (Sobrecomprado en una tendencia bajista).
    
    Gestión de Riesgo:
    - Stop Loss temporal: 1.5 * ATR(14) para calcular riesgo.
    - Take Profit temporal: 3.0 * ATR(14) (Risk/Reward 1:2).
    """

    def __init__(self):
        self.ema_fast = 21
        self.ema_slow = 200
        self.rsi_period = 14
        self.rsi_oversold = 40
        self.rsi_overbought = 60
        self.atr_period = 14
        self.atr_sl_multiplier = 1.5
        self.atr_tp_multiplier = 3.0

    def analyze(self, symbol: str, df: pd.DataFrame):
        """
        Analiza un DataFrame de klines (velas) y devuelve una señal.
        Se espera que el df tenga al menos las columnas: ['open', 'high', 'low', 'close']
        """
        if len(df) < self.ema_slow + 1:
            # No hay suficientes datos para calcular la EMA 200
            return None

        # Convertir a numérico si no lo están
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calcular indicadores
        try:
            df['ema21'] = ta.trend.ema_indicator(close=df['close'], window=self.ema_fast)
            df['ema200'] = ta.trend.ema_indicator(close=df['close'], window=self.ema_slow)
            df['rsi'] = ta.momentum.rsi(close=df['close'], window=self.rsi_period)
            
            # True Range y ATR
            atr_indicator = ta.volatility.AverageTrueRange(
                high=df['high'], low=df['low'], close=df['close'], window=self.atr_period
            )
            df['atr'] = atr_indicator.average_true_range()
            
        except Exception as e:
            logger.error(f"Error calculando indicadores para {symbol}: {e}")
            return None

        # Obtener la vela más reciente y la anterior (para evitar repintado se usa la reciente cerrada, pero aquí tomamos la última disponible)
        # Usamos iloc[-1] como la actual o iloc[-2] si queremos solo la vela cerrada.
        current = df.iloc[-1]
        
        # Saltamos si hay NaNs en los indicadores críticos
        if pd.isna(current['ema200']) or pd.isna(current['atr']):
            return None

        signal = None
        tp_price = None
        sl_price = None
        
        c_price = current['close']
        c_ema21 = current['ema21']
        c_ema200 = current['ema200']
        c_rsi = current['rsi']
        c_atr = current['atr']

        # Evaluar LONG
        if c_price > c_ema200 and c_ema21 > c_ema200:
            if c_rsi < self.rsi_oversold:
                signal = "LONG"
                sl_price = c_price - (c_atr * self.atr_sl_multiplier)
                tp_price = c_price + (c_atr * self.atr_tp_multiplier)

        # Evaluar SHORT
        elif c_price < c_ema200 and c_ema21 < c_ema200:
            if c_rsi > self.rsi_overbought:
                signal = "SHORT"
                sl_price = c_price + (c_atr * self.atr_sl_multiplier)
                tp_price = c_price - (c_atr * self.atr_tp_multiplier)

        if signal:
            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": c_price,
                "sl": sl_price,
                "tp": tp_price,
                "atr": c_atr
            }
        
        return None

strategy = TrendPullbackStrategy()
