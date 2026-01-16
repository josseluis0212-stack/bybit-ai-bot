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
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=length)
        if adx_df is not None and not adx_df.empty:
            return adx_df[f'ADX_{length}']
        return pd.Series([0] * len(df))
    @staticmethod
    def calculate_volume_sma(df, length=20):
        return ta.sma(df['volume'], length=length)
    @staticmethod
    def calculate_bbands(df, length=20, std=2):
        return ta.bbands(df['close'], length=length, std=std)
    @staticmethod
    def add_indicators(df, config):
        strat = config['estrategia']
        df['ema_fast'] = Indicators.calculate_ema(df, strat['ema_rapida'])
        df['ema_slow'] = Indicators.calculate_ema(df, strat['ema_lenta'])
        df['ema_trend'] = Indicators.calculate_ema(df, strat.get('ema_tendencia', 200))
        df['rsi'] = Indicators.calculate_rsi(df, strat['rsi_periodo'])
        df['atr'] = Indicators.calculate_atr(df)
        df['adx'] = Indicators.calculate_adx(df, strat.get('adx_periodo', 14))
        df['vol_ma'] = Indicators.calculate_volume_sma(df, strat.get('volumen_ma', 20))
        
        # Bandas Bollinger (Para Grid)
        bb = Indicators.calculate_bbands(df)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)
            cols = list(bb.columns)
            if len(cols) >= 3:
                df['bb_lower'] = bb[cols[0]]
                df['bb_mid'] = bb[cols[1]]
                df['bb_upper'] = bb[cols[2]]
        return df
    @staticmethod
    def klines_to_df(klines):
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df.sort_values('timestamp').reset_index(drop=True)
