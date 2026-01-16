import pandas as pd
import pandas_ta as ta

class Indicators:
    @staticmethod
    def calculate_ema(df, length):
        return ta.ema(df['close'], length=length)

    @staticmethod
    def calculate_rsi(df, length=14):
        return ta.rsi(df['close'], length=length)

    @staticmethod
    def calculate_atr(df, length=14):
        return ta.atr(df['high'], df['low'], df['close'], length=length)

    @staticmethod
    def add_indicators(df, config):
        df['ema_fast'] = Indicators.calculate_ema(df, config['estrategia']['ema_rapida'])
        df['ema_slow'] = Indicators.calculate_ema(df, config['estrategia']['ema_lenta'])
        df['rsi'] = Indicators.calculate_rsi(df, config['estrategia']['rsi_periodo'])
        df['atr'] = Indicators.calculate_atr(df)
        return df

    @staticmethod
    def klines_to_df(klines):
        # Bybit klines: [start_time, open, high, low, close, volume, turnover]
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        # Bybit returns klines in descending order (newest first), we need ascending for TA
        return df.sort_values('timestamp').reset_index(drop=True)
