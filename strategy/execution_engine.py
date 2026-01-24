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
        ESTRATEGIA ÚLTIMA GENERACIÓN (Triple Alineación + Volumen)
        1. Tendencia Macro (Diario): Precio > EMA 50
        2. Tendencia Táctica (1H): Precio > EMA 50
        3. Clasificación (15m): Precio > EMA 50
        4. Gatillo (15m): Cruce EMA 8/21 + Confirmación Volumen
        """
        # --- 1. Obtener Datos Multi-Temporalidad ---
        # Diario (D)
        klines_d = self.client.get_kline(symbol=symbol, interval="D", limit=55)
        if not klines_d: return None
        df_d = Indicators.klines_to_df(klines_d)
        df_d = Indicators.add_indicators(df_d, self.config)
        
        # 1 Hora (60)
        klines_1h = self.client.get_kline(symbol=symbol, interval="60", limit=55)
        if not klines_1h: return None
        df_1h = Indicators.klines_to_df(klines_1h)
        df_1h = Indicators.add_indicators(df_1h, self.config)
        
        # 15 Minutos (15)
        klines_15m = self.client.get_kline(symbol=symbol, interval="15", limit=55)
        if not klines_15m: return None
        df_15m = Indicators.klines_to_df(klines_15m)
        df_15m = Indicators.add_indicators(df_15m, self.config)
        
        if len(df_d) < 50 or len(df_1h) < 50 or len(df_15m) < 50: return None

        # --- 2. Análisis de Alineación (EMA 50) ---
        last_d = df_d.iloc[-1]
        last_1h = df_1h.iloc[-1]
        last_15m = df_15m.iloc[-1]
        prev_15m = df_15m.iloc[-2]
        
        trend_d = "ALCISTA" if last_d['close'] > last_d['ema_mid'] else "BAJISTA"
        trend_1h = "ALCISTA" if last_1h['close'] > last_1h['ema_mid'] else "BAJISTA"
        trend_15m = "ALCISTA" if last_15m['close'] > last_15m['ema_mid'] else "BAJISTA"
        
        # Filtro de Alineación Estricta
        if not (trend_d == trend_1h == trend_15m):
            return None
            
        tendencia_general = trend_d # "ALCISTA" o "BAJISTA"

        # --- 3. Gatillo de Entrada (15m) ---
        # Cruce de EMAs Configurable (Default 8 y 21)
        cruce_buy = prev_15m['ema_fast'] <= prev_15m['ema_slow'] and last_15m['ema_fast'] > last_15m['ema_slow']
        cruce_sell = prev_15m['ema_fast'] >= prev_15m['ema_slow'] and last_15m['ema_fast'] < last_15m['ema_slow']
        
        # Confirmación de Volumen (Volumen actual > Media de 20 periodos)
        vol_ok = last_15m['volume'] > last_15m['vol_ma']
        
        # --- 4. Decisión Final ---
        if tendencia_general == "ALCISTA" and cruce_buy and vol_ok:
            send_log(f"💎 SEÑAL CONFIRMADA (3 TF + Vol): {symbol} LONG", "log-success")
            return "Buy"
            
        if tendencia_general == "BAJISTA" and cruce_sell and vol_ok:
            send_log(f"💎 SEÑAL CONFIRMADA (3 TF + Vol): {symbol} SHORT", "log-success")
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
        klines = self.client.get_kline(symbol=symbol, interval="15", limit=20)
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
