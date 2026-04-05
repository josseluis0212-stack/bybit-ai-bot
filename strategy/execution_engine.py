from strategy.indicators import Indicators
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

    async def check_signal(self, symbol):
        """Analiza la señal usando HYPER SCALPER (VWAP + B-Bands Mean Reversion)"""
        
        entrada_cfg = self.config.get('entrada', {})
        tf = str(entrada_cfg.get('timeframe', '1'))
        velas = int(entrada_cfg.get('velas', 150))
        
        response = await self.client.get_klines_async(symbol=symbol, interval=tf, limit=velas)
        if not response or response.get('retCode') != 0: return None
        klines = response['result']['list']
        
        df = Indicators.klines_to_df(klines)
        
        # Calcular Indicadores Core
        df = Indicators.calculate_vwap(df)
        bb_len = int(entrada_cfg.get('bb_length', 20))
        bb_std = float(entrada_cfg.get('bb_std', 2.0))
        df = Indicators.calculate_bbands(df, length=bb_len, std=bb_std)
        df['vol_ma'] = Indicators.calculate_volume_sma(df, length=int(entrada_cfg.get('volumen_ma_length', 20)))
        df['atr'] = Indicators.calculate_atr(df, 14)
        
        if len(df) < 5: return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Verificar que existen los datos necesarios
        if any(pd.isna(last.get(k)) for k in ['close', 'vwap', 'bb_lower', 'bb_upper', 'vol_ma']):
            return None

        # 1. FILTRO MACRO INSTITUCIONAL (VWAP)
        macro_trend = "ALCISTA" if last['close'] > last['vwap'] else "BAJISTA"
        
        # 2. EVALUACIÓN DE VOLUMEN (Detectar anomalía/spike)
        vol_mult = float(entrada_cfg.get('volumen_spike_mult', 1.5))
        has_volume_spike = last['volume'] > (last['vol_ma'] * vol_mult)
        
        # 3. PATRÓN DE HYPER SCALPING (Cero Fricción)
        # LONG: La vela roza o penetra la banda inferior en 1 minuto
        setup_long = last['low'] <= last['bb_lower']
        
        # SHORT: La vela roza o penetra la banda superior en 1 minuto
        setup_short = last['high'] >= last['bb_upper']
        
        # --- DECISIÓN FINAL SIN FILTROS LENTOS ---
        if setup_long:
            return {
                "side": "Buy",
                "entry": last['close'],
                "atr": last['atr'],
                "vwap": last['vwap']
            }
            
        if setup_short:
            return {
                "side": "Sell",
                "entry": last['close'],
                "atr": last['atr'],
                "vwap": last['vwap']
            }
            
        return None

    async def execute_trade(self, symbol):
        """Ejecuta la orden de Hyper Scalping en Bybit"""
        max_ops = self.config.get('bot', {}).get('max_operaciones_simultaneas', 5)
        posiciones = self.client.get_active_positions()
        if len(posiciones) >= max_ops: return 

        if any(p['symbol'] == symbol for p in posiciones): return

        signal_data = await self.check_signal(symbol)
        if not signal_data: return
            
        side = signal_data["side"]
        entry = signal_data['entry']
        atr = signal_data['atr']
        
        send_log(f"⚡ HYPER SCALP: Señal {side} en {symbol} a {entry}", "log-success")
        
        # Position Sizing
        monto_fijo = float(self.config.get('bot', {}).get('monto_por_operacion_usdt', 100.0))
        apalancamiento = int(self.config.get('bot', {}).get('apalancamiento', 5))
        
        # El qty se calcula como el valor total a controlar (Monto * Apalancamiento) dividido por el precio de entrada
        pos_value = monto_fijo * apalancamiento
        qty = pos_value / entry
        
        # Stop Loss protegido a 1 ATR de la vela de gatillo
        sl_dist = atr 
        if sl_dist <= 0: return
        
        rr = float(self.config.get('riesgo', {}).get('rr_take_profit', 1.5))
        tp_dist = sl_dist * rr
        
        sl = entry - sl_dist if side == "Buy" else entry + sl_dist
        tp = entry + tp_dist if side == "Buy" else entry - tp_dist
        
        apalancamiento = int(self.config.get('bot', {}).get('apalancamiento', 10))
        
        await self.telegram.send_message(
            f"⚡ *HYPER SCALP EJECUTADO*\n\n"
            f"💎 *Moneda:* {symbol}\n"
            f"🚀 *Acción:* {side} @ {entry:.4f}\n"
            f"📈 *VWAP:* {signal_data['vwap']:.4f}\n"
            f"⚖️ *Lev:* {apalancamiento}x"
        )
        
        response = self.client.place_order(symbol, side, "Market", qty, sl=sl, tp=tp)
        
        if response and response.get("retCode") == 0:
            send_log(f"Ejecución exitosa en {symbol} (Pos: {pos_value:.2f} USD)", "log-success")
        else:
            ret_msg = response.get("retMsg") if response else "Sin respuesta"
            send_log(f"Fallo en {symbol}: {ret_msg}", "log-error")
            await self.telegram.send_message(f"❌ *Fail {symbol}*: {ret_msg}")
