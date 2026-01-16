from strategy.indicators import Indicators
from strategy.trend_analyzer import TrendAnalyzer
from dashboard.app import send_log
import pandas as pd

class ExecutionEngine:
    def __init__(self, client, risk_manager, memory_manager, config, telegram=None):
        self.client = client
        self.risk_manager = risk_manager
        self.memory_manager = memory_manager
        self.config = config
        self.telegram = telegram
        self.trend_analyzer = TrendAnalyzer(client, config)

    def check_signal(self, symbol):
        """
        Verifica señales de entrada en 5m respetando la tendencia diaria.
        """
        # 1. Obtener tendencia diaria y filtro BTC
        trend_diaria = self.trend_analyzer.get_market_trend(symbol)
        btc_trend, es_brusco_btc = self.trend_analyzer.analyze_btc_filter()
        
        # Filtrado por correlación con movimiento brusco de BTC
        if es_brusco_btc:
            if btc_trend == "ALCISTA" and trend_diaria != "ALCISTA":
                return None # Bloquear si no correlaciona con subida brusca
            if btc_trend == "BAJISTA" and trend_diaria != "BAJISTA":
                return None # Bloquear si no correlaciona con bajada brusca
        
        if btc_trend == "BAJISTA" and trend_diaria != "BAJISTA":
            return None
        
        if btc_trend == "ALCISTA" and trend_diaria != "ALCISTA":
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

        # Lógica de cruce de EMAs (window of 3 candles to catch recent moves)
        # Check if crossover happened in the last 3 periods
        cruce_alcista = False
        cruce_bajista = False
        
        subset = df.tail(4) # Need 4 to check 3 transitions
        for i in range(len(subset) - 1):
            prev = subset.iloc[i]
            curr = subset.iloc[i+1]
            if prev['ema_fast'] <= prev['ema_slow'] and curr['ema_fast'] > curr['ema_slow']:
                cruce_alcista = True
            if prev['ema_fast'] >= prev['ema_slow'] and curr['ema_fast'] < curr['ema_slow']:
                cruce_bajista = True
        
        if trend_diaria == "ALCISTA" and cruce_alcista and last_row['rsi'] > 50:
            send_log(f"✅ SEÑAL COMPRA en {symbol} (Trend: {trend_diaria}, RSI: {last_row['rsi']:.1f})", "log-success")
            return "Buy"
        elif trend_diaria == "BAJISTA" and cruce_bajista and last_row['rsi'] < 50:
            send_log(f"✅ SEÑAL VENTA en {symbol} (Trend: {trend_diaria}, RSI: {last_row['rsi']:.1f})", "log-success")
            return "Sell"
            
        return None

    def emergency_close_contrary_positions(self, btc_trend):
        """
        Cierra posiciones que van en contra del movimiento fuerte de BTC.
        """
        posiciones = self.client.get_active_positions()
        for p in posiciones:
            symbol = p['symbol']
            side = p['side'] # 'Buy' o 'Sell'
            
            # Si BTC sube fuerte (ALCISTA), se cierran los Shorts (Sell)
            if btc_trend == "ALCISTA" and side == "Sell":
                send_log(f"🚨 CIERRE DE EMERGENCIA (BTC Spike UP): Cerramos SHORT en {symbol}", "log-error")
                self.client.place_order(symbol, "Buy", "Market", p['size'])
            
            # Si BTC baja fuerte (BAJISTA), se cierran los Longs (Buy)
            elif btc_trend == "BAJISTA" and side == "Buy":
                send_log(f"🚨 CIERRE DE EMERGENCIA (BTC Spike DOWN): Cerramos LONG en {symbol}", "log-error")
                self.client.place_order(symbol, "Sell", "Market", p['size'])

    def execute_trade(self, symbol):
        # 0. Verificar Filtro BTC Brusco antes de nada
        btc_trend, es_brusco = self.trend_analyzer.analyze_btc_filter()
        if es_brusco:
            self.emergency_close_contrary_positions(btc_trend)

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
        if self.telegram:
            self.telegram.send_message(f"🎯 *Señal Detectada*\n{symbol}: {signal}")
        
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
        qty_adj = self.client.adjust_qty(symbol, qty)
        response = self.client.place_order(symbol, signal, "Market", qty, sl=sl, tp=tp)
        
        if response and response['retCode'] == 0:
            send_log(f"Orden ejecutada en {symbol}: {signal} a {entry_price}", "log-success")
            if self.telegram:
                leverage = self.client.leverage_cache.get(symbol, 3)
                self.telegram.send_message(
                    f"🤖 *BOT IA: SEÑAL DETECTADA*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 *Moneda:* {symbol}\n"
                    f"↕️ *Dirección:* {'COMPRA (Long)' if signal == 'Buy' else 'VENTA (Short)'}\n"
                    f"💰 *Monto:* {monto:.2f} USDT\n"
                    f"⚙️ *Apalancamiento:* {leverage}x\n"
                    f"💵 *Precio Entrada:* {entry_price:.4f}\n"
                    f"🛡️ *SL:* {sl:.4f} | 🎯 *TP:* {tp:.4f}\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
            return response
        else:
            error_msg = response['retMsg'] if response and 'retMsg' in response else "Error de conexión o respuesta vacía"
            send_log(f"Error al ejecutar orden en {symbol}: {error_msg}", "log-error")
            if self.telegram:
                self.telegram.send_message(f"❌ *Error en Orden*\n{symbol}: {error_msg}")
            return None
