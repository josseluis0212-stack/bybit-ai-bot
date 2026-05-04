import logging
import asyncio
from datetime import datetime, timedelta
import pandas as pd
from api.bybit_client import bybit_client
from database.db_manager import db_manager
from risk_management.risk_manager import risk_manager
from config.settings import settings

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self):
        self.trade_state: dict = {}
        self.cooldowns: dict = {}  # {symbol: timestamp_of_loss}
        self.max_positions = settings.MAX_CONCURRENT_TRADES

    def _format_step(self, value, step, round_down=False):
        if not step or float(step) == 0: return str(value)
        step_f = float(step)
        precision = 0
        if "." in str(step):
            precision = len(str(step).split(".")[1])
        
        val = float(value)
        if round_down:
            fact = 10 ** precision
            val = (int(val * fact)) / fact
        return f"{val:.{precision}f}"

    async def try_execute_signal(self, signal_data: dict) -> bool:
        symbol      = signal_data["symbol"]
        side_sig    = signal_data["signal"]
        entry_price = signal_data["entry_price"]
        sl_price    = signal_data["sl"]
        tp1         = signal_data["tp1"]
        be_price    = signal_data.get("breakeven_price")

        active_positions = bybit_client.get_active_positions()
        open_orders      = bybit_client.get_open_orders()
        
        total_slots_used = len(active_positions) + len(open_orders)

        if total_slots_used >= self.max_positions:
            logger.info(f"Bloqueo: Límite de 10 operaciones alcanzado (Pos: {len(active_positions)}, Ord: {len(open_orders)})")
            return False

        if any(p["symbol"] == symbol for p in active_positions) or any(o["symbol"] == symbol for o in open_orders):
            return False

        if symbol in self.cooldowns:
            if datetime.now() < self.cooldowns[symbol] + timedelta(minutes=15):
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

        bybit_client.set_leverage(symbol, settings.LEVERAGE)
        side = "Buy" if side_sig == "LONG" else "Sell"

        logger.info(f"🚀 [EMA PRO] EJECUTANDO {symbol} {side} | Qty={qty_str}")
        resp = bybit_client.place_order(
            symbol=symbol, side=side, order_type="Limit",
            qty=qty_str, price=entry_price, take_profit=tp_str, stop_loss=sl_str
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
                    "be_price": be_price
                }
            return True
        return False

    async def check_open_positions(self):
        # Check and cancel limit orders older than 10 mins
        open_orders = bybit_client.get_open_orders()
        if open_orders:
            for order in open_orders:
                try:
                    created = float(order.get("createdTime", 0)) / 1000.0
                    if datetime.now().timestamp() - created > 600: # 10 mins
                        bybit_client.cancel_order(order["symbol"], order["orderId"])
                        logger.info(f"Cancelando orden Limit expirada (>10m) de {order['symbol']}")
                except Exception as e:
                    pass

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
            is_long = trade.side == "LONG"
            state = self.trade_state.get(trade.id, {})

            if not state.get("breakeven_done", False):
                tp_dist = abs(trade.take_profit - trade.entry_price)
                cur_dist = (cur_price - trade.entry_price) if is_long else (trade.entry_price - cur_price)
                
                # Activar Breakeven al 60% del camino al TP (según dashboard)
                if tp_dist > 0 and cur_dist >= tp_dist * 0.6:
                    be_price = state.get("be_price", trade.entry_price)
                    bybit_client.set_trading_stop(trade.symbol, stop_loss=str(be_price))
                    state["breakeven_done"] = True
                    logger.info(f"🔒 Breakeven activado {trade.symbol} (60% alcanzado)")

                # Liberar TP al 90% para dejar correr la tendencia (EMA Trailing)
                if tp_dist > 0 and cur_dist >= tp_dist * 0.9 and not state.get("tp_released", False):
                    bybit_client.set_trading_stop(trade.symbol, take_profit="0")
                    state["tp_released"] = True
                    logger.info(f"🚀 [TRAIL] TP Liberado en {trade.symbol} para dejar correr tendencia hasta cruce EMA")

            from strategy.ema_strategy import ema_strategy
            resp_k = bybit_client.get_klines(trade.symbol, "1", 30)
            if resp_k and resp_k.get("retCode") == 0:
                df = pd.DataFrame(resp_k["result"]["list"], columns=["ts","o","h","l","c","v","t"])
                df = df.sort_values("ts", ascending=True).reset_index(drop=True)
                df['close'] = pd.to_numeric(df['c'])
                if ema_strategy.should_trail_close(df, trade.side):
                    logger.info(f"📉 Trailing EMA para {trade.symbol} — Cerrando")
                    self._force_close(trade, "EMA_TRAILING")

            self.trade_state[trade.id] = state

    def _sync_closed_trade(self, trade):
        resp = bybit_client.get_closed_pnl(symbol=trade.symbol, limit=1)
        if resp and resp.get("retCode") == 0 and resp["result"]["list"]:
            last = resp["result"]["list"][0]
            db_manager.close_trade(trade.id, float(last["avgExitPrice"]), float(last["closedPnl"]), 0, "BYBIT_SYNC")
            if float(last["closedPnl"]) < 0:
                self.cooldowns[trade.symbol] = datetime.now()
        else:
            db_manager.close_trade(trade.id, trade.entry_price, 0, 0, "UNKNOWN_SYNC")
        self.trade_state.pop(trade.id, None)

    def _force_close(self, trade, reason):
        side = "Sell" if trade.side == "LONG" else "Buy"
        resp = bybit_client.place_order(symbol=trade.symbol, side=side, order_type="Market", qty=str(trade.qty), reduce_only=True)
        if resp and resp.get("retCode") == 0:
            self._sync_closed_trade(trade)

    async def force_sync_at_startup(self):
        """Sincroniza el estado interno con la base de datos al iniciar."""
        try:
            logger.info("🔄 Sincronizando estado interno con la base de datos...")
            open_trades = db_manager.get_open_trades()
            for trade in open_trades:
                # Reconstruir estado mínimo para no perder seguimiento
                self.trade_state[trade.id] = {
                    "breakeven_done": False, 
                    "be_price": trade.entry_price * 1.0015 if trade.side == "LONG" else trade.entry_price * 0.9985
                }
            logger.info(f"✅ Sincronización completada. Monitoreando {len(open_trades)} posiciones.")
        except Exception as e:
            logger.error(f"Error en sincronización inicial: {e}")

    async def emergency_close_all(self) -> bool:
        """Cierra todas las posiciones y cancela todas las órdenes."""
        try:
            logger.warning("🚨 [PANIC] Ejecutando cierre de emergencia...")
            # 1. Cancelar órdenes
            bybit_client.cancel_all_orders()
            
            # 2. Cierre masivo de posiciones
            positions = bybit_client.get_active_positions()
            for p in positions:
                side = "Sell" if p["side"] == "Buy" else "Buy"
                bybit_client.place_order(
                    symbol=p["symbol"],
                    side=side,
                    order_type="Market",
                    qty=p["size"],
                    reduce_only=True
                )
                logger.info(f"Cerrada posición de {p['symbol']}")
            
            # 3. Limpiar estado interno y DB
            self.trade_state = {}
            db_manager.reset_all_stats()
            logger.info("✅ Pánico completado con éxito")
            return True
        except Exception as e:
            logger.error(f"Error en cierre de emergencia: {e}")
            return False

executor = ExecutionEngine()
