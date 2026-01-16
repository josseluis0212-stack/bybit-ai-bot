from strategy.indicators import Indicators
from strategy.trend_analyzer import TrendAnalyzer
from dashboard.app import send_log
import pandas as pd

class GridAnalyzer:
    def __init__(self, client, config, telegram=None):
        self.client = client
        self.config = config
        self.telegram = telegram
        self.trend_analyzer = TrendAnalyzer(client, config)

    def analyze_grid(self, symbol):
        """
        Estrategia de Grid de TENDENCIA (No Rangos).
        Usa EMA 8, 21, 200 + RSI + Volumen + ATR.
        """
        # 0. Filtro BTC Brusco
        btc_trend, es_brusco = self.trend_analyzer.analyze_btc_filter()
        if es_brusco:
            send_log(f"⚠️ Grid skip {symbol}: BTC brusco", "log-warning")
            return

        # 1. Análisis Macro (Tendencia 1D)
        klines_1d = self.client.get_kline(symbol=symbol, interval="D", limit=500)
        if not klines_1d: return
        df_1d = Indicators.klines_to_df(klines_1d)
        df_1d = Indicators.add_indicators(df_1d, self.config)
        
        last_1d = df_1d.iloc[-1]
        
        # Filtro de Tendencia (Relajado para capturar tendencias emergentes)
        trend_baseline = last_1d['ema_200'] if not pd.isna(last_1d['ema_200']) else last_1d['ema_mid']
        
        if pd.isna(trend_baseline): 
            trend_baseline = last_1d['ema_slow']

        # SAFETY CHECK: Ensure we have valid data for comparison to avoid TypeError
        if pd.isna(trend_baseline) or pd.isna(last_1d['ema_fast']) or pd.isna(last_1d['ema_slow']):
            send_log(f"ℹ️ Grid skip {symbol}: Datos insuficientes (EMAs)", "log-info")
            return

        is_long_1d = (last_1d['close'] > trend_baseline) and (last_1d['ema_fast'] > last_1d['ema_slow'])
        is_short_1d = (last_1d['close'] < trend_baseline) and (last_1d['ema_fast'] < last_1d['ema_slow'])
        
        if not is_long_1d and not is_short_1d:
            # Opción: Reducir logs de "No alineación" si son demasiados, o dejarlos si el usuario pide detalle
            # send_log(f"🔍 [GRID SKIP] {symbol}: No hay alineación 1D", "log-info")
            return
            
        direction = "COMPRA (Long Grid)" if is_long_1d else "VENTA (Short Grid)"

        # 2. Análisis de Correlación (1H)
        klines_1h = self.client.get_kline(symbol=symbol, interval="60", limit=500)
        if not klines_1h: return
        df_1h = Indicators.klines_to_df(klines_1h)
        df_1h = Indicators.add_indicators(df_1h, self.config)
        last_1h = df_1h.iloc[-1]
        
        # Debe estar a favor de la tendencia principal en 1H
        trend_baseline_1h = last_1h['ema_200'] if not pd.isna(last_1h['ema_200']) else last_1h['ema_mid']
        if is_long_1d and last_1h['close'] < trend_baseline_1h: 
            send_log(f"🔍 [GRID SKIP] {symbol}: 1H Bajista vs 1D Alcista", "log-error")
            return
        if is_short_1d and last_1h['close'] > trend_baseline_1h: 
            send_log(f"🔍 [GRID SKIP] {symbol}: 1H Alcista vs 1D Bajista", "log-error")
            return

        # 3. Gatillo y Filtros Pro (15m)
        klines_15m = self.client.get_kline(symbol=symbol, interval="15", limit=100)
        if not klines_15m: return
        df_15m = Indicators.klines_to_df(klines_15m)
        df_15m = Indicators.add_indicators(df_15m, self.config)
        last_15m = df_15m.iloc[-1]
        
        # Filtro RSI Momentum (Relajado a 40 para Long y 60 para Short)
        # Se suaviza un poco para encontrar mas entradas
        if is_long_1d and last_15m['rsi'] < 40: 
            return 
        if is_short_1d and last_15m['rsi'] > 60: 
            return 

        # Filtro Volumen (Permisivo: > 50% del promedio) - RELAJADO
        avg_volume = df_15m['volume'].tail(20).mean()
        if last_15m['volume'] < (avg_volume * 0.5): 
            return

        # Filtro ATR (Evitar lateralización extrema)
        atr_pct = last_15m['atr'] / last_15m['close']
        if atr_pct < 0.002: # Relajado de 0.003
            return 

        # 4. Cálculo de Parámetros de Grid de Tendencia
        current_price = last_15m['close']
        atr = last_15m['atr']
        
        if is_long_1d:
            # En Long, el grid se pone para capturar pullbacks y continuación
            # Límite Inferior: EMA 200 de 1H o soporte ATR
            lower_bound = min(last_1h['ema_200'], current_price - (atr * 3))
            upper_bound = current_price + (atr * 5) # Proyección de tendencia
            stop_loss = lower_bound * 0.98 # 2% debajo del fondo
        else:
            # En Short, el grid se pone para capturar rebotes y continuación bajista
            upper_bound = max(last_1h['ema_200'], current_price + (atr * 3))
            lower_bound = current_price - (atr * 5)
            stop_loss = upper_bound * 1.02 # 2% arriba del techo

        # Espaciado de grids: ~1% de distancia
        price_range_pct = (upper_bound - lower_bound) / lower_bound * 100
        num_grids = int(max(10, min(80, price_range_pct / 0.7)))

        self.send_grid_alert(symbol, direction, lower_bound, upper_bound, num_grids, stop_loss, current_price)

    def send_grid_alert(self, symbol, direction, lower, upper, grids, sl, current):
        msg = (
            f"📈 *BOT GRID: NUEVA CONFIGURACIÓN*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *Moneda:* {symbol}\n"
            f"📊 *Tendencia Detectada:* {direction}\n"
            f"💵 *Precio Actual (Entrada):* {current:.4f}\n\n"
            f"📏 *RANGO SUGERIDO (Manual):*\n"
            f"🔼 *Superior:* {upper:.4f}\n"
            f"🔽 *Inferior:* {lower:.4f}\n\n"
            f"🔢 *Configuración:* {grids} grids | ⚙️ 5x\n"
            f"🛑 *Stop Loss:* {sl:.4f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Consejo:* Las EMAs 8/21/200 están alineadas. Entre a favor del flujo institucional."
        )
        
        if self.telegram:
            self.telegram.send_message(msg)
        send_log(f"Alerta Grid de Tendencia enviada: {symbol}", "log-success")
