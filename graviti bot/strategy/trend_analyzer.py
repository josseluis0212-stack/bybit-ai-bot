from strategy.indicators import Indicators
import pandas as pd

class TrendAnalyzer:
    def __init__(self, client, config):
        self.client = client
        self.config = config

    def get_market_trend(self, symbol):
        """
        Analiza la tendencia diaria (1D) de un activo.
        Retorna: 'ALCISTA', 'BAJISTA' o 'LATERAL'
        """
        klines = self.client.get_kline(symbol=symbol, interval="D", limit=100)
        if not klines:
            return "DESCONOCIDO"
            
        df = Indicators.klines_to_df(klines)
        df = Indicators.add_indicators(df, self.config)
        
        last_row = df.iloc[-1]
        ema_fast = last_row.get('ema_fast')
        ema_slow = last_row.get('ema_slow')
        rsi = last_row.get('rsi')
        close = last_row.get('close')
        
        # Verificar que no sean NaN o None
        if any(pd.isna(x) for x in [ema_fast, ema_slow, rsi, close]):
            return "LATERAL"
            
        # Lógica de tendencia basada en EMAs y RSI
        if close > ema_fast > ema_slow and rsi > 50:
            return "ALCISTA"
        elif close < ema_fast < ema_slow and rsi < 50:
            return "BAJISTA"
        else:
            return "LATERAL"

    def analyze_btc_15m_filter(self):
        """
        Analiza si BTC ha movido > 3% en los últimos 15 minutos.
        Define la tendencia de referencia.
        """
        klines = self.client.get_kline(symbol="BTCUSDT", interval="15", limit=2)
        if not klines:
            return "NEUTRAL", 0
            
        # kline: [start, open, high, low, close, ...]
        open_p = float(klines[0][1])
        close_p = float(klines[0][4])
        
        cambio_pct = ((close_p - open_p) / open_p) * 100
        
        if abs(cambio_pct) >= 3.0:
            trend = "ALCISTA" if cambio_pct > 0 else "BAJISTA"
            send_log(f"⚡ MOVIMIENTO BRUSCO BTC: {cambio_pct:.2f}% (Tendencia: {trend})", "log-warning")
            return trend, abs(cambio_pct)
            
        return "NEUTRAL", abs(cambio_pct)

    def analyze_btc_filter(self):
        """
        Analiza BTC como filtro global.
        Solo bloquea si hay movimiento brusco (>3% en 15m).
        """
        trend_15m, pct = self.analyze_btc_15m_filter()
        
        # Retornamos la tendencia de 15m (será NEUTRAL si < 3%)
        return trend_15m
