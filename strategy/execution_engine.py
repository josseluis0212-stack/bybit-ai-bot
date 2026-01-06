from strategy.indicators import Indicators
from strategy.trend_analyzer import TrendAnalyzer
from dashboard.app import send_log
import pandas as pd
import time
class ExecutionEngine:
    def __init__(self, client, risk_manager, memory_manager, config, telegram_bot):
        self.client = client
        self.risk_manager = risk_manager
        self.memory_manager = memory_manager
        self.config = config
        self.telegram = telegram_bot
        self.trend_analyzer = TrendAnalyzer(client, config)
        self.last_grid_alert = {} # Control de spam (4 horas)
    def check_signal(self, symbol):
        # --- ESTRATEGIA PRINCIPAL (TRADING AUTOMÁTICO) ---
        # 1. FILTRO MACRO (DIARIO - 1D)
        klines_d = self.client.get_kline(symbol=symbol, interval="D", limit=100)
        if not klines_d: return None
        df_d = Indicators.klines_to_df(klines_d)
        df_d = Indicators.add_indicators(df_d, self.config)
        last_d = df_d.iloc[-1]
        
        ema200_d = last_d.get('ema_trend', 0)
        tendencia_diaria_alcista = last_d['close'] > ema200_d and last_d['rsi'] > 50
        tendencia_diaria_bajista = last_d['close'] < ema200_d and last_d['rsi'] < 50
        
        # 2. FILTRO TACTICO (1 HORA - 1H)
        klines_1h = self.client.get_kline(symbol=symbol, interval="60", limit=50)
        if not klines_1h: return None
        df_1h = Indicators.klines_to_df(klines_1h)
        df_1h = Indicators.add_indicators(df_1h, self.config)
        last_1h = df_1h.iloc[-1]
        
        if last_1h['adx'] <= 25: return None 
        alineacion_1h_alcista = last_1h['close'] > last_1h['ema_slow']
        alineacion_1h_bajista = last_1h['close'] < last_1h['ema_slow']
        
        # 3. GATILLO MICRO (5 MIN - 5m)
        klines_5m = self.client.get_kline(symbol=symbol, interval="5", limit=100)
        if not klines_5m: return None
        df_5m = Indicators.klines_to_df(klines_5m)
        df_5m = Indicators.add_indicators(df_5m, self.config)
        
        last_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]
        
        cruce_buy = prev_5m['ema_fast'] <= prev_5m['ema_slow'] and last_5m['ema_fast'] > last_5m['ema_slow']
        cruce_sell = prev_5m['ema_fast'] >= prev_5m['ema_slow'] and last_5m['ema_fast'] < last_5m['ema_slow']
        vol_power = last_5m['volume'] > (last_5m['vol_ma'] * 1.2)
        
        if not vol_power: return None
        if cruce_buy and tendencia_diaria_alcista and alineacion_1h_alcista: return "Buy"
        if cruce_sell and tendencia_diaria_bajista and alineacion_1h_bajista: return "Sell"
        return None
    def check_grid_signal(self, symbol):
        """
        ESTRATEGIA BOT GRID (Solo Alertas Profesionales)
        Analiza: Diario (Tendencia), 30m (Estructura), 15m (Gatillo).
        """
        # 1. FILTRO BTC (Seguridad)
        try:
            btc_trend = self.trend_analyzer.analyze_btc_filter()
        except: btc_trend = "NEUTRAL"
        
        # 2. ANÁLISIS DIARIO (D) - Determina el SESGO
        klines_d = self.client.get_kline(symbol=symbol, interval="D", limit=50)
        if not klines_d: return
        df_d = Indicators.klines_to_df(klines_d)
        df_d = Indicators.add_indicators(df_d, self.config)
        last_d = df_d.iloc[-1]
        
        ema200 = last_d.get('ema_trend', 0)
        tendencia_diaria = "ALCISTA" if last_d['close'] > ema200 else "BAJISTA"
        adx_diario = last_d.get('adx', 0)
        
        # 3. ANÁLISIS 30 MINUTOS (30m) - Estructura
        try:
            klines_30m = self.client.get_kline(symbol=symbol, interval="30", limit=50)
            if not klines_30m: return
        except: return 
        
        # 4. GATILLO 15 MINUTOS (15m) - Entrada Fina
        klines_15m = self.client.get_kline(symbol=symbol, interval="15", limit=50)
        if not klines_15m: return
        df_15m = Indicators.klines_to_df(klines_15m)
        df_15m = Indicators.add_indicators(df_15m, self.config)
        last_15m = df_15m.iloc[-1]
        
        # Necesitamos Bandas Bollinger
        if 'bb_lower' not in last_15m: return
        signal_grid = None
        motivo = ""
        
        # A) GRID LONG
        if last_15m['low'] <= last_15m['bb_lower'] and last_15m['rsi'] < 35:
            if tendencia_diaria == "ALCISTA":
                signal_grid = "LONG (A favor de tendencia)"
            else:
                signal_grid = "LONG (Contra-tendencia / Rebote)"
        # B) GRID SHORT
        elif last_15m['high'] >= last_15m['bb_upper'] and last_15m['rsi'] > 65:
            if tendencia_diaria == "BAJISTA":
                signal_grid = "SHORT (A favor de tendencia)"
            else:
                signal_grid = "SHORT (Contra-tendencia / Retroceso)"
        if not signal_grid: return
        # --- FILTRO DE TIEMPO (Anti-Spam 4 Horas) ---
        last_time = self.last_grid_alert.get(symbol, 0)
        if time.time() - last_time < (4 * 3600): # 4 Horas
            return
        # Actualizar timestamp
        self.last_grid_alert[symbol] = time.time()
        
        entry_price = last_15m['close']
        atr = last_15m['atr']
        
        # --- CÁLCULOS MATEMÁTICOS PARA GRID ---
        grid_low = last_15m['bb_lower']
        grid_high = last_15m['bb_upper']
        
        # Calcular número de grillas sugerido (Basado en ATR)
        rango_precio = grid_high - grid_low
        espacio_minimo = atr * 0.5
        num_grillas = int(rango_precio / espacio_minimo)
        num_grillas = max(5, min(15, num_grillas)) # Mantener entre 5 y 15
        
        sl_suggested = entry_price - (atr * 3) if "LONG" in signal_grid else entry_price + (atr * 3)
        tp_suggested = grid_high if "LONG" in signal_grid else grid_low
        
        send_log(f"Alerta Grid Pro enviada: {symbol}", "log-info")
        
        self.telegram.send_message(
            f"🤖 *BOT GRID DETECTADO* 🤖\n\n"
            f"⚠️ *Oportunidad de Entrada*\n"
            f"💎 *Moneda:* {symbol}\n"
            f"🚀 *Dirección:* {signal_grid}\n\n"
            f"📏 *RANGO DEL GRID:*\n"
            f"• Precio Bajo (Low): {grid_low:.4f}\n"
            f"• Precio Alto (High): {grid_high:.4f}\n"
            f"• Grillas Sugeridas: {num_grillas}\n\n"
            f"🛡️ *GESTIÓN DE RIESGO:*\n"
            f"• Stop Loss: {sl_suggested:.4f}\n"
            f"• Take Profit: {tp_suggested:.4f}\n"
            f"• Apalancamiento: 5x (Fijo)\n\n"
            f"🧠 *CONSEJO PROFESIONAL:*\n"
            f"\"El mercado está en zona extrema. Configura el Grid Neutral si esperas lateralidad, o Geométrico si esperas tendencia.\""
        )
    def execute_trade(self, symbol):
        # 1. Ejecutar Radar Grid (Alerta)
        try: self.check_grid_signal(symbol)
        except Exception as e: print(f"Error Grid: {e}")
        # 2. Ejecutar Trading Principal
        posiciones = self.client.get_active_positions()
        if len(posiciones) >= self.config['trading']['max_operaciones_simultaneas']: return 
        if any(p['symbol'] == symbol for p in posiciones): return
        signal = self.check_signal(symbol)
        if not signal: return
            
        send_log(f"¡Señal TRIPLE ALINEACIÓN en {symbol}: {signal}!", "log-success")
        self.telegram.send_message(f"🏛️ *SEÑAL TRADING AUTO*\n💎 {symbol}\n🚀 {signal}\n✅ Patrón Confirmado")
        
        balance = self.client.get_balance()
        monto = self.config['trading']['monto_por_operacion']
        if self.memory_manager.get_coin_score(symbol) < self.config['ia']['umbral_aprendizaje']: monto *= 0.5 
        klines = self.client.get_kline(symbol=symbol, interval="5", limit=20)
        df_calc = Indicators.klines_to_df(klines)
        df_calc = Indicators.add_indicators(df_calc, self.config)
        entry = float(df_calc.iloc[-1]['close'])
        atr = float(df_calc.iloc[-1]['atr'])
        
        sl_dist = atr * self.config['riesgo']['stop_loss_atr_multiplicador']
        sl = entry - sl_dist if signal == "Buy" else entry + sl_dist
        tp_ratio = self.config['riesgo']['take_profit_ratio']
        tp_dist = atr * 10 if tp_ratio == 0 else atr * tp_ratio
        tp = entry + tp_dist if signal == "Buy" else entry - tp_dist
        
        qty = round(monto / entry, 3) 
        self.client.place_order(symbol, signal, "Market", qty, sl=sl, tp=tp)
        self.telegram.send_message(f"✅ *Orden Ejecutada (5x)*\n{symbol} {signal}\nSL: {sl:.4f}")
