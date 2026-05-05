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
            symbol=symbol, side=side, order_type="Market",
            qty=qty_str, take_profit=tp_str, stop_loss=sl_str
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
                if tp_dist > 0 and cur_dist >= tp_dist * settings.BREAKEVEN_ACTIVATION_PCT:
                    be_price = state.get("be_price", trade.entry_price)
                    inst = bybit_client.get_instruments_info(symbol=trade.symbol)
                    if inst and trade.symbol in inst:
                        tick = inst[trade.symbol]["tickSize"]
                        be_price_str = self._format_step(be_price, tick)
                    else:
                        be_price_str = str(be_price)
                    bybit_client.set_trading_stop(trade.symbol, stop_loss=be_price_str)
                    state["breakeven_done"] = True
                    logger.info(f"🔒 Breakeven activado {trade.symbol} a {be_price_str}")

            from strategy.ema_strategy import ema_strategy
            resp_k = await bybit_client.get_klines_async(trade.symbol, "1", 30)
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
        inst = bybit_client.get_instruments_info(symbol=trade.symbol)
        if inst and trade.symbol in inst:
            step = inst[trade.symbol]["qtyStep"]
            qty_str = self._format_step(trade.qty, step, round_down=True)
        else:
            qty_str = str(trade.qty)
        resp = bybit_client.place_order(symbol=trade.symbol, side=side, order_type="Market", qty=qty_str, reduce_only=True)
        if resp and resp.get("retCode") == 0:
            self._sync_closed_trade(trade)

    async def force_sync_at_startup(self):
        pass

executor = ExecutionEngine()
