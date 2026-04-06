import pandas as pd
import ta
import logging
import numpy as np

logger = logging.getLogger(__name__)

class HyperQuantStrategy:
    """
    Hyper-Quant Ultra V5.0: Estrategia de Smart Money Concepts (SMC).
    Especializada en Liquidity Sweeps (Sacudidas) y Fair Value Gaps (FVG).
    
    Lógica:
    1. Filtro de Bias (15m): Solo opera a favor de la tendencia mayor (EMA 200).
    2. Liquidity Sweep (1m): Detecta cuando el precio limpia stops de minoristas.
    3. FVG (Displacement): Entra en el desequilibrio dejado por el dinero institucional.
    4. Riesgo: 2x ATR para SL, 3x ATR para TP (R/R 1.5).
    """

    def __init__(self):
        self.ema_period = 200
        self.atr_period = 14
        self.atr_sl_multiplier = 2.0
        self.atr_tp_multiplier = 3.0

    def analyze(self, symbol: str, df: pd.DataFrame, df_htf: pd.DataFrame):
        if len(df) < 50 or len(df_htf) < self.ema_period:
            return None

        # Asegurar tipos numéricos
        for d in [df, df_htf]:
            for col in ['open', 'high', 'low', 'close', 'volume']:
                d[col] = pd.to_numeric(d[col], errors='coerce')

        try:
            # 1. Calcular Bias en HTF (15m)
            df_htf['ema_200'] = ta.trend.ema_indicator(df_htf['close'], window=self.ema_period)
            htf_price = df_htf.iloc[-1]['close']
            htf_ema = df_htf.iloc[-1]['ema_200']
            bias = "LONG" if htf_price > htf_ema else "SHORT"

            # 2. Indicadores en 1m
            df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=self.atr_period)
            
        except Exception as e:
            logger.error(f"Error en indicadores V5 para {symbol}: {e}")
            return None

        # Datos actuales 1m
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        atr = curr['atr']
        price = curr['close']
        
        signal = None
        sl_price = None
        tp_price = None

        # --- Lógica SMC LONG ---
        if bias == "LONG":
            # 1. Liquidity Sweep: El mínimo de la vela anterior limpió el mínimo de las 5 velas previas
            lowest_5 = df.iloc[-7:-2]['low'].min()
            if prev['low'] < lowest_5 and prev['close'] > lowest_5:
                # 2. FVG (Fair Value Gap) Alcista detectado en las últimas 3 velas
                # Estructura: Low(Vela 3) > High(Vela 1)
                if curr['low'] > prev2['high']:
                    signal = "LONG"
                    # SL bajo la mecha de la sacudida
                    sl_price = min(prev['low'], curr['low']) - (atr * 0.5)
                    tp_price = price + (atr * self.atr_tp_multiplier)

        # --- Lógica SMC SHORT ---
        elif bias == "SHORT":
            # 1. Liquidity Sweep: El máximo de la vela anterior limpió el máximo de las 5 velas previas
            highest_5 = df.iloc[-7:-2]['high'].max()
            if prev['high'] > highest_5 and prev['close'] < highest_5:
                # 2. FVG Bajista
                # Estructura: High(Vela 3) < Low(Vela 1)
                if curr['high'] < prev2['low']:
                    signal = "SHORT"
                    sl_price = max(prev['high'], curr['high']) + (atr * 0.5)
                    tp_price = price - (atr * self.atr_tp_multiplier)

        if signal:
            # Filtro de comisiones: TP debe ser al menos 0.25% (Bybit coms ~0.1% total)
            potential_gain = abs(price - tp_price) / price
            if potential_gain < 0.0025:
                return None

            return {
                "symbol": symbol,
                "signal": signal,
                "entry_price": price,
                "sl": sl_price,
                "tp": tp_price,
                "bias": bias
            }

        return None

strategy = HyperQuantStrategy()

strategy = HyperQuantStrategy()
