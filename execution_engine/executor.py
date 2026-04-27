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

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self):
        self.last_report_count = -1

    def _format_step(self, value, step_string, round_down=False):
        try:
            step_dec = Decimal(str(step_string))
            val_dec = Decimal(str(value))
            if round_down:
                rounded = math.floor(val_dec / step_dec) * step_dec
            else:
                rounded = round(val_dec / step_dec) * step_dec
            decimals = abs(step_dec.as_tuple().exponent)
            return f"{float(rounded):.{decimals}f}"
        except:
            return f"{float(value):.4f}"

    async def try_execute_signal(self, signal_data):
        symbol = signal_data["symbol"]
        signal = signal_data["signal"]
        entry_price = signal_data["entry_price"]
        sl_price = signal_data["sl"]
        tp_price = signal_data["tp"] # Puede ser None para modo infinito

        active_positions = bybit_client.get_active_positions()
        open_count = len(active_positions)

        if open_count >= settings.MAX_CONCURRENT_TRADES:
            return False

        balance_info = bybit_client.get_wallet_balance()
        available_balance = 0.0
        if balance_info and balance_info.get("retCode") == 0:
            list_balances = balance_info["result"]["list"][0]["coin"]
            usdt_balance = next((item for item in list_balances if item["coin"] == "USDT"), None)
            if usdt_balance:
                available_balance = float(usdt_balance["walletBalance"])

        if not risk_manager.can_open_new_trade(open_count, available_balance):
            return False

        qty = risk_manager.calculate_position_size(entry_price)
        inst_info = bybit_client.get_instruments_info(symbol=symbol)
        
        if inst_info and symbol in inst_info:
            info = inst_info[symbol]
            qty_str = self._format_step(qty, info["qtyStep"], round_down=True)
            tp_str = self._format_step(tp_price, info["tickSize"]) if tp_price else "0"
            sl_str = self._format_step(sl_price, info["tickSize"])
        else:
            qty_str = f"{qty:.3f}"
            tp_str = f"{tp_price:.4f}" if tp_price else "0"
            sl_str = f"{sl_price:.4f}"

        if float(qty_str) <= 0: return False

        # Filtro de Funding
        funding = bybit_client.get_funding_rate(symbol)
        if signal == "LONG" and funding > 0.0001: return False
        if signal == "SHORT" and funding < -0.0001: return False

        bybit_client.set_leverage(symbol, settings.LEVERAGE)
        side = "Buy" if signal == "LONG" else "Sell"

        logger.info(f"🚀 EJECUTANDO {signal} | {symbol} | TP: {tp_str}")
        
        response = bybit_client.place_order(
            symbol=symbol, side=side, order_type="Limit",
            qty=qty_str, price=str(entry_price),
            take_profit=tp_str, stop_loss=sl_str
        )

        if response and response.get("retCode") == 0:
            risk_usdt = abs(entry_price - sl_price) * float(qty_str)
            db_manager.add_trade(
                symbol=symbol, side=signal, entry_price=entry_price,
                sl=sl_price, tp=tp_price or 0, qty=float(qty_str),
                leverage=settings.LEVERAGE, risk_usdt=risk_usdt
            )
            await telegram_notifier.notify_order_opened(
                symbol=symbol, side=signal, entry_price=f"{entry_price:.4f}",
                sl=f"{sl_price:.4f}", tp=tp_str, qty=qty_str,
                leverage=settings.LEVERAGE, current_trades=open_count + 1,
                max_trades=settings.MAX_CONCURRENT_TRADES, risk_usdt=f"{risk_usdt:.2f}"
            )
            return True
        return False

    async def _force_close_and_notify(self, trade, reason):
        symbol = trade.symbol
        side = "Sell" if trade.side == "LONG" else "Buy"
        resp = bybit_client.place_order(
            symbol=symbol, side=side, order_type="Market",
            qty=str(trade.qty), reduce_only=True
        )
        if resp and resp.get("retCode") == 0:
            ticker = bybit_client.get_tickers(symbol=symbol)
            exit_price = float(ticker[0]["lastPrice"]) if ticker else trade.entry_price
            pnl_usdt = (exit_price - trade.entry_price) * trade.qty if trade.side == "LONG" else (trade.entry_price - exit_price) * trade.qty
            pnl_pct = (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage
            db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
            await telegram_notifier.send_message(f"🚨 <b>{reason}</b>\n{symbol}: Cerrado a mercado.\nPnL: <b>{pnl_usdt:+.2f} USDT</b>")
            return True
        return False

    async def check_open_positions(self):
        open_trades = db_manager.get_open_trades()
        if not open_trades: return

        active_positions = bybit_client.get_active_positions()
        real_positions = {p["symbol"]: p for p in active_positions}

        tickers = bybit_client.get_tickers()
        ticker_map = {t["symbol"]: t for t in tickers} if tickers else {}

        for trade in open_trades:
            symbol = trade.symbol
            
            # 1. CIERRE POR TIEMPO (V9.1: 15 MINUTOS)
            now_utc = datetime.now(timezone.utc)
            ot_utc = trade.open_time.replace(tzinfo=timezone.utc)
            if (now_utc - ot_utc).total_seconds() > 900:
                await self._force_close_and_notify(trade, "TIME_EXIT")
                continue

            # 2. SINCRONIZACIÓN CON BYBIT (SL/TP TOCADOS)
            if symbol not in real_positions:
                ticker_info = ticker_map.get(symbol)
                exit_price = float(ticker_info["lastPrice"]) if ticker_info else trade.entry_price
                actual_pnl_data = bybit_client.get_closed_pnl(symbol=symbol, limit=1)
                
                if actual_pnl_data and actual_pnl_data.get("retCode") == 0 and actual_pnl_data["result"]["list"]:
                    real_pnl_item = actual_pnl_data["result"]["list"][0]
                    pnl_usdt = float(real_pnl_item.get("closedPnl", 0))
                    exit_price = float(real_pnl_item.get("avgExitPrice", exit_price))
                    reason = "BYBIT_SYNC"
                else:
                    pnl_usdt = (exit_price - trade.entry_price) * trade.qty if trade.side == "LONG" else (trade.entry_price - exit_price) * trade.qty
                    pnl_usdt -= (trade.entry_price * trade.qty) * 0.0011 # Fees
                    reason = "CERRADA"

                pnl_pct = (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage if (trade.entry_price * trade.qty) != 0 else 0
                db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
                continue

            # 3. GESTIÓN ACTIVA (BREAKEVEN+ Y TRAILING)
            pos = real_positions[symbol]
            cur_price = float(pos.get("markPrice", 0)) or float(ticker_map.get(symbol, {}).get("lastPrice", 0))
            if cur_price == 0: continue

            is_long = trade.side == "LONG"
            risk = abs(trade.entry_price - trade.stop_loss)
            if risk <= 0: continue

            target_tp = trade.take_profit if trade.take_profit > 0 else (trade.entry_price + risk * 4.4 if is_long else trade.entry_price - risk * 4.4)
            target_dist = abs(target_tp - trade.entry_price)
            current_profit_dist = (cur_price - trade.entry_price) if is_long else (trade.entry_price - cur_price)
            profit_pct = current_profit_dist / target_dist if target_dist > 0 else 0
            
            current_sl_bybit = float(pos.get("stopLoss", 0))
            new_sl = None

            # Breakeven+ al 60% -> Entrada + 0.15%
            if profit_pct >= 0.60:
                be_price = trade.entry_price * (1 + 0.0015) if is_long else trade.entry_price * (1 - 0.0015)
                if (is_long and current_sl_bybit < be_price) or (not is_long and (current_sl_bybit > be_price or current_sl_bybit == 0)):
                    new_sl = be_price

            # Trailing Stop al 85% -> Perseguir a 1.5 ATR
            if profit_pct >= 0.85:
                trail_sl = cur_price - risk * 1.5 if is_long else cur_price + risk * 1.5
                if is_long: new_sl = max(new_sl or 0, trail_sl, current_sl_bybit)
                else: new_sl = min(new_sl or 999999, trail_sl, current_sl_bybit if current_sl_bybit > 0 else 999999)

            if new_sl and abs(new_sl - current_sl_bybit) > (new_sl * 0.0005):
                inst = bybit_client.get_instruments_info(symbol=symbol)
                new_sl_str = self._format_step(new_sl, inst[symbol]["tickSize"]) if inst else f"{new_sl:.4f}"
                bybit_client.set_trading_stop(symbol, stop_loss=new_sl_str)

        # REPORTE CADA 10
        closed_count = db_manager.get_closed_trades_count()
        if closed_count > 0 and closed_count % 10 == 0 and closed_count != self.last_report_count:
            self.last_report_count = closed_count
            from analytics.analytics_manager import analytics_manager
            msg = analytics_manager.get_combined_periodic_report()
            if msg: await telegram_notifier.send_message(msg)

    async def force_sync_at_startup(self):
        await self.check_open_positions()

    async def emergency_close_all(self):
        bybit_client.session.cancel_all_orders(category="linear", settleCoin="USDT")
        active = bybit_client.get_active_positions()
        for p in active:
            bybit_client.place_order(p["symbol"], "Sell" if p["side"] == "Buy" else "Buy", "Market", p["size"], reduce_only=True)
        await self.force_sync_at_startup()
        return True

executor = ExecutionEngine()
