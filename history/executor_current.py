"""
Execution Engine - Configuración Actual
=========================================

Características:
- Máximo 10 operaciones simultáneas
- Margen $20, Apalancamiento 10x
- Chequeo de límites en tiempo real via API
- Cooldown de 30min tras pérdida
- Break-even a 1.5:1 RR
- Trailing stop estructural
- Sincronización al inicio

"""

import logging
import asyncio
import math
from decimal import Decimal
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
        step_dec = Decimal(str(step_string))
        val_dec = Decimal(str(value))
        if round_down:
            rounded = math.floor(val_dec / step_dec) * step_dec
        else:
            rounded = round(val_dec / step_dec) * step_dec

        decimals = abs(step_dec.as_tuple().exponent)
        return f"{float(rounded):.{decimals}f}"

    async def try_execute_signal(self, signal_data):
        symbol = signal_data["symbol"]
        signal = signal_data["signal"]
        entry_price = signal_data["entry_price"]
        sl_price = signal_data["sl"]
        tp_price = signal_data["tp"]

        # 1. Chequeo de límites concurrentes
        active_positions = bybit_client.get_active_positions()
        open_count = len(active_positions)

        logger.info(f"[EJECUTOR] {symbol} - Posiciones abiertas: {open_count}/10")

        if open_count >= settings.MAX_CONCURRENT_TRADES:
            logger.info(f"Omitiendo {symbol} - Límite máximo ({open_count}).")
            return False

        # 2. Chequeo de capital
        balance_info = bybit_client.get_wallet_balance()
        available_balance = 0.0
        if balance_info and balance_info.get("retCode") == 0:
            list_balances = balance_info["result"]["list"][0]["coin"]
            usdt_balance = next(
                (item for item in list_balances if item["coin"] == "USDT"), None
            )
            if usdt_balance:
                available_balance = float(usdt_balance["walletBalance"])

        logger.info(f"[EJECUTOR] {symbol} - Balance: {available_balance:.2f} USDT")

        if not risk_manager.can_open_new_trade(open_count, available_balance):
            logger.info(
                f"Omitiendo {symbol} - Balance insuficiente ({available_balance:.2f} USDT)"
            )
            return False

        # 3. Calcular cantidad e instruir la orden
        qty = risk_manager.calculate_position_size(entry_price)

        instruments_info = bybit_client.get_instruments_info(symbol=symbol)
        qty_str = f"{qty:.3f}"
        tp_str = f"{tp_price:.4f}"
        sl_str = f"{sl_price:.4f}"

        if instruments_info and symbol in instruments_info:
            info = instruments_info[symbol]
            qty_str = self._format_step(qty, info["qtyStep"], round_down=True)
            tp_str = self._format_step(tp_price, info["tickSize"])
            sl_str = self._format_step(sl_price, info["tickSize"])

            min_qty = float(info.get("minOrderQty", "0"))
            if float(qty_str) < min_qty:
                logger.warning(
                    f"Omitiendo señal {symbol} - Cantidad {qty_str} es menor al mínimo de Bybit {min_qty}."
                )
                return False

        if float(qty_str) <= 0:
            return False

        side = "Buy" if signal == "LONG" else "Sell"

        bybit_client.set_leverage(symbol, settings.LEVERAGE)

        logger.info(
            f"🚀 Ejecutando {signal} en {symbol} | Qty: {qty_str} | SL: {sl_str} | TP: {tp_str}"
        )

        response = bybit_client.place_order(
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty_str,
            take_profit=tp_str,
            stop_loss=sl_str,
        )

        if response and response.get("retCode") == 0:
            risk_usdt = abs(entry_price - sl_price) * float(qty_str)
            db_manager.add_trade(
                symbol=symbol,
                side=signal,
                entry_price=entry_price,
                sl=sl_price,
                tp=tp_price,
                qty=float(qty_str),
                leverage=settings.LEVERAGE,
                risk_usdt=risk_usdt,
            )

            await telegram_notifier.notify_order_opened(
                symbol=symbol,
                side=signal,
                entry_price=f"{entry_price:.4f}",
                sl=f"{sl_price:.4f}",
                tp=f"{tp_price:.4f}",
                qty=qty_str,
                leverage=settings.LEVERAGE,
                current_trades=open_count + 1,
                max_trades=settings.MAX_CONCURRENT_TRADES,
                risk_usdt=f"{risk_usdt:.2f}",
            )
            return True
        else:
            ret_msg = response.get("retMsg") if response else "Sin respuesta"
            ret_code = response.get("retCode") if response else "N/A"
            logger.error(
                f"❌ Fallo al ejecutar orden en {symbol}: [{ret_code}] {ret_msg}"
            )
            return False

    async def check_open_positions(self):
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            return

        logger.info(f"Monitorizando {len(open_trades)} operaciones abiertas...")

        active_positions = bybit_client.get_active_positions()
        real_positions = {p["symbol"]: p for p in active_positions}

        tickers = bybit_client.get_tickers()
        ticker_map = {t["symbol"]: t for t in tickers} if tickers else {}

        for trade in open_trades:
            symbol = trade.symbol

            if symbol not in real_positions:
                ticker_info = ticker_map.get(symbol)
                exit_price = trade.entry_price if not ticker_info else float(ticker_info["lastPrice"])

                if trade.side == "LONG":
                    pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                    reason = (
                        "TAKE PROFIT" if exit_price >= trade.take_profit
                        else ("STOP LOSS" if exit_price <= trade.stop_loss else "SINCRONIZADA")
                    )
                else:
                    pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                    reason = (
                        "TAKE PROFIT" if exit_price <= trade.take_profit
                        else ("STOP LOSS" if exit_price >= trade.stop_loss else "SINCRONIZADA")
                    )

                pnl_pct = ((pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage) if (trade.entry_price * trade.qty) != 0 else 0.0

                db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
                logger.info(f"Trade {symbol} cerrado en DB. Razón: {reason} | PnL: {pnl_usdt:.2f} USDT")

                balance_info = bybit_client.get_wallet_balance()
                current_balance = 0.0
                if balance_info and balance_info.get("retCode") == 0:
                    coin_list = balance_info["result"]["list"][0].get("coin", [])
                    usdt_info = next((c for c in coin_list if c["coin"] == "USDT"), None)
                    if usdt_info:
                        current_balance = float(usdt_info["walletBalance"])

                await telegram_notifier.notify_order_closed(
                    symbol=symbol,
                    side=trade.side,
                    entry_price=f"{trade.entry_price:.4f}",
                    exit_price=f"{exit_price:.4f}",
                    pnl_usdt=pnl_usdt,
                    pnl_pct=pnl_pct,
                    duration="N/A",
                    reason=reason,
                    balance=current_balance,
                )

    async def force_sync_at_startup(self):
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            logger.info("Startup sync: No hay trades abiertos en DB.")
            return

        logger.info(f"Startup sync: Verificando {len(open_trades)} trades en DB contra Bybit...")
        positions_response = bybit_client.get_positions()

        real_positions = {}
        if positions_response and positions_response.get("retCode") == 0:
            for pos in positions_response["result"]["list"]:
                if float(pos["size"]) > 0:
                    real_positions[pos["symbol"]] = pos

        tickers = bybit_client.get_tickers()
        ticker_map = {t["symbol"]: t for t in tickers} if tickers else {}

        closed_count = 0
        for trade in open_trades:
            symbol = trade.symbol
            if symbol not in real_positions:
                ticker_info = ticker_map.get(symbol)
                exit_price = float(ticker_info["lastPrice"]) if ticker_info else trade.entry_price

                if trade.side == "LONG":
                    pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                    reason = "TAKE PROFIT" if exit_price >= trade.take_profit else ("STOP LOSS" if exit_price <= trade.stop_loss else "SINCRONIZADA")
                else:
                    pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                    reason = "TAKE PROFIT" if exit_price <= trade.take_profit else ("STOP LOSS" if exit_price >= trade.stop_loss else "SINCRONIZADA")

                pnl_pct = ((pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage) if (trade.entry_price * trade.qty) != 0 else 0.0
                db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
                closed_count += 1

        logger.info(f"Startup sync completado: {closed_count} trades eliminados.")

    async def emergency_close_all(self):
        logger.warning("🚨 BOTÓN DE PÁNICO ACTIVADO")
        bybit_client.session.cancel_all_orders(category="linear", settleCoin="USDT")
        
        pos_res = bybit_client.get_positions()
        if not pos_res or pos_res.get("retCode") != 0:
            return False

        active_positions = [p for p in pos_res["result"]["list"] if float(p["size"]) > 0]

        for pos in active_positions:
            symbol = pos["symbol"]
            side = "Sell" if pos["side"] == "Buy" else "Buy"
            qty = pos["size"]
            bybit_client.place_order(symbol, side, "Market", qty, reduce_only=True)

        await self.force_sync_at_startup()
        logger.warning(f"🚨 Panic Complete: {len(active_positions)} posiciones cerradas.")
        return True


executor = ExecutionEngine()
