import asyncio
import time
from app.logger import logger
from app.database import crud
from app.exchange.bybit_client import AsyncBybitClient
from app.exchange.order_executor import OrderExecutor

class RecoveryEngine:
    """
    Se ejecuta al iniciar el sistema. Compara el estado de la Base de Datos con
    el Exchange y restaura el estado en memoria.
    
    INTELIGENCIA DE RECUPERACIÓN:
    - Si el bot estuvo apagado, consulta el precio ACTUAL del mercado.
    - Reconstruye el estado real de cada operación (tp1_hit, breakeven, trailing).
    - Si una condición YA SE CUMPLIÓ mientras el bot estaba caído, la activa de inmediato.
    - Nunca deja una posición desprotegida.
    """
    def __init__(self, engine):
        self.engine = engine
        self.client = AsyncBybitClient()
        self.executor = OrderExecutor()

    async def execute_recovery(self):
        logger.info("🔄 [RECOVERY] Iniciando recuperación inteligente post-reinicio...")

        # ── 1. Obtener posiciones abiertas REALES en el exchange ──────────
        open_positions = await self.client.get_positions()
        exchange_map = {}
        for pos in open_positions:
            sym = pos["symbol"]
            amt = float(pos.get("positionAmt", 0))
            if abs(amt) > 0:
                exchange_map[sym] = pos

        # ── 2. Obtener trades activos en DB ───────────────────────────────
        active_trades_db = await crud.get_all_active_trades()

        recovered = 0
        closed = 0
        processed_symbols = set()

        for trade_db in active_trades_db:
            sym = trade_db.symbol
            processed_symbols.add(sym)

            # Si ya no existe en exchange → se cerró mientras estaba caído
            if sym not in exchange_map:
                logger.warning(f"🔄 [RECOVERY] {sym} NO existe en Exchange. Marcando como cerrada en DB.")
                trade_db.position_closed = True
                await crud.save_trade(trade_db)
                closed += 1
                continue

            pos = exchange_map[sym]
            real_size = abs(float(pos.get("positionAmt", 0)))

            # ── 3. Consultar precio actual del mercado ────────────────────
            ticker = await self.client.get_ticker(sym)
            current_price = float(ticker.get("lastPrice", 0)) if ticker else 0.0

            entry   = trade_db.entry_price or 0.0
            tp1     = trade_db.tp1_price or 0.0
            tp2     = trade_db.tp2_price or 0.0
            sl      = trade_db.stop_loss or 0.0
            pl_lock = trade_db.profit_lock_price or entry
            atr     = trade_db.atr or (entry * 0.01)
            side    = trade_db.side

            # Valores actuales de estado (lo que hay guardado en DB)
            tp1_hit         = trade_db.tp1_filled
            tp2_hit         = trade_db.tp2_filled
            be_active       = trade_db.profit_lock_active
            trailing_active = trade_db.trailing_active
            sl_reconstructed = sl  # SL que usaremos al reconstruir

            # ── 4. RECONSTRUCCIÓN INTELIGENTE ─────────────────────────────
            # A) POR TAMAÑO: compara el tamaño real con el original para
            #    inferir cuántos TPs se ejecutaron mientras el bot estaba caído.
            original_size = trade_db.position_size or real_size
            size_ratio = real_size / original_size if original_size > 0 else 1.0

            if not tp1_hit and size_ratio <= 0.75:
                # Se vendió ~30% → TP1 se ejecutó
                logger.info(f"🔄 [RECOVERY] {sym} tamaño real {real_size:.4f} vs original {original_size:.4f} ({size_ratio:.0%}). TP1 ya fue ejecutado.")
                tp1_hit = True

            if not tp2_hit and size_ratio <= 0.45:
                # Se vendió ~60% → TP1 + TP2 se ejecutaron
                logger.info(f"🔄 [RECOVERY] {sym} tamaño {size_ratio:.0%} del original. TP2 también fue ejecutado. Activando Trailing.")
                tp2_hit = True
                trailing_active = True

            # B) POR PRECIO ACTUAL: detecta si condiciones de BE/Trailing
            #    ya se cumplieron aunque el tamaño no haya cambiado aún.

            if current_price > 0 and entry > 0 and tp2 > 0:
                dist_total = abs(tp2 - entry)

                if side == "LONG":
                    # TP1 superado?
                    if current_price >= tp1 and not tp1_hit:
                        logger.info(f"🔄 [RECOVERY] {sym} precio actual {current_price:.4f} ≥ TP1 {tp1:.4f}. Marcando TP1 como alcanzado.")
                        tp1_hit = True

                    # Condición de Breakeven: 33.3% de la operación (1.665 ATR)
                    be_threshold = atr * 1.665
                    if current_price >= entry + be_threshold and not be_active:
                        logger.info(f"🔄 [RECOVERY] {sym} precio {current_price:.4f} supera umbral BE {entry+be_threshold:.4f}. Activando Breakeven.")
                        be_active = True
                        sl_reconstructed = (entry + 0.05 * atr)  # SL landing: 1% (0.05 ATR)

                    # TP2 superado?
                    if current_price >= tp2 and not tp2_hit:
                        logger.info(f"🔄 [RECOVERY] {sym} precio {current_price:.4f} ≥ TP2 {tp2:.4f}. Marcando TP2 y activando Trailing.")
                        tp2_hit = True
                        trailing_active = True
                        # SL de trailing: precio actual - 1.2 ATR (conservador al reiniciar)
                        sl_reconstructed = current_price - (1.2 * atr)

                elif side == "SHORT":
                    if current_price <= tp1 and not tp1_hit:
                        logger.info(f"🔄 [RECOVERY] {sym} precio actual {current_price:.4f} ≤ TP1 {tp1:.4f}. Marcando TP1 como alcanzado.")
                        tp1_hit = True

                    # Condición de Breakeven SHORT: 33.3% de la operación (1.665 ATR)
                    be_threshold = atr * 1.665
                    if current_price <= entry - be_threshold and not be_active:
                        logger.info(f"🔄 [RECOVERY] {sym} precio {current_price:.4f} bajo umbral BE {entry-be_threshold:.4f}. Activando Breakeven.")
                        be_active = True
                        sl_reconstructed = (entry - 0.05 * atr)

                    if current_price <= tp2 and not tp2_hit:
                        logger.info(f"🔄 [RECOVERY] {sym} precio {current_price:.4f} ≤ TP2 {tp2:.4f}. Marcando TP2 y activando Trailing.")
                        tp2_hit = True
                        trailing_active = True
                        sl_reconstructed = current_price + (1.2 * atr)

            # ── 5. Persistir estado reconstruido en DB ────────────────────
            trade_db.tp1_filled       = tp1_hit
            trade_db.tp2_filled       = tp2_hit
            trade_db.profit_lock_active = be_active
            trade_db.trailing_active  = trailing_active
            trade_db.remaining_size   = real_size
            await crud.save_trade(trade_db)

            # ── 6. Restaurar en memoria (trade_state del engine) ──────────
            trade_mem = {
                "trade_id":          trade_db.trade_id,
                "side":              side,
                "strategy":          trade_db.strategy,
                "entry_price":       entry,
                "position_size":     trade_db.position_size,
                "remaining_size":    real_size,
                "atr":               atr,
                "sl_price":          sl_reconstructed,
                "tp1_price":         tp1 if tp1 > 0 else None,
                "tp2_price":         tp2 if tp2 > 0 else None,
                "profit_lock_price": pl_lock,
                "highest_price":     current_price if side == "LONG" else entry,
                "filled":            True,   # Ya está llena, estamos recuperando
                "tp1_hit":           tp1_hit,
                "tp2_hit":           tp2_hit,
                "profit_lock_active": be_active,
                "trailing_active":   trailing_active,
                "order_time":        time.time(),
                "entry_timeout":     0,      # Sin timeout al recuperar (ya está llena)
                "lock":              asyncio.Lock()
            }
            self.engine.trade_state[sym] = trade_mem

            # ── 7. Forzar SL y TPs correctos en el exchange ──────────────────────
            logger.info(f"🔄 [RECOVERY] {sym} {side} | BE:{be_active} | Trailing:{trailing_active} | SL reconstruido:{sl_reconstructed:.4f} | Empujando al exchange...")
            open_orders = await self.client.get_open_orders(sym)
            has_sl = False
            has_tp1 = False
            has_tp2 = False
            
            for o in (open_orders or []):
                stop_type = o.get("stopOrderType", "").upper()
                o_type = o.get("orderType", "").upper()
                px = float(o.get("stopPrice", o.get("triggerPrice", 0)))
                
                if "STOPLOSS" in stop_type or "STOP" in o_type:
                    has_sl = True
                elif "TAKEPROFIT" in stop_type or "TAKE_PROFIT" in o_type:
                    if tp1 > 0 and abs(px - tp1) < (atr * 0.5): has_tp1 = True
                    if tp2 > 0 and abs(px - tp2) < (atr * 0.5): has_tp2 = True

            if not has_sl:
                logger.warning(f"🔄 [RECOVERY] {sym} sin SL en exchange. Colocando SL @ {sl_reconstructed:.4f}...")
                new_sl_id = await self.executor.update_sl(sym, side, "", sl_reconstructed, real_size)
                if new_sl_id:
                    trade_mem["sl_order_id"] = new_sl_id
                    logger.info(f"✅ [RECOVERY] SL colocado para {sym}.")
                    
            if not tp1_hit and tp1 > 0 and not has_tp1:
                from app.risk.takeprofit_manager import TakeProfitManager
                qty1, _ = TakeProfitManager.calculate_tp_quantities(trade_db.position_size or real_size)
                logger.warning(f"🔄 [RECOVERY] {sym} sin TP1. Recreando TP1 @ {tp1:.4f} qty={qty1}")
                tp1_id = await self.executor.place_single_tp(sym, side, tp1, qty1)
                if tp1_id: trade_mem["tp1_order_id"] = tp1_id

            if not tp2_hit and tp2 > 0 and not has_tp2:
                from app.risk.takeprofit_manager import TakeProfitManager
                _, qty2 = TakeProfitManager.calculate_tp_quantities(trade_db.position_size or real_size)
                logger.warning(f"🔄 [RECOVERY] {sym} sin TP2. Recreando TP2 @ {tp2:.4f} qty={qty2}")
                tp2_id = await self.executor.place_single_tp(sym, side, tp2, qty2)
                if tp2_id: trade_mem["tp2_order_id"] = tp2_id

            # Suscribir al WebSocket de mark price para seguimiento en tiempo real
            await self.engine.ws.subscribe_mark_price(sym)
            recovered += 1

        # ── 8. ADOPCIÓN DE HUÉRFANOS (NUEVA LÓGICA) ───────────────────────
        adopted = 0
        for sym, pos in exchange_map.items():
            if sym not in processed_symbols:
                logger.warning(f"🚨 [RECOVERY] Operación HUÉRFANA detectada: {sym}. Iniciando Adopción Forzosa...")
                
                real_size = abs(float(pos.get("positionAmt", 0)))
                # Si positionAmt es negativo, es SHORT. En v5 Demo a veces positionSide está, pero confiar en el signo es mejor si está firmado
                amt_raw = float(pos.get("positionAmt", 0))
                pos_side = pos.get("positionSide", "")
                if pos_side == "LONG":
                    side = "LONG"
                elif pos_side == "SHORT":
                    side = "SHORT"
                else:
                    side = "LONG" if amt_raw > 0 else "SHORT"
                
                entry = float(pos.get("entryPrice", 0))
                
                ticker = await self.client.get_ticker(sym)
                current_price = float(ticker.get("lastPrice", 0)) if ticker else 0.0
                
                if entry <= 0:
                    entry = current_price
                    if entry <= 0: continue
                
                # Inteligencia Deductiva para Adivinar Estrategia
                open_orders = await self.client.get_open_orders(sym)
                has_tp_orders = any("TAKEPROFIT" in o.get("stopOrderType", "").upper() or "TAKE_PROFIT" in o.get("orderType", "").upper() for o in (open_orders or []))
                
                guessed_strategy = "AntigravityV13" if has_tp_orders else "SuperTrendRegimeMTF"
                display_strategy = "QUANTUM V13 PRO (Recuperado)" if has_tp_orders else "SUPERTREND (Recuperado)"
                
                atr = entry * 0.015  # Estimación del 1.5% de volatilidad
                
                if guessed_strategy == "AntigravityV13":
                    tp1_price = entry + (1.5 * atr) if side == "LONG" else entry - (1.5 * atr)
                    tp2_price = entry + (3.0 * atr) if side == "LONG" else entry - (3.0 * atr)
                    profit_lock_price = (entry + 0.05 * atr) if side == "LONG" else (entry - 0.05 * atr)
                    be_threshold = atr * 1.665
                else:
                    tp1_price = None
                    tp2_price = None
                    profit_lock_price = entry + (entry * (0.15 / 10)) if side == "LONG" else entry - (entry * (0.15 / 10))
                    be_threshold = atr * 1.5
                
                sl_price = entry - (2.5 * atr) if side == "LONG" else entry + (2.5 * atr)
                
                be_active = False
                tp1_hit = False
                trailing_active = False
                
                if side == "LONG":
                    if guessed_strategy == "AntigravityV13" and current_price >= tp1_price:
                        logger.info(f"🚀 [RECUPERACIÓN] {sym} LONG (Antigravity) en ALTA GANANCIA. Asegurando con Trailing Stop.")
                        tp1_hit = True
                        be_active = True
                        trailing_active = True
                        sl_price = current_price - (1.2 * atr)
                    elif current_price >= entry + be_threshold:
                        logger.info(f"🛡️ [RECUPERACIÓN] {sym} LONG en GANANCIA MEDIA. Asegurando Breakeven.")
                        be_active = True
                        sl_price = profit_lock_price
                        if guessed_strategy == "SuperTrendRegimeMTF" and current_price >= entry + (2.5 * atr):
                            trailing_active = True
                            sl_price = current_price - atr
                    else:
                        logger.info(f"⚓ [RECUPERACIÓN] {sym} LONG cerca de entrada o en pérdida. SL estándar.")
                else:
                    if guessed_strategy == "AntigravityV13" and current_price <= tp1_price:
                        logger.info(f"🚀 [RECUPERACIÓN] {sym} SHORT (Antigravity) en ALTA GANANCIA. Asegurando con Trailing Stop.")
                        tp1_hit = True
                        be_active = True
                        trailing_active = True
                        sl_price = current_price + (1.2 * atr)
                    elif current_price <= entry - be_threshold:
                        logger.info(f"🛡️ [RECUPERACIÓN] {sym} SHORT en GANANCIA MEDIA. Asegurando Breakeven.")
                        be_active = True
                        sl_price = profit_lock_price
                        if guessed_strategy == "SuperTrendRegimeMTF" and current_price <= entry - (2.5 * atr):
                            trailing_active = True
                            sl_price = current_price + atr
                    else:
                        logger.info(f"⚓ [RECUPERACIÓN] {sym} SHORT cerca de entrada o en pérdida. SL estándar.")
                
                trade_db = await crud.create_trade(
                    symbol=sym,
                    signal=side,
                    entry_price=entry,
                    stop_loss=sl_price,
                    qty=real_size,
                    strategy=guessed_strategy + "_Adopted",
                    trade_id=f"adopted_{int(time.time())}_{sym}",
                    position_size=real_size,
                    atr=atr,
                    tp1_price=tp1_price,
                    tp2_price=tp2_price,
                    profit_lock_price=profit_lock_price
                )
                
                trade_db.tp1_filled = tp1_hit
                trade_db.profit_lock_active = be_active
                trade_db.trailing_active = trailing_active
                await crud.save_trade(trade_db)
                
                trade_mem = {
                    "trade_id":          trade_db.trade_id,
                    "side":              side,
                    "strategy":          display_strategy,
                    "entry_price":       entry,
                    "position_size":     real_size,
                    "remaining_size":    real_size,
                    "atr":               atr,
                    "sl_price":          sl_price,
                    "tp1_price":         tp1_price,
                    "tp2_price":         tp2_price,
                    "profit_lock_price": profit_lock_price,
                    "highest_price":     max(entry, current_price) if side == "LONG" else min(entry, current_price),
                    "filled":            True,
                    "tp1_hit":           tp1_hit,
                    "tp2_hit":           False,
                    "profit_lock_active": be_active,
                    "trailing_active":   trailing_active,
                    "order_time":        time.time(),
                    "entry_timeout":     0,
                    "lock":              asyncio.Lock()
                }
                self.engine.trade_state[sym] = trade_mem
                
                logger.warning(f"🛡️ [RECOVERY] Colocando protecciones para huérfano {sym}: SL={sl_price:.4f}, TP1={tp1_price:.4f}, TP2={tp2_price:.4f}")
                
                tp1_to_place = None if tp1_hit else tp1_price
                tp2_to_place = None if (tp1_hit and tp2_hit) else tp2_price
                
                # First cancel any existing bad SL/TP for the orphan
                await self.client.cancel_all_orders(sym)
                
                order_ids = await self.executor.place_sl_and_tps(sym, side, sl_price, tp1_to_place, tp2_to_place, real_size)
                if order_ids:
                    trade_mem["sl_order_id"] = order_ids.get("sl")
                    trade_mem["tp1_order_id"] = order_ids.get("tp1")
                    trade_mem["tp2_order_id"] = order_ids.get("tp2")
                
                await self.engine.ws.subscribe_mark_price(sym)
                adopted += 1

        logger.info(f"✅ [RECOVERY] Completado. {recovered} recuperadas, {closed} cerradas, {adopted} ADOPTADAS.")

