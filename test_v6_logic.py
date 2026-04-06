import pandas as pd
import numpy as np
import logging
from strategy.base_strategy import strategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_mock_data(size=200):
    prices = 100 + np.cumsum(np.random.randn(size) * 0.1)
    df = pd.DataFrame({
        'open': prices + np.random.randn(size) * 0.05,
        'high': prices + 0.2,
        'low': prices - 0.2,
        'close': prices,
        'volume': np.random.randint(1000, 5000, size)
    })
    return df

def test_v6_logic():
    print("\n" + "="*50)
    print("VERIFICACIÓN DE LÓGICA HYPER-QUANT ULTRA V6.0 (BALANCED)")
    print("="*50)
    
    df_1m = generate_mock_data(150)
    df_15m = generate_mock_data(150)
    
    # 1. Bias LONG Setup
    df_15m.loc[df_15m.index[-1], 'close'] = 150 # Price far above EMA 100
    
    # --- ESCENARIO A: SMC (Sweep + FVG) ---
    print("\n--- Test A: SMC Sweep + FVG (LONG) ---")
    # Crear un rango de liquidez (mínimo entre -15 y -6)
    df_1m.iloc[-15:-6, df_1m.columns.get_loc('low')] = 100.0
    # Hacer que la vela -2 barra ese mínimo
    df_1m.loc[df_1m.index[-2], 'low'] = 99.5
    df_1m.loc[df_1m.index[-2], 'close'] = 100.5
    # FVG en vela actual (Low actual > High -3)
    prev2_high = df_1m.iloc[-3]['high']
    df_1m.loc[df_1m.index[-1], 'low'] = prev2_high + 0.1
    df_1m.loc[df_1m.index[-1], 'close'] = prev2_high + 0.5
    
    res_smc = strategy.analyze("TESTUSDT", df_1m, df_15m)
    if res_smc and res_smc['reason'] == "SMC (Sweep+FVG)":
        print(f"SUCCESS: SMC Detectado. Entrada: {res_smc['entry_price']:.2f}")
    else:
        print(f"FAILURE: SMC no detectado. Resultado: {res_smc}")

    # --- ESCENARIO B: Trend Pullback (EMA 20) ---
    print("\n--- Test B: Trend Pullback EMA 20 (LONG) ---")
    # Reset df_1m
    df_1m = generate_mock_data(150)
    # Price clearly above EMA 20
    df_1m.iloc[:-2, df_1m.columns.get_loc('close')] = 110
    df_1m.iloc[:-2, df_1m.columns.get_loc('low')] = 109
    
    # Calcular indicadores para tener EMA 20 real
    import ta
    df_1m['ema_20'] = ta.trend.ema_indicator(df_1m['close'], window=20)
    ema_val = df_1m.iloc[-1]['ema_20']
    
    # Vela anterior rompe hacia abajo o toca EMA 20
    df_1m.loc[df_1m.index[-2], 'low'] = ema_val - 0.1
    df_1m.loc[df_1m.index[-2], 'close'] = ema_val + 0.2
    
    # Vela actual cierra arriba de EMA 20
    df_1m.loc[df_1m.index[-1], 'close'] = ema_val + 0.5
    df_1m.loc[df_1m.index[-1], 'low'] = ema_val + 0.1
    
    res_pb = strategy.analyze("TESTUSDT", df_1m, df_15m)
    if res_pb and res_pb['reason'] == "Trend Pullback (EMA 20)":
        print(f"SUCCESS: Pullback Detectado. Entrada: {res_pb['entry_price']:.2f}")
    else:
         print(f"FAILURE: Pullback no detectado. Resultado: {res_pb}")

    print("\n" + "="*50)

if __name__ == "__main__":
    test_v6_logic()
