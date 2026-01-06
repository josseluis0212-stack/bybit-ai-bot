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
    def calculate_adx(df, length=14):
        try:
            adx = ta.adx(df['high'], df['low'], df['close'], length=length)
            if adx is not None and not adx.empty:
                return adx[f'ADX_{length}']
        except:
            pass
        return pd.Series([0]*len(df))
    @staticmethod
    def add_indicators(df, config):
        df['ema_fast'] = Indicators.calculate_ema(df, config['estrategia']['ema_rapida'])
        df['ema_slow'] = Indicators.calculate_ema(df, config['estrategia']['ema_lenta'])
        df['ema_trend'] = Indicators.calculate_ema(df, config['estrategia']['ema_tendencia'])
        df['rsi'] = Indicators.calculate_rsi(df, config['estrategia']['rsi_periodo'])
        df['atr'] = Indicators.calculate_atr(df)
        df['adx'] = Indicators.calculate_adx(df, config['estrategia']['adx_periodo'])
        return df
    @staticmethod
    def klines_to_df(klines):
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df.sort_values('timestamp').reset_index(drop=True)
