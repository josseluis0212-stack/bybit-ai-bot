import pandas as pd
import numpy as np
from strategy.base_strategy import strategy

def test_v91_logic():
    print("Testing V9.1 Strategy Logic...")
    
    # Create dummy data (1m timeframe)
    data = {
        'open': np.linspace(100, 105, 100),
        'high': np.linspace(101, 106, 100),
        'low': np.linspace(99, 104, 100),
        'close': np.linspace(100.5, 105.5, 100),
        'volume': [1000] * 100
    }
    df = pd.DataFrame(data)
    
    # Create HTF data (15m timeframe)
    htf_data = {
        'open': np.linspace(90, 100, 200),
        'high': np.linspace(91, 101, 200),
        'low': np.linspace(89, 99, 200),
        'close': np.linspace(90.5, 100.5, 200),
        'volume': [5000] * 200
    }
    df_htf = pd.DataFrame(htf_data)
    
    # Test analysis
    result = strategy.analyze("BTCUSDT", df, df_htf)
    print(f"Result for Long Bias: {result}")
    
    # Test Short Bias
    htf_data_short = {
        'open': np.linspace(110, 100, 200),
        'high': np.linspace(111, 101, 200),
        'low': np.linspace(109, 99, 200),
        'close': np.linspace(110.5, 100.5, 200),
        'volume': [5000] * 200
    }
    df_htf_short = pd.DataFrame(htf_data_short)
    result_short = strategy.analyze("BTCUSDT", df, df_htf_short)
    print(f"Result for Short Bias: {result_short}")

if __name__ == "__main__":
    try:
        test_v91_logic()
        print("Test completed successfully.")
    except Exception as e:
        print(f"Test failed: {e}")
