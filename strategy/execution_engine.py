from strategy.indicators import Indicators
from strategy.trend_analyzer import TrendAnalyzer
from dashboard.app import send_log
import pandas as pd

class ExecutionEngine:
    def __init__(self, client, risk_manager, memory_manager, config):
        self.client = client
        self.risk_manager = risk_manager
        self.memory_manager = memory_manager
        self.config = config
        self.trend_analyzer = TrendAnalyzer(client, config)

    def check_signal(self, symbol):
        """
        Verifica señales de entrada en 5m respetando la tendencia diaria.
        """
        # 1. Obtener tendencia diaria
        trend_diaria = self.trend_analyzer.get_market_trend(symbol)
        btc_trend = self.trend_analyzer.analyze_btc_filter()
        
        if btc_trend == "BAJISTA" and trend_diaria != "BAJISTA":
            send_log(f"Operación en {symbol} bloqueada por filtro BTC Bajista (>3%)", "log-warning")
            return None
        
        if btc_trend == "ALCISTA" and trend_diaria != "ALCISTA":
            send_log(f"Operación en {symbol} bloqueada por filtro BTC Alcista (>3%)", "log-warning")
            return None

        # 2. Obtener datos de 5m
        klines_5m = self.client.get_kline(symbol=symbol, interval="5", limit=100)
        if not klines_5m:
            return None
            
        df = Indicators.klines_to_df(klines_5m)
        df = Indicators.add_indicators(df, self.config)
        
        if len(df) < 2:
            return None
            
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        # Verificar que los indicadores no sean NaN
        required_cols = ['ema_fast', 'ema_slow', 'rsi']
        if any(pd.isna(last_row[col]) for col in required_cols) or \
           any(pd.isna(prev_row[col]) for col in ['ema_fast', 'ema_slow']):
            return None

        # Lógica de cruce de EMAs
        cruce_alcista = prev_row['ema_fast'] <= prev_row['ema_slow'] and last_row['ema_fast'] > last_row['ema_slow']
        cruce_bajista = prev_row['ema_fast'] >= prev_row['ema_slow'] and last_row['ema_fast'] < last_row['ema_slow']
        
        if trend_diaria == "ALCISTA" and cruce_alcista and last_row['rsi'] > 50:
            return "Buy"
        elif trend_diaria == "BAJISTA" and cruce_bajista and last_row['rsi'] < 50:
            return "Sell"
            
        return None

    def execute_trade(self, symbol):
        # 1. Verificar límites operativos
        posiciones = self.client.get_active_positions()
        if len(posiciones) >= self.config['trading']['max_operaciones_simultaneas']:
            send_log(f"Límite de {len(posiciones)} operaciones alcanzado. Esperando...", "log-warning")
            return
            
        # Verificar si ya estamos operando este par
        if any(p['symbol'] == symbol for p in posiciones):
            return

        signal = self.check_signal(symbol)
        if not signal:
            return
            
        send_log(f"¡Señal detectada en {symbol}: {signal}!", "log-success")
        
        # 2. Calcular tamaño y SL/TP
        balance = self.client.get_balance()
        
        # Lógica de Exploración (IA)
        score = self.memory_manager.get_coin_score(symbol)
        es_exploracion = score < self.config['ia']['umbral_aprendizaje']
        
        monto = self.risk_manager.calculate_position_size(balance)
        if es_exploracion:
            monto = monto * 0.5 # Menor tamaño para aprender
            send_log(f"Operación de EXPLORACIÓN en {symbol}", "log-info")

        # Obtener datos para SL/TP y Qty
        klines = self.client.get_kline(symbol=symbol, interval="5", limit=20)
        if not klines: return
        df = Indicators.klines_to_df(klines)
        df = Indicators.add_indicators(df, self.config)
        
        entry_price = float(df.iloc[-1]['close'])
        atr = float(df.iloc[-1]['atr'])
        
        if entry_price <= 0: return

        # Calcular qty basado en monto USDT
        qty = round(monto / entry_price, 5) 
        if qty <= 0:
            send_log(f"Cantidad calculada demasiado pequeña para {symbol}", "log-warning")
            return
        
        sl, tp = self.risk_manager.calculate_sl_tp(signal, entry_price, atr)
        
        # 3. Colocar orden
        response = self.client.place_order(symbol, signal, "Market", qty, sl=sl, tp=tp)
        if response and response['retCode'] == 0:
            send_log(f"Orden ejecutada en {symbol}: {signal} a {entry_price}", "log-success")
            return response
        else:
            send_log(f"Error al ejecutar orden en {symbol}: {response['retMsg'] if response else 'Error desconocido'}", "log-error")
            return None
