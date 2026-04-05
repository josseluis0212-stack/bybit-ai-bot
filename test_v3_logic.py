import pandas as pd
import numpy as np
from strategy.base_strategy import strategy
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

def generate_mock_data(size=100):
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(size))
    high = close + np.random.rand(size)
    low = close - np.random.rand(size)
    open_p = close + np.random.randn(size) * 0.5
    volume = np.random.randint(100, 1000, size)
    
    df = pd.DataFrame({
        'open': open_p,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    return df

def test_strategy():
    print("Testing Hyper-Quant V3 Strategy Logic...")
    df = generate_mock_data(500)
    
    # Test Normal Analysis - This will calculate indicators in the DF
    signal = strategy.analyze("BTCUSDT", df)
    print(f"Initial Analysis (Signal): {signal}")
    
    # After first analysis, columns like 'bb_low' and 'mfi' should exist
    if 'bb_low' in df.columns and 'mfi' in df.columns:
        print("Columns created successfully. Forcing a LONG signal...")
        # Force a LONG: price below BB_low and MFI below 20
        df.loc[df.index[-1], 'close'] = df.iloc[-1]['bb_low'] - 0.5
        df.loc[df.index[-1], 'mfi'] = 15
        df.loc[df.index[-2], 'close'] = df.iloc[-2]['bb_low'] - 1 # Ensure prev was below too
        
        signal_forced = strategy.analyze("BTCUSDT", df)
        print(f"Forced LONG Result: {signal_forced}")
    else:
        print(f"Error: Indicators not found in DF. Columns: {df.columns.tolist()}")
    
    print("Strategy test completed.")

if __name__ == "__main__":
    test_strategy()
