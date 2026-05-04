"""
LRMC PRO — Execution Engine
Gestión de órdenes con TP parciales (TP1 50% / TP2 30% / TP3 20%),
breakeven en 1R y cierre por estancamiento.
"""
import logging
import asyncio
import math
from decimal import Decimal
from datetime import datetime, timezone
from api.bybit_client import bybit_client
from database.db_manager import db_manager
from risk_management.risk_manager import risk_manager
from config.settings import settings
from notifications.telegram_bot import telegram_notifier
from strategy.lrmc_strategy import lrmc_strategy

logger = logging.getLogger(__name__)

# Gestión dinámica LRMC
BREAKEVEN_AT_R     = 1.0   # Mover SL a BE cuando el precio llega a 1R
STAGNATION_CANDLES = 10    # Ciclos sin movimiento → cerrar
STAGNATION_MOVE_PCT = 0.002  # Movimiento mínimo esperado (0.2%)

class ExecutionEngine:
    def __init__(self):
        self.last_report_count = -1
        # Seguimiento de trades parciales: {trade_id: {"tp1_done": bool, "tp2_done": bool, "stagnation_count": int, "last_price": float}}
        self.trade_state: dict = {}

    # ─── FORMATEO ─────────────────────────────────────────────────────────────

    def _format_step(self, value, step_string, round_down=False):
        try:
            step_dec = Decimal(str(step_string))
            val_dec  = Decimal(str(value))
            if round_down:
                rounded = math.floor(val_dec / step_dec) * step_dec
            else:
                rounded = round(val_dec / step_dec) * step_dec
            decimals = abs(step_dec.as_tuple().exponent)
            return f"{float(rounded):.{decimals}f}"
        except:
            return f"{float(value):.4f}"

    # ─── ENTRADA ──────────────────────────────────────────────────────────────

    async def try_execute_signal(self, signal_data: dict) -> bool:
        symbol      = signal_data["symbol"]
        signal      = signal_data["signal"]
        entry_price = signal_data["entry_price"]
        sl_price    = signal_data["sl"]
        tp1         = signal_data["tp1"]
        tp2         = signal_data["tp2"]
        tp3         = signal_data["tp3"]

        # Verificar límite de trades abiertos
        active_positions = bybit_client.get_active_positions()
        open_count = len(active_positions)
        if open_count >= settings.MAX_CONCURRENT_TRADES:
            return False

        # Verificar balance
        balance_info = bybit_client.get_wallet_balance()
        available_balance = 0.0
        if balance_info and balance_info.get("retCode") == 0:
            coins = balance_info["result"]["list"][0]["coin"]
            usdt = next((c for c in coins if c["coin"] == "USDT"), None)
            if usdt:
                available_balance = float(usdt["walletBalance"])

        if not risk_manager.can_open_new_trade(open_count, available_balance):
            return False

        # Calcular cantidad total
        qty = risk_manager.calculate_position_size(entry_price)
        inst_info = bybit_client.get_instruments_info(symbol=symbol)
        tick_size = inst_info[symbol]["tickSize"] if inst_info and symbol in inst_info else "0.0001"
        qty_step  = inst_info[symbol]["qtyStep"]  if inst_info and symbol in inst_info else "0.001"

        qty_str  = self._format_step(qty,       qty_step,  round_down=True)
        sl_str   = self._format_step(sl_price,  tick_size)
        tp1_str  = self._format_step(tp1,       tick_size)

        if float(qty_str) <= 0:
            return False

        # Apalancamiento
        bybit_client.set_leverage(symbol, settings.LEVERAGE)
        side = "Buy" if signal == "LONG" else "Sell"

        logger.info(
            f"🚀 [LRMC] ENTRANDO {signal} | {symbol} | "
            f"Entry={entry_price:.4f} SL={sl_str} TP1={tp1_str}"
        )

        # Orden límite con TP1 y SL nativos (los TPs parciales se gestionan manualmente)
        response = bybit_client.place_order(
            symbol=symbol, side=side, order_type="Limit",
            qty=qty_str, price=str(entry_price),
            take_profit=tp1_str, stop_loss=sl_str,
            time_in_force="PostOnly"
        )

        if response and response.get("retCode") == 0:
            risk_usdt = abs(entry_price - sl_price) * float(qty_str)
            trade_id = db_manager.add_trade(
                symbol=symbol, side=signal, entry_price=entry_price,
                sl=sl_price, tp=tp1, qty=float(qty_str),
                leverage=settings.LEVERAGE, risk_usdt=risk_usdt
            )

            # Inicializar estado del trade para gestión dinámica
            if trade_id:
                self.trade_state[trade_id] = {
                    "tp1_done":        False,
                    "tp2_done":        False,
                    "breakeven_done":  False,
                    "stagnation_count": 0,
                    "last_price":      entry_price,
                    "tp1":             tp1,
                    "tp2":             tp2,
                    "tp3":             tp3,
                    "tp1_pct":         signal_data.get("tp1_pct", 0.50),
                    "tp2_pct":         signal_data.get("tp2_pct", 0.30),
                    "original_qty":    float(qty_str),
                }

            await telegram_notifier.notify_order_opened(
                symbol=symbol, side=signal, entry_price=f"{entry_price:.4f}",
                sl=sl_str, tp=tp1_str, qty=qty_str,
                leverage=settings.LEVERAGE, current_trades=open_count + 1,
                max_trades=settings.MAX_CONCURRENT_TRADES, risk_usdt=f"{risk_usdt:.2f}"
            )
            return True

        logger.warning(f"[LRMC] Orden rechazada {symbol}: {response}")
        return False

    # ─── MONITOREO DE POSICIONES ABIERTAS ────────────────────────────────────

    async def check_open_positions(self):
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            return

        active_positions = bybit_client.get_active_positions()
        real_positions   = {p["symbol"]: p for p in active_positions}
        tickers          = bybit_client.get_tickers()
        ticker_map       = {t["symbol"]: t for t in tickers} if tickers else {}

        for trade in open_trades:
            symbol = trade.symbol

            # ── A. SINCRONIZACIÓN: posición ya no existe en Bybit ─────────────
            if symbol not in real_positions:
                await self._sync_closed_trade(trade, ticker_map)
                continue

            # ── B. PRECIO ACTUAL ──────────────────────────────────────────────
            pos = real_positions[symbol]
            cur_price = float(pos.get("markPrice", 0)) or \
                        float(ticker_map.get(symbol, {}).get("lastPrice", 0))
            if cur_price == 0:
                continue

            is_long = trade.side == "LONG"
            risk    = abs(trade.entry_price - trade.stop_loss)
            if risk <= 0:
                continue

            state = self.trade_state.get(trade.id, {})

            # ── C. BREAKEVEN en 1R ────────────────────────────────────────────
            if not state.get("breakeven_done", False):
                profit_dist = (cur_price - trade.entry_price) if is_long else (trade.entry_price - cur_price)
                if profit_dist >= risk * BREAKEVEN_AT_R:
                    be_price = trade.entry_price * 1.0003 if is_long else trade.entry_price * 0.9997
                    current_sl = float(pos.get("stopLoss", 0))
                    move_be = (is_long and current_sl < be_price) or \
                              (not is_long and (current_sl > be_price or current_sl == 0))
                    if move_be:
                        inst = bybit_client.get_instruments_info(symbol=symbol)
                        tick = inst[symbol]["tickSize"] if inst and symbol in inst else "0.0001"
                        be_str = self._format_step(be_price, tick)
                        bybit_client.set_trading_stop(symbol, stop_loss=be_str)
                        state["breakeven_done"] = True
                        logger.info(f"[LRMC] 🔒 Breakeven activado {symbol} → SL={be_str}")

            # ── D. TP PARCIALES ───────────────────────────────────────────────
            tp1 = state.get("tp1", 0)
            tp2 = state.get("tp2", 0)
            tp1_pct = state.get("tp1_pct", 0.50)
            tp2_pct = state.get("tp2_pct", 0.30)
            original_qty = state.get("original_qty", trade.qty)

            # TP1 (50%): cerrar parcialmente y mover TP al TP2
            if not state.get("tp1_done", False) and tp1 > 0:
                tp1_hit = (is_long and cur_price >= tp1) or (not is_long and cur_price <= tp1)
                if tp1_hit:
                    close_qty = original_qty * tp1_pct
                    await self._partial_close(trade, close_qty, "TP1_50%")
                    # Actualizar TP nativo a TP2
                    tp2_str = self._format_step(tp2, "0.0001") if tp2 > 0 else "0"
                    if tp2_str != "0":
                        bybit_client.set_trading_stop(symbol, take_profit=tp2_str)
                    state["tp1_done"] = True
                    logger.info(f"[LRMC] 🎯 TP1 alcanzado {symbol} — cerrando 50%")

            # TP2 (30%): cerrar parcialmente
            elif state.get("tp1_done") and not state.get("tp2_done", False):
                tp2_hit = (is_long and cur_price >= tp2) or (not is_long and cur_price <= tp2)
                if tp2_hit:
                    close_qty = original_qty * tp2_pct
                    await self._partial_close(trade, close_qty, "TP2_30%")
                    # El 20% restante corre libre con trailing
                    tp3 = state.get("tp3", 0)
                    if tp3 > 0:
                        tp3_str = self._format_step(tp3, "0.0001")
                        bybit_client.set_trading_stop(symbol, take_profit=tp3_str)
                    state["tp2_done"] = True
                    logger.info(f"[LRMC] 🎯 TP2 alcanzado {symbol} — cerrando 30%")

            # ── E. SEÑAL CONTRARIA → SALIR ────────────────────────────────────
            # (se delega al scanner principal, aquí solo chequeamos estancamiento)

            # ── F. ESTANCAMIENTO (10 ciclos sin moverse ≥ 0.2%) ──────────────
            last_price = state.get("last_price", trade.entry_price)
            move_pct = abs(cur_price - last_price) / last_price if last_price > 0 else 0
            if move_pct < STAGNATION_MOVE_PCT:
                state["stagnation_count"] = state.get("stagnation_count", 0) + 1
            else:
                state["stagnation_count"] = 0
                state["last_price"] = cur_price

            if state.get("stagnation_count", 0) >= STAGNATION_CANDLES:
                logger.info(f"[LRMC] ⏱️ Estancamiento {symbol} — cerrando posición")
                await self._force_close_and_notify(trade, "STAGNATION_EXIT")
                state["stagnation_count"] = 0
                continue

            self.trade_state[trade.id] = state

        # Reporte cada 10 trades cerrados
        closed_count = db_manager.get_closed_trades_count()
        if closed_count > 0 and closed_count % 10 == 0 and closed_count != self.last_report_count:
            self.last_report_count = closed_count
            from analytics.analytics_manager import analytics_manager
            msg = analytics_manager.get_combined_periodic_report()
            if msg:
                await telegram_notifier.send_message(msg)

    # ─── CIERRE PARCIAL ───────────────────────────────────────────────────────

    async def _partial_close(self, trade, qty_to_close: float, reason: str):
        """Cierra una porción de la posición a mercado."""
        symbol = trade.symbol
        side   = "Sell" if trade.side == "LONG" else "Buy"
        inst   = bybit_client.get_instruments_info(symbol=symbol)
        step   = inst[symbol]["qtyStep"] if inst and symbol in inst else "0.001"
        qty_str = self._format_step(qty_to_close, step, round_down=True)

        if float(qty_str) <= 0:
            return

        resp = bybit_client.place_order(
            symbol=symbol, side=side, order_type="Market",
            qty=qty_str, reduce_only=True
        )
        if resp and resp.get("retCode") == 0:
            ticker = bybit_client.get_tickers(symbol=symbol)
            exit_price = float(ticker[0]["lastPrice"]) if ticker else trade.entry_price
            pnl = (exit_price - trade.entry_price) * float(qty_str) if trade.side == "LONG" \
                  else (trade.entry_price - exit_price) * float(qty_str)
            await telegram_notifier.send_message(
                f"✅ <b>{reason}</b> | {symbol}\n"
                f"Cerrado {qty_str} @ {exit_price:.4f}\n"
                f"PnL parcial: <b>{pnl:+.2f} USDT</b>"
            )

    # ─── CIERRE FORZADO ───────────────────────────────────────────────────────

    async def _force_close_and_notify(self, trade, reason: str):
        symbol = trade.symbol
        side   = "Sell" if trade.side == "LONG" else "Buy"
        resp   = bybit_client.place_order(
            symbol=symbol, side=side, order_type="Market",
            qty=str(trade.qty), reduce_only=True
        )
        if resp and resp.get("retCode") == 0:
            ticker = bybit_client.get_tickers(symbol=symbol)
            exit_price = float(ticker[0]["lastPrice"]) if ticker else trade.entry_price
            pnl_usdt = (exit_price - trade.entry_price) * trade.qty if trade.side == "LONG" \
                       else (trade.entry_price - exit_price) * trade.qty
            pnl_pct  = (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage \
                       if (trade.entry_price * trade.qty) != 0 else 0
            db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)

            # Informar al estratega LRMC del resultado
            if pnl_usdt >= 0:
                lrmc_strategy.register_win()
            else:
                lrmc_strategy.register_loss()

            await telegram_notifier.send_message(
                f"🚨 <b>{reason}</b>\n{symbol}: cerrado @ {exit_price:.4f}\n"
                f"PnL: <b>{pnl_usdt:+.2f} USDT</b>"
            )
            # Limpiar estado
            self.trade_state.pop(trade.id, None)
            return True
        return False

    # ─── SINCRONIZACIÓN CON BYBIT ────────────────────────────────────────────

    async def _sync_closed_trade(self, trade, ticker_map: dict):
        """Trade ya no existe en Bybit → sincronizar DB."""
        symbol = trade.symbol
        ticker_info = ticker_map.get(symbol)
        exit_price  = float(ticker_info["lastPrice"]) if ticker_info else trade.entry_price

        open_time_ms = int(trade.open_time.replace(tzinfo=timezone.utc).timestamp() * 1000)
        pnl_data     = bybit_client.get_closed_pnl(symbol=symbol, limit=50, start_time=open_time_ms)

        if pnl_data and pnl_data.get("retCode") == 0 and pnl_data["result"]["list"]:
            pnl_usdt   = sum(float(i.get("closedPnl", 0)) for i in pnl_data["result"]["list"])
            exit_price = float(pnl_data["result"]["list"][0].get("avgExitPrice", exit_price))
            reason     = "Cerrada en Exchange (TP/SL)"
        else:
            pnl_usdt = (exit_price - trade.entry_price) * trade.qty if trade.side == "LONG" \
                       else (trade.entry_price - exit_price) * trade.qty
            # PnL directo — igual al exchange (fees ya incluidos en closedPnl de Bybit)
            reason    = "Cerrada (Sync)"

        pnl_pct = (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage \
                  if (trade.entry_price * trade.qty) != 0 else 0
        db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)

        if pnl_usdt >= 0:
            lrmc_strategy.register_win()
        else:
            lrmc_strategy.register_loss()

        self.trade_state.pop(trade.id, None)

    # ─── UTILIDADES ───────────────────────────────────────────────────────────

    async def force_sync_at_startup(self):
        await self.check_open_positions()

    async def emergency_close_all(self):
        bybit_client.session.cancel_all_orders(category="linear", settleCoin="USDT")
        active = bybit_client.get_active_positions()
        for p in active:
            side = "Sell" if p["side"] == "Buy" else "Buy"
            bybit_client.place_order(p["symbol"], side, "Market", p["size"], reduce_only=True)
        lrmc_strategy.unblock()
        self.trade_state.clear()
        await self.force_sync_at_startup()
        return True


executor = ExecutionEngine()
