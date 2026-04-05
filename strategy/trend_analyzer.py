from strategy.indicators import Indicators
import pandas as pd

class TrendAnalyzer:
    def __init__(self, client, config):
        self.client = client
        self.config = config

    def analyze_macro_trend(self, symbol):
        """
        Analiza la tendencia macro.
        Según config: timeframe 4H (240m), Supertrend + EMA200.
        Retorna: 'ALCISTA', 'BAJISTA' o 'LATERAL'
        """
        filtro = self.config.get('filtro_macro', {})
        tf = str(filtro.get('timeframe', '240'))
        velas_necesarias = int(filtro.get('velas', 250))
        
        klines = self.client.get_kline(symbol=symbol, interval=tf, limit=velas_necesarias)
        if not klines: return "LATERAL"
        
        df = Indicators.klines_to_df(klines)
        
        # Calcular EMA200 y Supertrend
        ema_largo = int(filtro.get('ema_largo', 200))
        st_len = int(filtro.get('supertrend_periodo', 10))
        st_mult = float(filtro.get('supertrend_multiplicador', 3.0))
        
        df['ema_trend'] = Indicators.calculate_ema(df, ema_largo)
        df = Indicators.calculate_supertrend(df, length=st_len, multiplier=st_mult)
        
        last_row = df.iloc[-1]
        close = last_row.get('close')
        ema_200 = last_row.get('ema_trend')
        st_dir = last_row.get('supertrend_dir') # 1 = Bull, -1 = Bear
        
        if pd.isna(close) or pd.isna(ema_200) or pd.isna(st_dir): return "LATERAL"
        
        if close > ema_200 and st_dir == 1:
            return "ALCISTA"
        elif close < ema_200 and st_dir == -1:
            return "BAJISTA"
            
        return "LATERAL"

    def analyze_btc_filter(self):
        """
        Filtro de Bitcoin global de 4H.
        Retorna 'ALCISTA', 'BAJISTA' o 'LATERAL'
        """
        btc_config = self.config.get('filtro_btc', {})
        if not btc_config.get('activado', True): return "LATERAL"
        
        symbol = btc_config.get('simbolo', 'BTCUSDT')
        return self.analyze_macro_trend(symbol)
