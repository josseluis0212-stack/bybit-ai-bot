import pandas as pd
import numpy as np
from strategy.base_strategy import strategy
import logging

logging.basicConfig(level=logging.INFO)

def generate_mock_data(size=500, seed=42):
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.randn(size) * 0.1)
    high = close + np.abs(np.random.randn(size) * 0.2)
    low = close - np.abs(np.random.randn(size) * 0.2)
    open_p = close + np.random.randn(size) * 0.05
    volume = np.random.randint(1000, 5000, size)
    
    df = pd.DataFrame({
        'open': open_p,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    return df

def test_v5_logic():
    print("\n" + "="*50)
    print("VERIFICACIÓN DE LÓGICA HYPER-QUANT ULTRA V5.0 (SMC/FVG)")
    print("="*50)
    
    df_1m = generate_mock_data(100)
    df_15m = generate_mock_data(300) # Suficiente para EMA 200
    
    # Caso 1: Test sin señales (Mercado Aleatorio)
    res = strategy.analyze("BTCUSDT", df_1m, df_15m)
    print(f"Análisis Inicial (Sin Señal): {res}")
    
    # Caso 2: Forzar un LONG con SMC (Sweep + FVG)
    print("\n--- Forzando Escenario LONG (Trend + Sweep + FVG) ---")
    
    # 2.1 Garantizar Bias LONG (Precio > EMA 200)
    # EMA 200 de df_15m
    df_15m.loc[df_15m.index[-1], 'close'] = 150 # Muy por encima del inicio
    
    # 2.2 Crear Liquidity Sweep en 1m
    # El mínimo de 5 velas atrás (previos a la penúltima)
    lowest_5 = df_1m.iloc[-7:-2]['low'].min()
    
    # La vela anterior (penúltima) limpia el mínimo y cierra arriba
    df_1m.loc[df_1m.index[-2], 'low'] = lowest_5 - 0.5
    df_1m.loc[df_1m.index[-2], 'close'] = lowest_5 + 0.1
    df_1m.loc[df_1m.index[-2], 'high'] = lowest_5 + 0.5
    
    # 2.3 Crear FVG en la vela actual (Low actual > High ante-penúltima)
    prev2_high = df_1m.iloc[-3]['high']
    df_1m.loc[df_1m.index[-1], 'low'] = prev2_high + 0.2
    df_1m.loc[df_1m.index[-1], 'close'] = prev2_high + 0.5
    df_1m.loc[df_1m.index[-1], 'high'] = prev2_high + 1.0
    
    res_long = strategy.analyze("BTCUSDT", df_1m, df_15m)
    if res_long and res_long['signal'] == "LONG":
        print("[✅] ÉXITO: Detección de SMC LONG Correcta.")
        print(f"    Entrada: {res_long['entry_price']:.2f}")
        print(f"    SL:      {res_long['sl']:.2f}")
        print(f"    TP:      {res_long['tp']:.2f}")
    else:
        print("[❌] FALLO: No se detectó el SMC LONG forzado.")

    # Caso 3: Forzar un SHORT con SMC
    print("\n--- Forzando Escenario SHORT (Trend + Sweep + FVG) ---")
    df_15m.loc[df_15m.index[-1], 'close'] = 50 # Muy por debajo de EMA 200
    
    highest_5 = df_1m.iloc[-7:-2]['high'].max()
    df_1m.loc[df_1m.index[-2], 'high'] = highest_5 + 0.5
    df_1m.loc[df_1m.index[-2], 'close'] = highest_5 - 0.1
    
    prev2_low = df_1m.iloc[-3]['low']
    df_1m.loc[df_1m.index[-1], 'high'] = prev2_low - 0.2
    df_1m.loc[df_1m.index[-1], 'close'] = prev2_low - 0.5
    
    res_short = strategy.analyze("BTCUSDT", df_1m, df_15m)
    if res_short and res_short['signal'] == "SHORT":
        print("[✅] ÉXITO: Detección de SMC SHORT Correcta.")
    else:
        print("[❌] FALLO: No se detectó el SMC SHORT forzado.")

    print("\n" + "="*50)

if __name__ == "__main__":
    test_v5_logic()
