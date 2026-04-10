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

        # 1. Chequeo de límites concurrentes (USANDO DATA EN VIVO DE BYBIT)
        active_positions = bybit_client.get_active_positions()
        open_count = len(active_positions)

        if open_count >= settings.MAX_CONCURRENT_TRADES:
            logger.info(
                f"Omitiendo señal {symbol} - Límite de trades abierto alcanzado en Bybit ({open_count})."
            )
            return False

        # Sincronizar conteo con DB por si acaso (opcional pero recomendado)
        db_count = db_manager.get_open_trades_count()
        if db_count > open_count:
            logger.warning(
                f"Discrepancia detectada: DB dice {db_count} trades, Bybit dice {open_count}. Priorizando Bybit."
            )

        # 2. Chequeo de capital en Bybit
        balance_info = bybit_client.get_wallet_balance()
        available_balance = 0.0
        if balance_info and balance_info.get("retCode") == 0:
            list_balances = balance_info["result"]["list"][0]["coin"]
            usdt_balance = next(
                (item for item in list_balances if item["coin"] == "USDT"), None
            )
            if usdt_balance:
                available_balance = float(usdt_balance["walletBalance"])

        if not risk_manager.can_open_new_trade(open_count, available_balance):
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

        # 3.5 Establecer Apalancamiento para la moneda antes de la primera orden
        bybit_client.set_leverage(symbol, settings.LEVERAGE)

        logger.info(
            f"🚀 Ejecutando {signal} en {symbol} | Qty: {qty_str} | SL: {sl_str} | TP: {tp_str}"
        )

        response = bybit_client.place_order(
            symbol=symbol,
            side=side,
            order_type="Market",  # Entramos Market porque la vela ya cerró confirmando señal
            qty=qty_str,
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

                # Aproximación de pnl (LONG vs SHORT)
                if trade.side == "LONG":
                    pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                    reason = (
                        "TAKE PROFIT"
                        if exit_price >= trade.take_profit
                        else (
                            "STOP LOSS"
                            if exit_price <= trade.stop_loss
                            else "SINCRONIZADA"
                        )
                    )
                else:
                    pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                    reason = (
                        "TAKE PROFIT"
                        if exit_price <= trade.take_profit
                        else (
                            "STOP LOSS"
                            if exit_price >= trade.stop_loss
                            else "SINCRONIZADA"
                        )
                    )

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

                if should_be_be:
                    # SL mínimo = entrada + spread para cubrir comisiones (0.1%)
                    min_profit = entry * settings.BREAKEVEN_SPREAD
                    be_sl = entry + min_profit if is_long else entry - min_profit

                    logger.info(
                        f"Protegiendo {symbol}: Precio alcanzó 1.5:1 RR. Moviendo SL a breakeven + spread ({be_sl:.4f})."
                    )

                    # Formatear el nuevo SL según el tickSize del instrumento
                    inst_info = bybit_client.get_instruments_info(symbol=symbol)
                    if inst_info and symbol in inst_info:
                        new_sl_str = self._format_step(
                            be_sl, inst_info[symbol]["tickSize"]
                        )
                    else:
                        new_sl_str = f"{be_sl:.4f}"

                    resp = bybit_client.set_trading_stop(symbol, stop_loss=new_sl_str)
                    if resp and resp.get("retCode") == 0:
                        await telegram_notifier.send_message(
                            f"🛡️ <b>BREAKEVEN ACTIVADO</b>\n{symbol}: SL → {new_sl_str} (+{min_profit:.2f} profit mínimo para comisiones)"
                        )
                    else:
                        logger.error(f"Error al aplicar Breakeven en {symbol}: {resp}")

                # --- LÓGICA DE TRAILING STOP ESTRUCTURAL ---
                elif (
                    is_long
                    and current_sl_bybit >= be_sl
                    and cur_price >= (entry + risk * 2.5)
                ):
                    # Buscar el último fractal alcista cercano para mover el SL
                    df = await bybit_client.get_klines_async(
                        symbol=symbol, interval="15", limit=20
                    )
                    if df and df.get("result") and df["result"]["list"]:
                        # Convertir a DF y buscar el último Low Fractal
                        prices = [
                            float(x[3]) for x in df["result"]["list"][::-1]
                        ]  # Lows
                        new_structural_sl = min(
                            prices[:5]
                        )  # Mínimo de las últimas 5 velas 15m
                        if new_structural_sl > current_sl_bybit:
                            new_sl_str = (
                                self._format_step(
                                    new_structural_sl, inst_info[symbol]["tickSize"]
                                )
                                if inst_info
                                else f"{new_structural_sl:.4f}"
                            )
                            resp = bybit_client.set_trading_stop(
                                symbol, stop_loss=new_sl_str
                            )
                            if resp and resp.get("retCode") == 0:
                                await telegram_notifier.send_message(
                                    f"📈 <b>TRAILING ESTRUCTURAL</b>\nProtegiendo beneficios en <b>{symbol}</b>. Nuevo SL: {new_sl_str}"
                                )

                elif (
                    not is_long
                    and current_sl_bybit <= be_sl
                    and current_sl_bybit > 0
                    and cur_price <= (entry - risk * 2.5)
                ):
                    df = await bybit_client.get_klines_async(
                        symbol=symbol, interval="15", limit=20
                    )
                    if df and df.get("result") and df["result"]["list"]:
                        prices = [
                            float(x[2]) for x in df["result"]["list"][::-1]
                        ]  # Highs
                        new_structural_sl = max(
                            prices[:5]
                        )  # Máximo de las últimas 5 velas
                        if new_structural_sl < current_sl_bybit:
                            new_sl_str = (
                                self._format_step(
                                    new_structural_sl, inst_info[symbol]["tickSize"]
                                )
                                if inst_info
                                else f"{new_structural_sl:.4f}"
                            )
                            resp = bybit_client.set_trading_stop(
                                symbol, stop_loss=new_sl_str
                            )
                            if resp and resp.get("retCode") == 0:
                                await telegram_notifier.send_message(
                                    f"📉 <b>TRAILING ESTRUCTURAL</b>\nProtegiendo beneficios en <b>{symbol}</b>. Nuevo SL: {new_sl_str}"
                                )

            # REPORTE CADA 10 OPERACIONES (Enviamos el pack completo: Diario, Semanal y Mensual)
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

                if trade.side == "LONG":
                    pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                    reason = (
                        "TAKE PROFIT"
                        if exit_price >= trade.take_profit
                        else (
                            "STOP LOSS"
                            if exit_price <= trade.stop_loss
                            else "SINCRONIZADA"
                        )
                    )
                else:
                    pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                    reason = (
                        "TAKE PROFIT"
                        if exit_price <= trade.take_profit
                        else (
                            "STOP LOSS"
                            if exit_price >= trade.stop_loss
                            else "SINCRONIZADA"
                        )
                    )

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
