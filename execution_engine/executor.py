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
        self.last_report_count = -1  # Para evitar repetir el reporte de "10 trades"

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

        # Ajustar lote mínimo sugerido por Bybit mediante instruments_info
        instruments_info = bybit_client.get_instruments_info(symbol=symbol)
        qty_str = f"{qty:.3f}"
        tp_str = f"{tp_price:.4f}"
        sl_str = f"{sl_price:.4f}"

        if instruments_info and symbol in instruments_info:
            info = instruments_info[symbol]
            qty_str = self._format_step(qty, info["qtyStep"], round_down=True)
            tp_str = self._format_step(tp_price, info["tickSize"])
            sl_str = self._format_step(sl_price, info["tickSize"])

            # Additional safety check vs Bybit minimum order size
            min_qty = float(info.get("minOrderQty", "0"))
            if float(qty_str) < min_qty:
                logger.warning(
                    f"Omitiendo señal {symbol} - Cantidad {qty_str} es menor al mínimo de Bybit {min_qty}."
                )
                return False
        else:
            logger.warning(
                f"Info de instrumento no encontrada para {symbol}. Usando default_step 3 decimales."
            )
            qty_str = f"{qty:.3f}"
            tp_str = f"{tp_price:.4f}"
            sl_str = f"{sl_price:.4f}"

        if float(qty_str) <= 0:
            logger.warning(
                f"Omitiendo señal {symbol} - Cantidad muy pequeña tras ajustar a lote mínimo."
            )
            return False

        side = "Buy" if signal == "LONG" else "Sell"

        # 3.6 Filtro de Funding Rate Profesional
        funding = bybit_client.get_funding_rate(symbol)
        if signal == "LONG" and funding > 0.0001: # > 0.01%
             logger.warning(f"Omitiendo LONG en {symbol} - Funding demasiado alto: {funding:.6f}")
             return False
        if signal == "SHORT" and funding < -0.0001: # < -0.01%
             logger.warning(f"Omitiendo SHORT en {symbol} - Funding demasiado bajo: {funding:.6f}")
             return False

        # 3.7 Establecer Apalancamiento
        bybit_client.set_leverage(symbol, settings.LEVERAGE)

        logger.info(
            f"🚀 Ejecutando {signal} LIMIT en {symbol} | Qty: {qty_str} | Price: {entry_price:.4f}"
        )

        response = bybit_client.place_order(
            symbol=symbol,
            side=side,
            order_type="Limit",
            qty=qty_str,
            price=str(entry_price),
            take_profit=tp_str,
            stop_loss=sl_str,
        )

        if response and response.get("retCode") == 0:
            # 4. Guardar en Base de Datos
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

            # 5. Notificar a Telegram
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
            # Opcional: Notificar fallo crítico a Telegram
            await telegram_notifier.send_message(
                f"⚠️ <b>ERROR CRÍTICO</b>\nNo se pudo ejecutar {signal} en {symbol}\nError: {ret_msg}"
            )
            return False

    async def check_open_positions(self):
        """
        Revisa las posiciones abiertas en la BD y las sincroniza con Bybit para ver si tocaron SL o TP.
        Esta función también actúa como sincronizador: si la DB tiene trades OPEN que Bybit no tiene,
        los cierra automáticamente (trade cerrado por SL/TP mientras el bot no estaba corriendo).
        """
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            return

        logger.info(f"Monitorizando {len(open_trades)} operaciones abiertas...")

        # Obtenemos las posiciones reales de Bybit
        active_positions = bybit_client.get_active_positions()
        real_positions = {p["symbol"]: p for p in active_positions}

        if not active_positions and open_trades:
            logger.info(
                "Bybit no reporta posiciones abiertas, pero la DB sí. Forzando limpieza de trades fantasma..."
            )

        # Comparar nuestra BD con Bybit
        tickers = bybit_client.get_tickers()
        ticker_map = {t["symbol"]: t for t in tickers} if tickers else {}

        for trade in open_trades:
            symbol = trade.symbol

            # Si el trade está en nuestra DB pero NO en Bybit con size > 0, significa que se cerró (SL o TP tocado)
            if symbol not in real_positions:
                logger.info(
                    f"El trade {symbol} (ID:{trade.id}) ya no está activo en Bybit. Procesando cierre..."
                )

                ticker_info = ticker_map.get(symbol)
                if not ticker_info:
                    # Si no hay ticker, cerrar como "CERRADA" al último precio conocido (entry)
                    exit_price = trade.entry_price
                else:
                    exit_price = float(ticker_info["lastPrice"])

                # Intentar obtener PnL real desde Bybit para incluir comisiones
                actual_pnl_data = bybit_client.get_closed_pnl(symbol=symbol, limit=1)
                if actual_pnl_data and actual_pnl_data.get("retCode") == 0 and actual_pnl_data["result"]["list"]:
                    real_pnl_item = actual_pnl_data["result"]["list"][0]
                    pnl_usdt = float(real_pnl_item.get("closedPnl", 0))
                    exit_price = float(real_pnl_item.get("avgExitPrice", exit_price))
                else:
                    # Fallback a cálculo manual si Bybit no responde a tiempo
                    if trade.side == "LONG":
                        pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                    else:
                        pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                    
                    # Restar comisiones estimadas (0.11% total taker entry+exit)
                    fees_est = (trade.entry_price * trade.qty) * 0.0011
                    pnl_usdt -= fees_est

                pnl_pct = (
                    (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage
                    if (trade.entry_price * trade.qty) != 0
                    else 0.0
                )

                # Actualizar DB
                db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
                logger.info(
                    f"Trade {symbol} cerrado en DB. Razón: {reason} | PnL: {pnl_usdt:.2f} USDT"
                )

                # Consultar balance para Telegram
                balance_info = bybit_client.get_wallet_balance()
                current_balance = 0.0
                if balance_info and balance_info.get("retCode") == 0:
                    coin_list = balance_info["result"]["list"][0].get("coin", [])
                    usdt_info = next(
                        (c for c in coin_list if c["coin"] == "USDT"), None
                    )
                    if usdt_info:
                        current_balance = float(usdt_info["walletBalance"])

                # Notificar a Telegram
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

            # --- LÓGICA DE BREAKEVEN (NUEVO) ---
            elif symbol in real_positions:
                pos = real_positions[symbol]
                cur_price = float(pos.get("markPrice", 0)) or float(
                    ticker_map.get(symbol, {}).get("lastPrice", 0)
                )
                if cur_price == 0:
                    continue

                entry = float(pos.get("avgPrice", trade.entry_price))
                initial_sl = trade.stop_loss
                risk = abs(entry - initial_sl)

                # Si el riesgo es 0 o muy pequeño, evitar división por cero o lógica errónea
                if risk <= 0:
                    continue

                # Verificar si ya está en breakeven (o cerca) en Bybit
                current_sl_bybit = float(pos.get("stopLoss", 0))

                is_long = trade.side == "LONG"

                # Condición de Breakeven: Precio alcanzó 1.5:1 RR (más conservador)
                should_be_be = False
                if is_long:
                    if cur_price >= (entry + risk * 1.5) and current_sl_bybit < entry:
                        should_be_be = True
                else:  # SHORT
                    if cur_price <= (entry - risk * 1.5) and (
                        current_sl_bybit > entry or current_sl_bybit == 0
                    ):
                        should_be_be = True

                # SL mínimo = entrada + spread para cubrir comisiones (0.1%)
                min_profit = entry * settings.BREAKEVEN_SPREAD
                be_sl = entry + min_profit if is_long else entry - min_profit

                if should_be_be:
                    logger.info(
                        f"Protegiendo {symbol}: Precio alcanzó 1.5:1 RR. Moviendo SL a breakeven + spread ({be_sl:.4f})."
                    )

                    # Formatear el nuevo SL según el tickSize del instrumento
                target_dist = abs(trade.take_profit - trade.entry_price)
                current_profit_dist = (cur_price - trade.entry_price) if is_long else (trade.entry_price - cur_price)
                profit_pct_of_target = (current_profit_dist / target_dist) if target_dist > 0 else 0
                
                # Parametros de la foto: Breakeven al 60% -> +0.15%
                be_trigger = 0.60 
                be_offset_pct = 0.0015 # 0.15%
                
                new_sl = None
                
                # FASE 1: BREAKEVEN+
                if profit_pct_of_target >= be_trigger:
                    be_price = trade.entry_price * (1 + be_offset_pct) if is_long else trade.entry_price * (1 - be_offset_pct)
                    
                    # Solo mover si el SL actual es inferior (para long) o superior (para short) al BE
                    if is_long and (current_sl_bybit < be_price or current_sl_bybit == 0):
                        new_sl = be_price
                    elif not is_long and (current_sl_bybit > be_price or current_sl_bybit == 0):
                        new_sl = be_price

                # FASE 2: TRAILING STOP (Cuando supera el 85% del TP, perseguimos con ATR)
                if profit_pct_of_target >= 0.85:
                    atr_dist = risk * 1.5 # Usamos el risk (que es ATR) como base
                    trail_sl = cur_price - atr_dist if is_long else cur_price + atr_dist
                    
                    if is_long:
                        new_sl = max(new_sl or 0, trail_sl, current_sl_bybit)
                    else:
                        # Para short, queremos el más bajo
                        valid_current = current_sl_bybit if current_sl_bybit > 0 else 999999
                        new_sl = min(new_sl or 999999, trail_sl, valid_current)

                # EJECUTAR CAMBIO SI ES NECESARIO
                inst_info = bybit_client.get_instruments_info(symbol=symbol)
                if new_sl and abs(new_sl - current_sl_bybit) > (new_sl * 0.0005): # Evitar spam de mini-cambios
                    new_sl_str = self._format_step(new_sl, inst_info[symbol]["tickSize"]) if inst_info else f"{new_sl:.4f}"
                    resp = bybit_client.set_trading_stop(symbol, stop_loss=new_sl_str)
                    if resp and resp.get("retCode") == 0:
                        logger.info(f"PROTECCIÓN: {symbol} SL movido a {new_sl_str} (Target: {profit_pct_of_target:.1%})")
                        await telegram_notifier.send_message(f"🛡️ <b>PROTECCIÓN QUANT</b>\n{symbol}: SL ajustado a {new_sl_str}\nObjetivo alcanzado: {profit_pct_of_target:.1%}")

            # REPORTE CADA 10 OPERACIONES
            closed_count = db_manager.get_closed_trades_count()
            if (
                closed_count > 0
                and closed_count % 10 == 0
                and closed_count != self.last_report_count
            ):
                self.last_report_count = closed_count
                from analytics.analytics_manager import analytics_manager

                combined_report = analytics_manager.get_combined_periodic_report()
                if combined_report:
                    await telegram_notifier.send_message(combined_report)

    async def force_sync_at_startup(self):
        """
        Sincronización forzada al inicio del bot.
        Cierra en la DB local todos los trades marcados como OPEN que ya no existen en Bybit.
        Esto evita que trades 'fantasma' bloqueen nuevas operaciones al reiniciar el bot en Render.
        """
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            logger.info("Startup sync: No hay trades abiertos en DB. Todo limpio.")
            return

        logger.info(
            f"Startup sync: Verificando {len(open_trades)} trades en DB contra Bybit..."
        )
        positions_response = bybit_client.get_positions()

        real_positions = {}
        if positions_response and positions_response.get("retCode") == 0:
            for pos in positions_response["result"]["list"]:
                if float(pos["size"]) > 0:
                    real_positions[pos["symbol"]] = pos
        else:
            logger.warning(
                "Startup sync: No se pudo obtener posiciones de Bybit. Abortando sync."
            )
            return

        tickers = bybit_client.get_tickers()
        ticker_map = {t["symbol"]: t for t in tickers} if tickers else {}

        closed_count = 0
        for trade in open_trades:
            symbol = trade.symbol
            if symbol not in real_positions:
                ticker_info = ticker_map.get(symbol)
                exit_price = (
                    float(ticker_info["lastPrice"])
                    if ticker_info
                    else trade.entry_price
                )

                # Intentar obtener PnL real desde Bybit
                actual_pnl_data = bybit_client.get_closed_pnl(symbol=symbol, limit=1)
                if actual_pnl_data and actual_pnl_data.get("retCode") == 0 and actual_pnl_data["result"]["list"]:
                    real_pnl_item = actual_pnl_data["result"]["list"][0]
                    pnl_usdt = float(real_pnl_item.get("closedPnl", 0))
                    exit_price = float(real_pnl_item.get("avgExitPrice", exit_price))
                    reason = "BYBIT_SYNC"
                else:
                    if trade.side == "LONG":
                        pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                        reason = "TAKE PROFIT" if exit_price >= trade.take_profit else ("STOP LOSS" if exit_price <= trade.stop_loss else "SINCRONIZADA")
                    else:
                        pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                        reason = "TAKE PROFIT" if exit_price <= trade.take_profit else ("STOP LOSS" if exit_price >= trade.stop_loss else "SINCRONIZADA")
                    
                    # Restar comisiones estimadas
                    fees_est = (trade.entry_price * trade.qty) * 0.0011
                    pnl_usdt -= fees_est

                pnl_pct = (
                    (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage
                    if (trade.entry_price * trade.qty) != 0
                    else 0.0
                )
                db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
                logger.info(
                    f"Startup sync: Trade {symbol} (ID:{trade.id}) cerrado. Razón: {reason}"
                )
                closed_count += 1
            else:
                logger.info(f"Startup sync: Trade {symbol} sigue activo en Bybit. OK.")

        logger.info(
            f"Startup sync completado: {closed_count} trades fantasma eliminados de DB."
        )

    async def emergency_close_all(self):
        """
        BOTÓN DE PÁNICO: Cierra todas las posiciones y cancela todas las órdenes inmediatamente.
        """
        logger.warning("🚨 BOTÓN DE PÁNICO ACTIVADO: Iniciando cierre de emergencia...")

        # 1. Cancelar todas las órdenes abiertas
        bybit_client.session.cancel_all_orders(category="linear", settleCoin="USDT")
        logger.info("Panic: Todas las órdenes abiertas han sido canceladas.")

        # 2. Obtener posiciones activas
        pos_res = bybit_client.get_positions()
        if not pos_res or pos_res.get("retCode") != 0:
            logger.error("Panic: No se pudieron obtener las posiciones para cerrar.")
            return False

        active_positions = [
            p for p in pos_res["result"]["list"] if float(p["size"]) > 0
        ]

        # 3. Cerrar cada posición a mercado
        closed_count = 0
        for pos in active_positions:
            symbol = pos["symbol"]
            side = "Sell" if pos["side"] == "Buy" else "Buy"
            qty = pos["size"]

            logger.info(f"Panic: Cerrando posición en {symbol} ({qty} {pos['side']})")
            bybit_client.place_order(symbol, side, "Market", qty, reduce_only=True)
            closed_count += 1

        # 4. Sincronizar DB local
        self.force_sync_at_startup()  # Reutilizamos la lógica de sincronización para limpiar la DB

        logger.warning(f"🚨 Panic Complete: {closed_count} posiciones cerradas.")
        return True


executor = ExecutionEngine()
