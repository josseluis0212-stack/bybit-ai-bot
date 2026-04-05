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
        """
        Intenta transformar una señal de la estrategia en una orden real,
        pasando primero por los filtros de riesgo.
        """
        symbol = signal_data['symbol']
        signal = signal_data['signal']
        entry_price = signal_data['entry_price']
        sl_price = signal_data['sl']
        tp_price = signal_data['tp']
        
        # 1. Chequeo de límites concurrentes
        open_count = db_manager.get_open_trades_count()
        if open_count >= settings.MAX_CONCURRENT_TRADES:
            logger.info(f"Omitiendo señal {symbol} - Límite de trades abiertos ({settings.MAX_CONCURRENT_TRADES}) alcanzado.")
            return False

        # 2. Chequeo de capital en Bybit
        balance_info = bybit_client.get_wallet_balance()
        available_balance = 0.0
        if balance_info and balance_info.get('retCode') == 0:
             list_balances = balance_info['result']['list'][0]['coin']
             usdt_balance = next((item for item in list_balances if item['coin'] == 'USDT'), None)
             if usdt_balance:
                 available_balance = float(usdt_balance['walletBalance'])
                 
        # Forzamos los parámetros autónomos: $50 de margen y 10x
        fixed_margin = 50.0 
        leverage = 10 
        required_margin = fixed_margin * 1.1 # Buffer del 10%
        
        if available_balance < required_margin:
            logger.warning(f"Omitiendo {symbol} - Balance insuficiente ({available_balance:.2f} < {required_margin})")
            return False

        # 3. Calcular cantidad para una posición de $500 nocional ($50 * 10)
        notional_value = fixed_margin * leverage
        qty = notional_value / entry_price
        
        # Ajustar lote mínimo
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
                logger.warning(f"Omitiendo {symbol} - Cantidad {qty_str} < Mínimo {min_qty}")
                return False
        
        if float(qty_str) <= 0:
            return False

        side = "Buy" if signal == "LONG" else "Sell"
        
        # 3.5 Establecer Apalancamiento Fijo 10x
        bybit_client.set_leverage(symbol, leverage)
        
        logger.info(f"🚀 [AUTÓNOMO] Ejecutando {signal} en {symbol} | Notion: ${notional_value} | Margin: ${fixed_margin}")
        
        response = bybit_client.place_order(
            symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty_str,
            take_profit=tp_str,
            stop_loss=sl_str
        )

        if response and response.get("retCode") == 0:
            risk_usdt = abs(entry_price - sl_price) * float(qty_str)
            db_manager.add_trade(
                symbol=symbol, side=signal, entry_price=entry_price,
                sl=sl_price, tp=tp_price, qty=float(qty_str),
                leverage=leverage, risk_usdt=risk_usdt
            )
            
            await telegram_notifier.notify_order_opened(
                symbol=symbol, side=signal, entry_price=f"{entry_price:.4f}",
                sl=sl_price, tp=tp_price, qty=qty_str, leverage=leverage,
                current_trades=open_count + 1, max_trades=settings.MAX_CONCURRENT_TRADES,
                risk_usdt=f"{risk_usdt:.2f}"
            )
            return True
        return False

    async def check_open_positions(self):
        """
        Monitoriza trades abiertos y reporta estadísticas cada 10 trades.
        """
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            return
            
        from datetime import datetime
        now = datetime.utcnow()
        
        positions_response = bybit_client.get_positions()
        real_positions = {}
        if positions_response and positions_response.get('retCode') == 0:
            for pos in positions_response['result']['list']:
                if float(pos['size']) > 0:
                    real_positions[pos['symbol']] = pos

        for trade in open_trades:
            symbol = trade.symbol
            
            # Si el símbolo ya no está en las posiciones reales, significa que se cerró por TP/SL
            if symbol not in real_positions:
                duration = now - trade.open_time
                logger.info(f"Trade {symbol} cerrado por Bybit (TP/SL/Manual).")
                tickers = bybit_client.get_tickers()
                ticker_info = next((t for t in tickers if t['symbol'] == symbol), None)
                if not ticker_info: continue
                
                exit_price = float(ticker_info['lastPrice'])
                if trade.side == "LONG":
                    pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                    reason = "TAKE PROFIT" if exit_price >= (trade.take_profit or 0) else ("STOP LOSS" if exit_price <= (trade.stop_loss or 0) else "CERRADA")
                else:
                    pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                    reason = "TAKE PROFIT" if exit_price <= (trade.take_profit or 0) else ("STOP LOSS" if exit_price >= (trade.stop_loss or 0) else "CERRADA")
                
                pnl_pct = (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage
                db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
                
                balance_info = bybit_client.get_wallet_balance()
                current_balance = float(balance_info['result']['list'][0]['coin'][0]['walletBalance']) if balance_info else 0.0
                
                await telegram_notifier.notify_order_closed(
                    symbol=symbol, side=trade.side, entry_price=f"{trade.entry_price:.4f}",
                    exit_price=f"{exit_price:.4f}", pnl_usdt=pnl_usdt, pnl_pct=pnl_pct,
                    duration=f"{duration.total_seconds()/60:.1f} min", reason=reason, balance=current_balance
                )

                # --- Verificación de Reporte Estadístico (Cada 10 trades) ---
                closed_count = db_manager.get_closed_trades_count()
                if closed_count > 0 and closed_count % 10 == 0:
                    daily = db_manager.get_stats("daily")
                    weekly = db_manager.get_stats("weekly")
                    monthly = db_manager.get_stats("monthly")
                    await telegram_notifier.notify_stats_summary(daily, weekly, monthly, closed_count)

executor = ExecutionEngine()
