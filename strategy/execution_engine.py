from strategy.indicators import Indicators
from strategy.trend_analyzer import TrendAnalyzer
from dashboard.app import send_log
import pandas as pd
class ExecutionEngine:
    def __init__(self, client, risk_manager, memory_manager, config, telegram_bot):
        self.client = client
        self.risk_manager = risk_manager
        self.memory_manager = memory_manager
        self.config = config
        self.telegram = telegram_bot
        self.trend_analyzer = TrendAnalyzer(client, config)
    def check_signal(self, symbol):
        # 1. Obtener datos de 5m
        klines_5m = self.client.get_kline(symbol=symbol, interval="5", limit=300)
        if not klines_5m: return None
            
        df = Indicators.klines_to_df(klines_5m)
        df = Indicators.add_indicators(df, self.config)
        
        if len(df) < 5: return None
            
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Validar datos
        req = ['ema_fast', 'ema_slow', 'ema_trend', 'rsi', 'atr', 'adx']
        if any(pd.isna(last[c]) for c in req): return None
        # --- FILTRO 1: Tendencia Mayor (EMA 200) ---
        tendencia_alcista = last['close'] > last['ema_trend']
        tendencia_bajista = last['close'] < last['ema_trend']
        # --- FILTRO 2: Fuerza de Tendencia (ADX) ---
        if last['adx'] < 20: 
            return None # Mercado lateral
        # --- FILTRO 3: Volatilidad (ATR) ---
        min_vol = last['close'] * 0.0005
        if last['atr'] < min_vol:
            return None # Mercado muerto
        # --- SEÑAL: Cruce EMA 18 y 21 ---
        cruce_up = prev['ema_fast'] <= prev['ema_slow'] and last['ema_fast'] > last['ema_slow']
        cruce_down = prev['ema_fast'] >= prev['ema_slow'] and last['ema_fast'] < last['ema_slow']
        
        # --- CONFIRMACIÓN RSI ---
        rsi_buy = last['rsi'] > 50
        rsi_sell = last['rsi'] < 50
        if tendencia_alcista and cruce_up and rsi_buy:
            return "Buy"
        elif tendencia_bajista and cruce_down and rsi_sell:
            return "Sell"
            
        return None
    def execute_trade(self, symbol):
        # 1. Verificar límites operativos
        posiciones = self.client.get_active_positions()
        if len(posiciones) >= self.config['trading']['max_operaciones_simultaneas']:
            return
            
        if any(p['symbol'] == symbol for p in posiciones):
            return
        # Verificar CAPITAL DISPONIBLE
        balance = self.client.get_balance()
        monto_requerido = self.config['trading']['monto_por_operacion']
        
        if balance < monto_requerido:
            send_log(f"Saldo insuficiente ({balance:.2f} USDT) para operar {symbol}", "log-warning")
            return
        signal = self.check_signal(symbol)
        if not signal:
            return
            
        send_log(f"¡Señal detectada en {symbol}: {signal}!", "log-success")
        self.telegram.send_message(f"🚀 *Señal Detectada*\n\n*Moneda:* {symbol}\n*Dirección:* {signal}\n*Estado:* Ejecutando orden...")
        
        # Obtener datos precio
        klines = self.client.get_kline(symbol=symbol, interval="5", limit=20)
        if not klines: return
        df = Indicators.klines_to_df(klines)
        df = Indicators.add_indicators(df, self.config)
        
        entry_price = float(df.iloc[-1]['close'])
        atr = float(df.iloc[-1]['atr'])
        
        if entry_price <= 0: return
        # Calcular Cantidad Exacta
        info = self.client.get_symbol_info(symbol)
        if info and 'lotSizeFilter' in info:
            qty_step = str(info['lotSizeFilter']['qtyStep'])
            min_qty = float(info['lotSizeFilter']['minOrderQty'])
        else:
            qty_step = "0.01"
            min_qty = 0.001
        if '.' in qty_step:
            precision = len(qty_step.split('.')[-1])
        else:
            precision = 0
            
        # Calcular cantidad con apalancamiento aplicado
        # Monto = Valor nocional / Precio. El margen usado será Monto/Apalancamiento
        # Si queremos arriesgar 15 USD de margen, la orden debe ser de 15 * 3 = 45 USD
        
        leverage = self.config['trading']['apalancamiento'] # 3x
        valor_orden = monto_requerido * leverage # 15 * 3 = 45 USD de tamaño de posición
        
        raw_qty = valor_orden / entry_price
        qty = round(raw_qty, precision) if precision > 0 else int(raw_qty)
        if qty < min_qty: 
            send_log(f"Cantidad muy pequeña para {symbol}", "log-warning")
            return
        
        # Forzar apalancamiento antes de operar
        self.client.set_leverage(symbol, leverage)
        sl, tp = self.risk_manager.calculate_sl_tp(signal, entry_price, atr)
        
        # 3. Colocar orden
        response = self.client.place_order(symbol, signal, "Market", qty, sl=sl, tp=tp)
        
        if response and response['retCode'] == 0:
            msg = f"✅ *Orden Ejecutada*\n\n*Moneda:* {symbol}\n*Signal:* {signal}\n*Precio:* {entry_price}\n*Margen:* {monto_requerido} USDT\n*Total:* {valor_orden:.2f} USDT ({leverage}x)\n*SL:* {sl} | *TP:* {tp}"
            send_log(f"Orden ejecutada en {symbol}", "log-success")
            self.telegram.send_message(msg)
        else:
            error_msg = response['retMsg'] if response else 'Error desconocido'
            send_log(f"Error {symbol}: {error_msg}", "log-error")
            self.telegram.send_message(f"❌ *Error Orden {symbol}*\n{error_msg}")
