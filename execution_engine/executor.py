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
        # Almacena el timestamp hasta el cual una moneda está bloqueada tras una pérdida
        self.symbol_cooldowns = {}

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
        
        # 0. Chequeo de Cooldown (V9.0)
        from datetime import datetime
        now = datetime.utcnow()
        if symbol in self.symbol_cooldowns:
            if now < self.symbol_cooldowns[symbol]:
                remaining = (self.symbol_cooldowns[symbol] - now).total_seconds() / 60
                logger.info(f"Omitiendo {symbol} - Moneda en COOLDOWN tras pérdida ({remaining:.1f} min)")
                return False
            else:
                # Cooldown expirado, limpiar
                del self.symbol_cooldowns[symbol]

        # 1. Chequeo de límites concurrentes REAL-TIME (API)
        positions_res = bybit_client.get_positions()
        real_open_count = 0
        if positions_res and positions_res.get('retCode') == 0:
            real_open_count = len([p for p in positions_res['result']['list'] if float(p['size']) > 0])
        
        db_count = db_manager.get_open_trades_count()
        
        if real_open_count >= settings.MAX_CONCURRENT_TRADES:
            logger.info(f"Omitiendo {symbol} - Límite Real alcanzado: {real_open_count}/{settings.MAX_CONCURRENT_TRADES}")
            return False

        # 2. Chequeo de capital en Bybit
        # MODO RESILIENTE: Si hay un error 401 (No autorizado) o el balance falla, 
        # asumimos un balance de respaldo para no bloquear la operación.
        balance_info = bybit_client.get_wallet_balance()
        available_balance = 0.0
        fallback_used = False
        
        if balance_info and balance_info.get('retCode') == 0:
             try:
                 list_balances = balance_info['result']['list'][0]['coin']
                 usdt_balance = next((item for item in list_balances if item['coin'] == 'USDT'), None)
                 if usdt_balance:
                     available_balance = float(usdt_balance['walletBalance'])
             except Exception as e:
                 logger.warning(f"Error parseando balance, usando respaldo: {e}")
                 available_balance = 1000.0
                 fallback_used = True
        else:
            logger.warning(f"⚠️ Error de API Bybit (Balance): {balance_info}. Activando MODO RESILIENTE (Balance de respaldo $1000).")
            available_balance = 1000.0
            fallback_used = True
                 
        # Forzamos los parámetros autónomos: $20 de margen y 10x
        fixed_margin = 20.0 
        leverage = 10 
        required_margin = fixed_margin * 1.1 # Buffer del 10%
        
        if available_balance < required_margin and not fallback_used:
            logger.warning(f"Omitiendo {symbol} - Balance insuficiente real ({available_balance:.2f} < {required_margin})")
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
        
        # 3.4 Notificación Inmediata de Señal (ALERTA)
        await telegram_notifier.notify_signal_detected(
            symbol=symbol, side=signal, entry_price=f"{entry_price:.4f}",
            sl=f"{sl_price:.4f}", tp=f"{tp_price:.4f}"
        )
        
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
            
            from utils.ui_utils import send_log, refresh_ui
            send_log(f"🚀 POSICIÓN ABIERTA: {symbol} ({signal}) a {entry_price:.4f}", "log-success")
            refresh_ui()
            
            await telegram_notifier.notify_order_opened(
                symbol=symbol, side=signal, entry_price=f"{entry_price:.4f}",
                sl=sl_price, tp=tp_price, qty=qty_str, leverage=leverage,
                current_trades=real_open_count + 1, max_trades=settings.MAX_CONCURRENT_TRADES,
                risk_usdt=f"{risk_usdt:.2f}",
                margin=fixed_margin
            )
            return True
        else:
            from utils.ui_utils import send_log
            send_log(f"❌ Error al abrir {symbol}: {response.get('retMsg', 'Unknown')}", "log-error")
            ret_code = response.get("retCode") if response else "Unknown"
            if ret_code == 10003:
                await telegram_notifier.notify_api_error(
                    "API Key Inválida (10003)",
                    "Asegúrate de que las llaves correspondan al entorno (Demo/Real)."
                )
            elif response and "401" in str(response):
                await telegram_notifier.notify_api_error(
                    "Error 401 (No Autorizado)",
                    "Las llaves no tienen permisos o el entorno BYBIT_DEMO es incorrecto."
                )
            return False

    async def check_open_positions(self):
        """
        Monitoriza trades abiertos y reporta estadísticas cada 10 trades.
        """
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            return
            
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        
        positions_response = bybit_client.get_positions()
        real_positions = {}
        if positions_response and positions_response.get('retCode') == 0:
            for pos in positions_response['result']['list']:
                if float(pos['size']) > 0:
                    real_positions[pos['symbol']] = pos

        # Emitir actualización completa a la UI (Posiciones, Historial, Stats)
        from utils.ui_utils import refresh_ui
        refresh_ui()

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
                
                # --- APLICAR COOLDOWN SI ES PÉRDIDA (V9.0) ---
                if pnl_usdt < 0:
                    from datetime import timedelta
                    self.symbol_cooldowns[symbol] = datetime.utcnow() + timedelta(minutes=30)
                    logger.info(f"❄️ {symbol} en COOLDOWN de 30 min tras pérdida.")

                from utils.ui_utils import send_log, refresh_ui
                msg_close = "💰 GAIN" if pnl_usdt > 0 else "🩸 LOSS"
                send_log(f"🏁 TRADE CERRADO: {symbol} | {msg_close} | PnL: {pnl_usdt:.2f}$ ({pnl_pct:.2f}%)", "log-success" if pnl_usdt > 0 else "log-error")
                refresh_ui()

                balance_info = bybit_client.get_wallet_balance()
                current_balance = float(balance_info['result']['list'][0]['coin'][0]['walletBalance']) if balance_info else 0.0
                
                await telegram_notifier.notify_order_closed(
                    symbol=symbol, side=trade.side, entry_price=f"{trade.entry_price:.4f}",
                    exit_price=f"{exit_price:.4f}", pnl_usdt=pnl_usdt, pnl_pct=pnl_pct,
                    duration=f"{duration.total_seconds()/60:.1f} min", reason=reason, balance=current_balance
                )
            else:
                # El trade sigue abierto, verificar Breakeven
                pos = real_positions[symbol]
                current_price = float(pos['markPrice'])
                
                # Definir 50% del camino al TP
                tp_dist = abs(trade.take_profit - trade.entry_price)
                progress = abs(current_price - trade.entry_price) / tp_dist if tp_dist > 0 else 0
                
                # Si llegamos al 60% del camino y no hemos movido el SL
                if progress > 0.6 and not getattr(trade, 'breakeven_active', False):
                    # Solo mover si estamos en ganancia
                    is_profit = (trade.side == "LONG" and current_price > trade.entry_price) or \
                                (trade.side == "SHORT" and current_price < trade.entry_price)
                    
                    if is_profit:
                        logger.info(f"🛡️ Protegiendo {symbol} - Moviendo a BREAKEVEN (Progreso: {progress:.1%})")
                        res = bybit_client.set_trading_stop(symbol, stop_loss=trade.entry_price)
                        if res and res.get('retCode') == 0:
                            trade.breakeven_active = True
                            from dashboard.app import send_log
                            send_log(f"🛡️ {symbol}: Moviendo SL a BREAKEVEN para proteger.", "log-warning")
                            # Notificar con el nuevo diseño
                            await telegram_notifier.notify_breakeven(symbol, trade.entry_price)

                # --- Verificación de Reporte Estadístico (Cada 10 trades) ---
                closed_count = db_manager.get_closed_trades_count()
                if closed_count > 0 and closed_count % 10 == 0:
                    daily = db_manager.get_stats("daily")
                    weekly = db_manager.get_stats("weekly")
                    monthly = db_manager.get_stats("monthly")
                    await telegram_notifier.notify_stats_summary(daily, weekly, monthly, closed_count)

executor = ExecutionEngine()
