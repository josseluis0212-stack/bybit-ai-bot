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

    async def check_signal(self, symbol):
        """Analiza la señal usando triple pantalla de forma asíncrona"""
        # 1. FILTRO MACRO (DIARIO - 1D) 🌊
        response_d = await self.client.get_klines_async(symbol=symbol, interval="D", limit=100)
        if not response_d or response_d.get('retCode') != 0: return None
        klines_d = response_d['result']['list']
        
        df_d = Indicators.klines_to_df(klines_d)
        df_d = Indicators.add_indicators(df_d, self.config)
        last_d = df_d.iloc[-1]
        
        # Tendencia Diaria: Precio > EMA200
        ema200_d = last_d.get('ema_trend', 0)
        tendencia_diaria_alcista = last_d['close'] > ema200_d and last_d['rsi'] > 50
        tendencia_diaria_bajista = last_d['close'] < ema200_d and last_d['rsi'] < 50
        
        # 2. FILTRO TÁCTICO (1 HORA - 1H) 💪
        response_1h = await self.client.get_klines_async(symbol=symbol, interval="60", limit=50)
        if not response_1h or response_1h.get('retCode') != 0: return None
        klines_1h = response_1h['result']['list']
        
        df_1h = Indicators.klines_to_df(klines_1h)
        df_1h = Indicators.add_indicators(df_1h, self.config)
        last_1h = df_1h.iloc[-1]
        
        # Fuerza H1: ADX > 15
        if last_1h['adx'] <= 15: return None 

        alineacion_1h_alcista = last_1h['close'] > last_1h['ema_slow']
        alineacion_1h_bajista = last_1h['close'] < last_1h['ema_slow']
        
        # 3. GATILLO MICRO (5 MIN - 5m) 🔫
        response_5m = await self.client.get_klines_async(symbol=symbol, interval="5", limit=100)
        if not response_5m or response_5m.get('retCode') != 0: return None
        klines_5m = response_5m['result']['list']
        
        df_5m = Indicators.klines_to_df(klines_5m)
        df_5m = Indicators.add_indicators(df_5m, self.config)
        
        last_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]
        
        # Cruce EMAs 8/21
        cruce_buy = prev_5m['ema_fast'] <= prev_5m['ema_slow'] and last_5m['ema_fast'] > last_5m['ema_slow']
        cruce_sell = prev_5m['ema_fast'] >= prev_5m['ema_slow'] and last_5m['ema_fast'] < last_5m['ema_slow']
        
        # Volumen Power (> Promedio)
        vol_power = last_5m['volume'] > last_5m['vol_ma']
        
        if not vol_power: return None

        # --- EVALUACIÓN FINAL ---
        if cruce_buy and tendencia_diaria_alcista and alineacion_1h_alcista:
            return "Buy"
            
        if cruce_sell and tendencia_diaria_bajista and alineacion_1h_bajista:
            return "Sell"
            
        return None



    async def execute_trade(self, symbol):
        """Ejecuta la lógica de trading para un símbolo de forma asíncrona"""
        # 1. ESTRATEGIA PRINCIPAL (TRIPLE PANTALLA)
        # Verificar Límite de 5 Operaciones (usando sesión síncrona aquí está bien, es una sola llamada)
        posiciones = self.client.get_active_positions()
        if len(posiciones) >= self.config['trading']['max_operaciones_simultaneas']:
            return 

        if any(p['symbol'] == symbol for p in posiciones): return

        # Buscar señal PRINCIPAL (Asíncrono)
        signal = await self.check_signal(symbol)
        if not signal: return
            
        send_log(f"¡Señal detectada en {symbol}: {signal}!", "log-success")
        await self.telegram.send_message(
            f"🏛️ *SEÑAL INSTITUCIONAL*\n\n"
            f"💎 *Moneda:* {symbol}\n"
            f"🚀 *Dirección:* {signal}\n"
            f"✅ Diario: Tendencia OK\n"
            f"✅ 1 Hora: Alineación OK\n"
            f"✅ 5 Min: Gatillo Activado"
        )
        
        # Ejecución
        balance = self.client.get_balance()
        monto = self.config['trading']['monto_por_operacion'] 
        
        # IA Scoring
        if self.memory_manager.get_coin_score(symbol) < self.config['ia']['umbral_aprendizaje']: 
            monto *= 0.5 

        # Datos para SL/TP
        response_calc = await self.client.get_klines_async(symbol=symbol, interval="5", limit=20)
        if not response_calc or response_calc.get('retCode') != 0: return
        klines = response_calc['result']['list']
        
        df_calc = Indicators.klines_to_df(klines)
        df_calc = Indicators.add_indicators(df_calc, self.config)
        entry = float(df_calc.iloc[-1]['close'])
        atr = float(df_calc.iloc[-1]['atr'])
        
        # Stops
        sl_dist = atr * self.config['riesgo']['stop_loss_atr_multiplicador']
        sl = entry - sl_dist if signal == "Buy" else entry + sl_dist
        
        # TP
        tp_ratio = self.config['riesgo']['take_profit_ratio']
        tp_dist = atr * 10 if tp_ratio == 0 else atr * tp_ratio
        tp = entry + tp_dist if signal == "Buy" else entry - tp_dist
        
        # Cantidad
        qty = round(monto / entry, 3) 
        
        # Enviar orden (Síncrono por ahora, pero con logs mejorados)
        response = self.client.place_order(symbol, signal, "Market", qty, sl=sl, tp=tp)
        
        if response and response.get("retCode") == 0:
            msg_final = f"✅ *Orden Ejecutada en {symbol}*\nDirección: {signal}\nSL: {sl:.4f}\nTP: {tp:.4f}"
            send_log(f"Orden exitosa en {symbol}", "log-success")
        else:
            ret_msg = response.get("retMsg") if response else "Sin respuesta"
            msg_final = f"❌ *Error al ejecutar en {symbol}*\nMotivo: {ret_msg}"
            send_log(f"Fallo en {symbol}: {ret_msg}", "log-error")
            
        await self.telegram.send_message(msg_final)
