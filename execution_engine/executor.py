import logging
import asyncio
from datetime import datetime, timedelta
import pandas as pd
import time
from api.bybit_client import bybit_client
from database.db_manager import db_manager
from risk_management.risk_manager import risk_manager
from config.settings import settings

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self):
        self.trade_state: dict = {}
        self.cooldowns: dict = {}  # {symbol: timestamp_of_loss}
        self.max_positions = 10

    def _format_step(self, value, step, round_down=False):
        if not step or float(step) == 0: return str(value)
        from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
        val_d = Decimal(str(value))
        step_d = Decimal(str(step))
        if round_down:
            aligned_val = (val_d / step_d).quantize(Decimal('1'), rounding=ROUND_DOWN) * step_d
        else:
            aligned_val = (val_d / step_d).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * step_d
        result = format(aligned_val, 'f')
        if '.' in result:
            result = result.rstrip('0').rstrip('.')
        return result

    async def try_execute_signal(self, signal_data: dict) -> bool:
        symbol      = signal_data["symbol"]
        side_sig    = signal_data["signal"]
        entry_price = signal_data["entry_price"]
        sl_price    = signal_data["sl"]
        tp1         = signal_data["tp1"]
        be_price    = signal_data.get("breakeven_price")

        active_positions = bybit_client.get_active_positions()
        if len(active_positions) >= self.max_positions:
            return False

        if any(p["symbol"] == symbol for p in active_positions):
            return False

        if symbol in self.cooldowns:
            if datetime.now() < self.cooldowns[symbol] + timedelta(minutes=30):
                return False
            else:
                del self.cooldowns[symbol]

        balance_info = bybit_client.get_wallet_balance()
        avail = 0.0
        if balance_info and balance_info.get("retCode") == 0:
            for c in balance_info["result"]["list"][0]["coin"]:
                if c["coin"] == "USDT":
                    avail = float(c["walletBalance"])

        if not risk_manager.can_open_new_trade(len(active_positions), avail):
            return False

        qty = risk_manager.calculate_position_size(entry_price)
        inst = bybit_client.get_instruments_info(symbol=symbol)
        if not inst or symbol not in inst: return False
        
        tick = inst[symbol]["tickSize"]
        step = inst[symbol]["qtyStep"]

        qty_str = self._format_step(qty, step, round_down=True)
        sl_str  = self._format_step(sl_price, tick)
        tp_str  = self._format_step(tp1, tick)

        if float(qty_str) <= 0: return False

        # Verificar si ya hay una orden límite abierta para este símbolo
        open_orders = bybit_client.get_open_orders(symbol=symbol)
        if open_orders:
            logger.warning(f"⚠️ Ya existe una orden abierta para {symbol}, ignorando señal.")
            return False

        # Calcular precio Límite "pegadito" al mercado
        offset = 0.0002 
        limit_price = entry_price * (1 + offset) if side_sig == "LONG" else entry_price * (1 - offset)
        limit_price_str = self._format_step(limit_price, tick)

        bybit_client.set_leverage(symbol, settings.LEVERAGE)
        side = "Buy" if side_sig == "LONG" else "Sell"

        logger.info(f"🚀 [LIMIT ADV] EJECUTANDO {symbol} {side} | Qty={qty_str} | Price={limit_price_str}")
        resp = bybit_client.place_order(
            symbol=symbol, side=side, order_type="Limit",
            price=limit_price_str, qty=qty_str, 
            take_profit=tp_str, stop_loss=sl_str,
            time_in_force="GTC"
        )

        if resp and resp.get("retCode") == 0:
            trade_id = db_manager.add_trade(
                symbol=symbol, side=side_sig, entry_price=entry_price,
                sl=sl_price, tp=tp1, qty=float(qty_str),
                leverage=settings.LEVERAGE, risk_usdt=0
            )
            if trade_id:
                self.trade_state[trade_id] = {
                    "breakeven_done": False,
                    "trailing_active": False,
                    "be_price": be_price
                }
            return True

        return False

    async def check_open_positions(self):
        open_trades = db_manager.get_open_trades()
        if not open_trades: return

        active_positions = bybit_client.get_active_positions()
        real_map = {p["symbol"]: p for p in active_positions}

        for trade in open_trades:
            if trade.symbol not in real_map:
                self._sync_closed_trade(trade)
                continue

            pos = real_map[trade.symbol]
            cur_price = float(pos.get("markPrice", 0))
            if cur_price <= 0:
                continue

            is_long = trade.side == "LONG"
            state = self.trade_state.get(trade.id, {
                "breakeven_done": False,
                "trailing_active": False,
                "be_price": None
            })

            tp_dist = abs(trade.take_profit - trade.entry_price)
            if tp_dist <= 0:
                self.trade_state[trade.id] = state
                continue

            cur_dist = (cur_price - trade.entry_price) if is_long else (trade.entry_price - cur_price)

            # 1. BREAKEVEN
            if not state.get("breakeven_done", False) and cur_dist >= tp_dist * settings.BREAKEVEN_ACTIVATION_PCT:
                try:
                    profit_to_lock = tp_dist * settings.BREAKEVEN_PROFIT_PCT
                    be_price = trade.entry_price + profit_to_lock if is_long else trade.entry_price - profit_to_lock

                    inst = bybit_client.get_instruments_info(symbol=trade.symbol)
                    tick = inst[trade.symbol]["tickSize"] if inst and trade.symbol in inst else None
                    be_price_str = self._format_step(be_price, tick) if tick else str(round(be_price, 8))

                    resp_be = bybit_client.set_trading_stop(trade.symbol, stop_loss=be_price_str)
                    if resp_be and resp_be.get("retCode") == 0:
                        state["breakeven_done"] = True
                        state["be_price"] = float(be_price_str)
                        logger.info(f"🔒 BREAKEVEN activado en {trade.symbol} | SL movido a {be_price_str}")
                except Exception as e:
                    logger.error(f"❌ Error activando Breakeven en {trade.symbol}: {e}")

            # 2. TRAILING STOP
            if state.get("breakeven_done", False) and not state.get("trailing_active", False) and cur_dist >= tp_dist * settings.TRAILING_STOP_ACTIVATION_PCT:
                try:
                    trail_dist = tp_dist * 0.10
                    inst = bybit_client.get_instruments_info(symbol=trade.symbol)
                    tick = inst[trade.symbol]["tickSize"] if inst and trade.symbol in inst else None
                    trail_dist_str = self._format_step(trail_dist, tick) if tick else str(round(trail_dist, 8))

                    resp_ts = bybit_client.set_trading_stop(trade.symbol, take_profit="0", trailing_stop=trail_dist_str)
                    if resp_ts and resp_ts.get("retCode") == 0:
                        state["trailing_active"] = True
                        logger.info(f"🚀 TRAILING STOP activado en {trade.symbol} | Distancia: {trail_dist_str}")
                except Exception as e:
                    logger.error(f"❌ Error activando Trailing en {trade.symbol}: {e}")

            # 3. EMA TRAILING CONDICIONAL (Solo en pérdida)
            try:
                cur_pnl_est = (cur_price - trade.entry_price) if is_long else (trade.entry_price - cur_price)
                if cur_pnl_est < 0: 
                    from strategy.ema_strategy import ema_strategy
                    resp_k = await bybit_client.get_klines_async(trade.symbol, "1", 30)
                    if resp_k and resp_k.get("retCode") == 0:
                        df = pd.DataFrame(resp_k["result"]["list"], columns=["ts","o","h","l","c","v","t"])
                        df = df.sort_values("ts", ascending=True).reset_index(drop=True)
                        df['close'] = pd.to_numeric(df['c'])
                        if ema_strategy.should_trail_close(df, trade.side):
                            logger.info(f"📉 Salida preventiva EMA por debilidad en {trade.symbol} (en pérdida)")
                            self._force_close(trade, "EMA_EXIT_LOSS")
            except Exception as e:
                logger.warning(f"⚠️ Error en EMA check para {trade.symbol}: {e}")

            self.trade_state[trade.id] = state

    def get_trade_status(self, trade_id):
        state = self.trade_state.get(trade_id, {})
        return {
            "be_active": state.get("breakeven_done", False),
            "ts_active": state.get("trailing_active", False)
        }

    async def emergency_close_all(self):
        logger.info("🚨 EJECUTANDO CIERRE DE EMERGENCIA TOTAL")
        try:
            active_positions = bybit_client.get_active_positions()
            for pos in active_positions:
                symbol = pos["symbol"]
                side = "Sell" if pos["side"] == "Buy" else "Buy"
                qty = pos["size"]
                bybit_client.place_order(symbol=symbol, side=side, order_type="Market", qty=qty, reduce_only=True)
            bybit_client.cancel_all_orders()
            return True
        except Exception as e:
            logger.error(f"Error en cierre de emergencia: {e}")
            return False

    def _sync_closed_trade(self, trade):
        time.sleep(1.5)
        resp = bybit_client.get_closed_pnl(symbol=trade.symbol, limit=1)
        reason = "DESCONOCIDO"
        if resp and resp.get("retCode") == 0 and resp["result"]["list"]:
            last = resp["result"]["list"][0]
            exit_price = float(last["avgExitPrice"])
            pnl_bybit = float(last["closedPnl"])
            is_long = trade.side == "LONG"
            raw_pnl = (exit_price - trade.entry_price) * trade.qty if is_long else (trade.entry_price - exit_price) * trade.qty
            volumen = trade.entry_price * trade.qty
            pnl_final = raw_pnl - (volumen * 0.001)
            pnl = pnl_bybit if abs(pnl_bybit) > abs(pnl_final) * 0.8 else pnl_final
            
            state = self.trade_state.get(trade.id, {})
            if state.get("trailing_active"): reason = "TRAILING STOP"
            elif state.get("breakeven_done"): reason = "BREAKEVEN"
            elif pnl < 0: reason = "STOP LOSS"
            else: reason = "PROFIT (TS/BE)"

            if pnl > 0 and reason == "STOP LOSS": reason = "BREAKEVEN"
            pnl_pct = (pnl / (trade.entry_price * trade.qty / trade.leverage)) * 100 if trade.qty > 0 else 0
            db_manager.close_trade(trade.id, exit_price, pnl, pnl_pct, reason)
            if pnl < 0: self.cooldowns[trade.symbol] = datetime.now()
            logger.info(f"✅ Sincronizado {trade.symbol} | PnL: {pnl:+.4f} | Razón: {reason}")
        else:
            db_manager.close_trade(trade.id, trade.entry_price, 0, 0, "SYNC_ERROR")
        self.trade_state.pop(trade.id, None)

    def _force_close(self, trade, reason):
        side = "Sell" if trade.side == "LONG" else "Buy"
        inst = bybit_client.get_instruments_info(symbol=trade.symbol)
        qty_str = self._format_step(trade.qty, inst[trade.symbol]["qtyStep"], True) if inst and trade.symbol in inst else str(trade.qty)
        resp = bybit_client.place_order(symbol=trade.symbol, side=side, order_type="Market", qty=qty_str, reduce_only=True)
        if resp and resp.get("retCode") == 0: self._sync_closed_trade(trade)

    async def force_sync_at_startup(self):
        logger.info("🔄 Sincronización inicial de posiciones...")
        try:
            active_positions = bybit_client.get_active_positions()
            open_trades = db_manager.get_open_trades()
            db_symbols = {t.symbol for t in open_trades}
            for pos in active_positions:
                symbol = pos["symbol"]
                if symbol not in db_symbols:
                    side = "LONG" if pos["side"] == "Buy" else "SHORT"
                    entry_price, qty = float(pos["avgPrice"]), float(pos["size"])
                    sl_raw, tp_raw = pos.get("stopLoss", ""), pos.get("takeProfit", "")
                    sl = float(sl_raw) if sl_raw else entry_price * 0.99
                    tp = float(tp_raw) if tp_raw else entry_price * 1.02
                    db_manager.add_trade(symbol=symbol, side=side, entry_price=entry_price, sl=sl, tp=tp, qty=qty, leverage=settings.LEVERAGE, risk_usdt=0)
            
            open_trades = db_manager.get_open_trades()
            real_symbols = {p["symbol"] for p in active_positions}
            for trade in open_trades:
                if trade.symbol in real_symbols:
                    pos = next((p for p in active_positions if p["symbol"] == trade.symbol), None)
                    be_done, ts_active = False, False
                    if pos:
                        tp_bybit = pos.get("takeProfit", "")
                        if not tp_bybit or tp_bybit == "0": be_done, ts_active = True, True
                        elif abs(float(pos["markPrice"]) - trade.entry_price) >= abs(trade.take_profit - trade.entry_price) * settings.BREAKEVEN_ACTIVATION_PCT: be_done = True
                    self.trade_state[trade.id] = {"breakeven_done": be_done, "trailing_active": ts_active, "be_price": None}
        except Exception as e: logger.error(f"Error en sincronización inicial: {e}")

    async def cleanup_old_orders(self):
        try:
            open_orders = bybit_client.get_open_orders()
            if not open_orders: return
            now_ts = int(time.time() * 1000)
            for order in open_orders:
                if now_ts - int(order.get("createdTime", now_ts)) > 10 * 60 * 1000:
                    bybit_client.cancel_order(order["symbol"], order["orderId"])
        except Exception as e: logger.error(f"Error en limpieza de órdenes: {e}")

executor = ExecutionEngine()
