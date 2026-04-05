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
    def calculate_sma(df, length):
        return ta.sma(df['close'], length=length)

    @staticmethod
    def calculate_volume_sma(df, length=20):
        return ta.sma(df['volume'], length=length)

    @staticmethod
    def calculate_bbands(df, length=20, std=2):
        # Retorna un DataFrame con columnas: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
        return ta.bbands(df['close'], length=length, std=std)

    @staticmethod
    def calculate_supertrend(df, length=10, multiplier=3.0):
        st = ta.supertrend(df['high'], df['low'], df['close'], length=length, multiplier=multiplier)
        if st is not None and not st.empty:
            cols = list(st.columns)
            # Retorna DataFrame original con trend_dir (1 o -1) y supertrend_value añadidos
            df['supertrend_dir'] = st[cols[1]]
            df['supertrend_val'] = st[cols[0]]
        else:
            df['supertrend_dir'] = 0
            df['supertrend_val'] = 0
        return df

    @staticmethod
    def calculate_macd(df, fast=12, slow=26, signal=9):
        macd = ta.macd(df['close'], fast=fast, slow=slow, signal=signal)
        if macd is not None and not macd.empty:
            cols = list(macd.columns)
            df['macd'] = macd[cols[0]]
            df['macd_hist'] = macd[cols[1]]
            df['macd_signal'] = macd[cols[2]]
        else:
            df['macd'] = 0
            df['macd_hist'] = 0
            df['macd_signal'] = 0
        return df

    @staticmethod
    def calculate_vwap(df):
        df_vp = df.copy()
        if 'timestamp' in df_vp.columns:
            df_vp.set_index('timestamp', inplace=True)
        vwap = ta.vwap(high=df_vp['high'], low=df_vp['low'], close=df_vp['close'], volume=df_vp['volume'], anchor='D')
        if vwap is not None and not vwap.empty:
            if isinstance(vwap, pd.Series):
                df['vwap'] = vwap.values
            else:
                cols = list(vwap.columns)
                df['vwap'] = vwap[cols[0]].values
        else:
            df['vwap'] = df['close']
        return df

    @staticmethod
    def add_indicators(df, config=None):
        if config is None:
            return df


        if 'estrategia' in config:
            strat = config['estrategia']
            df['ema_fast'] = Indicators.calculate_ema(df, strat.get('ema_rapida', 20))
            df['ema_slow'] = Indicators.calculate_ema(df, strat.get('ema_lenta', 50))
            df['ema_trend'] = Indicators.calculate_ema(df, strat.get('ema_tendencia', 200))
            df['rsi'] = Indicators.calculate_rsi(df, strat.get('rsi_periodo', 14))
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
