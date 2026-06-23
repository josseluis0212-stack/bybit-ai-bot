import asyncio
import time
from app.logger import logger
from app.exchange.bybit_client import AsyncBybitClient
from app.database import crud
from app.exchange.order_executor import OrderExecutor

class ExchangeSynchronizer:
    """
    Supervisa cada 5 segundos que:
    - Órdenes límite pendientes no superen 15 minutos (las cancela si expiran).
    - Condición de Breakeven (40% hacia TP2) se activa correctamente.
    - La posición siga existiendo (si se cerró por SL/TP, actualiza DB y limpia memoria).
    - El Stop Loss real en el exchange coincida con el estado en memoria.
    Si un SL fue borrado accidentalmente, lo re-crea automáticamente para estar siempre protegido.
    """
    def __init__(self, engine):
        self.engine = engine
        self.client = AsyncBybitClient()
        self.executor = OrderExecutor()
        self.running = False

    async def start(self):
        self.running = True
        logger.info("🦸‍♂️ [SUPER SUPERVISOR] Inicializado. Vigilancia estricta de Timeout/SL/TP/BE/Trailing activada.")
        await self._patrol()

    async def _patrol(self):
        backoff_time = 2
        max_backoff = 60
        while self.running:
            await asyncio.sleep(5)  # Patrulla estricta cada 5 segundos
            try:
                active_symbols = list(self.engine.trade_state.keys())
                if not active_symbols:
                    continue

                for symbol in active_symbols:
                    trade = self.engine.trade_state.get(symbol)
                    if not trade: continue

                    # ─────────────────────────────────────────────────────
                    # CHECK 0: TIMEOUT DE 15 MINUTOS PARA ÓRDENES SIN LLENAR
                    # ─────────────────────────────────────────────────────
                    if not trade.get("filled"):
                        # Parche Anti-Ghost: Verificar si ByBit ya la llenó pero el WS no avisó
                        pos = await self.executor.verify_position_exists(symbol, trade["side"])
                        if pos:
                            logger.info(f"✅ [SUPER SUPERVISOR] ¡Ghost Fill detectado! {symbol} se llenó en ByBit (WS lag). Activando protecciones...")
                            trade["filled"] = True
                            trade["remaining_size"] = abs(float(pos.get("positionAmt", 0)))
                            await self.engine._place_protections(symbol, trade)
                            # Continuamos con el resto de verificaciones para protegerla
                        else:
                            timeout = trade.get("entry_timeout", 0)
                            if timeout > 0 and time.time() > timeout:
                                logger.warning(f"⏰ [TIMEOUT] {symbol} no llenó en 15 min. Cancelando orden límite...")
                                await self.client.cancel_all_orders(symbol)
                                self.engine.trade_state.pop(symbol, None)
                                logger.info(f"🚫 [TIMEOUT] {symbol} eliminada. Cooldown 1h aplicado.")
                                self.engine.cooldowns[symbol] = time.time() + 3600
                                continue
                            else:
                                remaining = max(0, (timeout - time.time()) / 60)
                                logger.info(f"⏳ [PENDING] {symbol} esperando llenado. Timeout en {remaining:.1f} min.")
                                continue

                    # ─────────────────────────────────────────────────────
                    # CHECK 1: ¿LA POSICIÓN SIGUE EXISTIENDO EN BYBIT?
                    # ─────────────────────────────────────────────────────
                    pos = await self.executor.verify_position_exists(symbol, trade["side"])
                    if not pos:
                        logger.info(f"🦸‍♂️ [SUPER SUPERVISOR] La posición {symbol} ya NO existe en el Exchange. Limpiando...")
                        await self.engine._close_position_internal(symbol, "Cerrada por SL/TP en Exchange")
                        continue
                        
                    real_size = abs(float(pos.get("positionAmt", 0)))
                    if abs(real_size - trade["remaining_size"]) > (trade["position_size"] * 0.01):
                        logger.warning(f"🦸‍♂️ [SUPER SUPERVISOR] Desfase volumen {symbol}. Memoria:{trade['remaining_size']:.4f} Bybit:{real_size:.4f}. Sincronizando...")
                        trade["remaining_size"] = real_size

                    # ─────────────────────────────────────────────────────
                    # CHECK 2: VERIFICAR CONDICIÓN DE BREAKEVEN ACTIVAMENTE
                    # ─────────────────────────────────────────────────────
                    if not trade.get("profit_lock_active"):
                        try:
                            ticker = await self.client.get_ticker(symbol)
                            mark_price = float(ticker.get("lastPrice", 0))
                            if mark_price > 0:
                                side = trade["side"]
                                entry_price = trade["entry_price"]
                                atr = trade["atr"]
                                
                                # BE se activa según la estrategia
                                if trade.get("strategy") == "AntigravityV13":
                                    from app.config import Config
                                    be_threshold = entry_price * (0.333 / Config.LEVERAGE)
                                else:
                                    be_threshold = atr * 2.0
                                    
                                be_triggered = (
                                    (side == "LONG" and mark_price >= entry_price + be_threshold) or
                                    (side == "SHORT" and mark_price <= entry_price - be_threshold)
                                )
                                if be_triggered:
                                    logger.info(f"🦸‍♂️ [SUPER SUPERVISOR→BE] Condición Breakeven detectada para {symbol} @ {mark_price:.4f}. Activando...")
                                    await self.engine._activate_profit_lock(symbol, trade)
                        except Exception as e:
                            logger.error(f"[SUPER SUPERVISOR BE CHECK] Error en {symbol}: {e}")

                    # ─────────────────────────────────────────────────────
                    # CHECK 3: AUDITAR ÓRDENES ABIERTAS Y LIMPIAR DUPLICADOS
                    # ─────────────────────────────────────────────────────
                    open_orders = await self.client.get_open_orders(symbol)
                    
                    found_sl = False
                    found_tp1 = False
                    found_tp2 = False
                    exchange_sl_price = 0.0
                    
                    # Contadores para duplicados
                    sl_orders = []
                    tp1_orders = []
                    tp2_orders = []

                    if open_orders:
                        for order in open_orders:
                            oid = str(order.get("orderId", ""))
                            stop_px = float(order.get("stopPrice", order.get("triggerPrice", 0)))
                            order_type = order.get("orderType", "").upper()
                            stop_order_type = order.get("stopOrderType", "").upper()
                            
                            is_conditional = stop_px > 0
                            
                            is_sl = False
                            is_tp = False
                            
                            if is_conditional:
                                # String-based identification
                                if "STOP" in order_type or "STOPLOSS" in stop_order_type:
                                    is_sl = True
                                elif "TAKE" in order_type or "TAKEPROFIT" in stop_order_type:
                                    is_tp = True
                                else:
                                    # Price-based inference for opaque conditional orders
                                    if trade.get("side") == "LONG":
                                        if stop_px < trade.get("entry_price", 0):
                                            is_sl = True
                                        else:
                                            is_tp = True
                                    elif trade.get("side") == "SHORT":
                                        if stop_px > trade.get("entry_price", float('inf')):
                                            is_sl = True
                                        else:
                                            is_tp = True
                                            
                            if is_sl:
                                sl_orders.append((oid, stop_px))
                            elif is_tp:
                                # Inferir si es TP1 o TP2 por cercanía al precio original
                                if trade.get("tp1_price") and abs(stop_px - trade["tp1_price"]) < (trade["atr"] * 0.5):
                                    tp1_orders.append((oid, stop_px))
                                elif trade.get("tp2_price") and abs(stop_px - trade["tp2_price"]) < (trade["atr"] * 0.5):
                                    tp2_orders.append((oid, stop_px))
                                    
                    # Limpiar Stop Loss Duplicados
                    if len(sl_orders) > 1:
                        logger.warning(f"🦸‍♂️ [SUPER SUPERVISOR] Detectados {len(sl_orders)} Stop Loss duplicados para {symbol}. Limpiando excedentes...")
                        for oid, _ in sl_orders[1:]:
                            await self.client.cancel_order(symbol, oid)
                        sl_orders = [sl_orders[0]] # Conservar uno para evitar loop de recreación

                    if len(sl_orders) == 1:
                        found_sl = True
                        trade["sl_order_id"] = sl_orders[0][0]
                        exchange_sl_price = sl_orders[0][1]

                    # Limpiar TP Duplicados
                    if len(tp1_orders) > 1:
                        logger.warning(f"🦸‍♂️ [SUPER SUPERVISOR] Detectados {len(tp1_orders)} TP1 duplicados para {symbol}. Limpiando...")
                        for oid, _ in tp1_orders: await self.client.cancel_order(symbol, oid)
                    elif len(tp1_orders) == 1:
                        found_tp1 = True
                        trade["tp1_order_id"] = tp1_orders[0][0]

                    if len(tp2_orders) > 1:
                        logger.warning(f"🦸‍♂️ [SUPER SUPERVISOR] Detectados {len(tp2_orders)} TP2 duplicados para {symbol}. Limpiando...")
                        for oid, _ in tp2_orders: await self.client.cancel_order(symbol, oid)
                    elif len(tp2_orders) == 1:
                        found_tp2 = True
                        trade["tp2_order_id"] = tp2_orders[0][0]

                    # ─────────────────────────────────────────────────────
                    # CHECK 4: VALIDAR Y FORZAR STOP LOSS
                    # ─────────────────────────────────────────────────────
                    if not found_sl:
                        logger.error(f"⚠️ [SUPER SUPERVISOR] ALERTA: {symbol} ({trade.get('strategy', 'Unknown')}) NO tiene Stop Loss en Bybit! Recreando @ {trade['sl_price']:.4f}...")
                        new_sl = await self.executor.update_sl(
                            symbol, trade["side"], old_sl_id="", new_sl_price=trade["sl_price"], remaining_size=trade["remaining_size"]
                        )
                        if new_sl:
                            trade["sl_order_id"] = new_sl
                            logger.info(f"✅ [SUPER SUPERVISOR] SL Restaurado exitosamente para {symbol}.")
                    else:
                        # Chequeo de Ghost SL (desfase por red)
                        if abs(exchange_sl_price - trade["sl_price"]) > (trade["atr"] * 0.05):
                            logger.warning(f"👻 [SUPER SUPERVISOR] Ghost SL en {symbol}. Bybit:{exchange_sl_price:.4f} Memoria:{trade['sl_price']:.4f}. Corrigiendo...")
                            new_sl = await self.executor.update_sl(
                                symbol, trade["side"], old_sl_id=trade["sl_order_id"], new_sl_price=trade["sl_price"], remaining_size=trade["remaining_size"]
                            )
                            if new_sl:
                                trade["sl_order_id"] = new_sl
                                logger.info(f"🦸‍♂️ [SUPER SUPERVISOR] SL Sincronizado correctamente para {symbol}.")

                    # ─────────────────────────────────────────────────────
                    # CHECK 5: VALIDAR TAKE PROFITS HUÉRFANOS (Solo Estrategia 1)
                    # ─────────────────────────────────────────────────────
                    if trade.get("tp1_price") is not None:
                        if not found_tp1 and not trade.get("tp1_hit"):
                            logger.error(f"⚠️ [SUPER SUPERVISOR] ALERTA: TP1 de {symbol} desaparecido. Recreando...")
                            tp1_qty = trade["position_size"] * 0.3
                            new_tp1 = await self.executor.place_single_tp(symbol, trade["side"], trade["tp1_price"], tp1_qty)
                            if new_tp1:
                                trade["tp1_order_id"] = new_tp1
                                
                        if not found_tp2 and not trade.get("tp2_hit"):
                            logger.error(f"⚠️ [SUPER SUPERVISOR] ALERTA: TP2 de {symbol} desaparecido. Recreando...")
                            tp2_qty = trade["position_size"] * 0.3
                            new_tp2 = await self.executor.place_single_tp(symbol, trade["side"], trade["tp2_price"], tp2_qty)
                            if new_tp2:
                                trade["tp2_order_id"] = new_tp2

                    # ─────────────────────────────────────────────────────
                    # LOG DE ESTADO DE FASE EN CADA CICLO
                    # ─────────────────────────────────────────────────────
                    phase = "ENTRADA ACTIVA"
                    if trade.get("trailing_active"):        phase = "🔁 TRAILING RUN (40%)"
                    elif trade.get("tp2_hit"):              phase = "TP2 ✅ → Activando Trailing"
                    elif trade.get("profit_lock_active"):   phase = "🛡️ BREAKEVEN ACTIVO"
                    elif trade.get("tp1_hit"):              phase = "TP1 ✅ → Buscando TP2"
                    
                    t1 = f"{trade['tp1_price']:.4f}" if trade.get('tp1_price') else "OFF"
                    t2 = f"{trade['tp2_price']:.4f}" if trade.get('tp2_price') else "OFF"
                    logger.info(f"🦸‍♂️ [SUPER SUPERVISOR] {symbol} {trade['side']} ({trade.get('strategy', 'Unknown')}) | {phase} | SL:{trade['sl_price']:.4f} | TP1:{t1} | TP2:{t2}")

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Too Many Requests" in error_msg or "timeout" in error_msg.lower():
                    backoff_time = min(backoff_time * 2, max_backoff)
                    logger.error(f"🦸‍♂️ [SUPER SUPERVISOR] Rate Limit. Durmiendo {backoff_time}s.")
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error(f"🦸‍♂️ [SUPER SUPERVISOR] Error durante patrullaje: {e}")
            else:
                backoff_time = 2

    async def stop(self):
        self.running = False
        logger.info("🦸‍♂️ [SUPER SUPERVISOR] Apagando...")

