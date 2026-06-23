import asyncio
import time
from app.logger import logger
from app.exchange.bybit_client import AsyncBybitClient
from app.exchange.order_executor import OrderExecutor
from app.database import crud

# ──────────────────────────────────────────────────────────────────────────────
# POSITION MANAGER — Inteligencia Retroactiva por Velas (K-lines)
#
# Misión: Cada 60 segundos, descarga las últimas velas de cada posición activa
# y cruza los máximos/mínimos históricos con los niveles matemáticos de la 
# estrategia. Si el precio tocó un nivel mientras el Websocket estaba caído 
# o el servidor reiniciado, esta función lo detecta y activa el estado 
# correspondiente retroactivamente.
#
# Lógica de niveles (ATR):
#   SL         = entry ± 2.5 ATR
#   TP1        = entry ± 2.5 ATR   → 30% del volumen
#   Breakeven  = entry ± 2.0 ATR   → 40% del recorrido hasta TP2 (5.0 ATR)
#   TP2        = entry ± 5.0 ATR   → 30% del volumen, activa Trailing
# ──────────────────────────────────────────────────────────────────────────────

class RetroactivePositionManager:
    def __init__(self, engine):
        self.engine = engine
        self.client = AsyncBybitClient()
        self.executor = OrderExecutor()
        self.running = False
        self._audit_interval = 60  # segundos entre auditorías de klines

    async def start(self):
        self.running = True
        logger.info("🔭 [RETRO-PM] Inteligencia Retroactiva iniciada. Auditando velas cada 60s.")
        await self._audit_loop()

    async def stop(self):
        self.running = False

    async def _audit_loop(self):
        while self.running:
            await asyncio.sleep(self._audit_interval)
            symbols = list(self.engine.trade_state.keys())
            if not symbols:
                continue
            for sym in symbols:
                try:
                    await self._audit_symbol(sym)
                except Exception as e:
                    logger.error(f"🔭 [RETRO-PM] Error auditando {sym}: {e}")

    async def _audit_symbol(self, symbol: str):
        trade = self.engine.trade_state.get(symbol)
        if not trade or not trade.get("filled"):
            return  # Aún no llenada, nada que auditar

        side        = trade["side"]
        entry       = trade["entry_price"]
        atr         = trade["atr"]
        tp1         = trade["tp1_price"]
        tp2         = trade["tp2_price"]
        sl          = trade["sl_price"]
        be_thresh   = entry + (1.665 * atr) if side == "LONG" else entry - (1.665 * atr)  # 33.3% activa BE
        pl_lock     = entry + (0.05 * atr) if side == "LONG" else entry - (0.05 * atr)  # SL landing BE 1%

        # ── Descargar las últimas 30 velas de 1 minuto ─────────────────────
        klines = await self.client.get_klines(symbol, interval="1", limit=30)
        if not klines:
            logger.warning(f"🔭 [RETRO-PM] Sin velas para {symbol}. Saltando.")
            return

        # ── Calcular máximos y mínimos históricos del lote de velas ────────
        candle_highs = [k["high"] for k in klines]
        candle_lows  = [k["low"]  for k in klines]
        hist_high    = max(candle_highs)
        hist_low     = min(candle_lows)

        changed = False  # si cambia algo, persistimos en DB

        if side == "LONG":
            # ── Detección de TP1 por mecha ────────────────────────────────
            if tp1 is not None and not trade.get("tp1_hit") and hist_high >= tp1:
                logger.info(f"🔭 [RETRO-PM] {symbol} LONG: Mecha detectada en TP1 {tp1:.4f} (high={hist_high:.4f}). Marcando TP1.")
                trade["tp1_hit"] = True
                trade["remaining_size"] = max(trade["remaining_size"] - trade["position_size"] * 0.3, 0)
                changed = True

            # ── Detección de Breakeven por mecha ─────────────────────────
            if not trade.get("profit_lock_active") and hist_high >= be_thresh:
                logger.info(f"🔭 [RETRO-PM] {symbol} LONG: Precio superó umbral BE {be_thresh:.4f}. Activando Breakeven retroactivo.")
                await self._activate_be(symbol, trade)
                changed = True

            # ── Detección de TP2 / Trailing por mecha ────────────────────
            if tp2 is not None and not trade.get("tp2_hit") and hist_high >= tp2:
                logger.info(f"🔭 [RETRO-PM] {symbol} LONG: Mecha detectada en TP2 {tp2:.4f} (high={hist_high:.4f}). Activando Trailing.")
                trade["tp2_hit"] = True
                trade["trailing_active"] = True
                trade["remaining_size"] = max(trade["remaining_size"] - trade["position_size"] * 0.3, 0)
                # SL de trailing: precio más alto visto - 1.2 ATR
                new_sl = hist_high - (1.2 * atr)
                if new_sl > trade["sl_price"]:
                    await self._push_sl(symbol, trade, new_sl)
                changed = True

            # ── Trailing activo: ajustar SL al máximo histórico visto ─────
            elif trade.get("trailing_active") and hist_high > trade.get("highest_price", entry):
                trade["highest_price"] = hist_high
                new_sl = hist_high - (1.2 * atr)
                if new_sl > trade["sl_price"] + (atr * 0.05):
                    logger.info(f"🔭 [RETRO-PM] {symbol} Trailing retroactivo. Nuevo SL: {new_sl:.4f}")
                    await self._push_sl(symbol, trade, new_sl)
                    changed = True

            # ── Verificar si el SL fue roto (posición liquidada) ──────────
            if hist_low <= sl and not trade.get("trailing_active"):
                logger.warning(f"🔭 [RETRO-PM] {symbol} LONG: Mecha cruzó SL {sl:.4f} (low={hist_low:.4f}). Verificando posición...")
                await self._verify_position_closed(symbol, trade)
                return

        elif side == "SHORT":
            # ── Detección de TP1 por mecha ────────────────────────────────
            if tp1 is not None and not trade.get("tp1_hit") and hist_low <= tp1:
                logger.info(f"🔭 [RETRO-PM] {symbol} SHORT: Mecha detectada en TP1 {tp1:.4f} (low={hist_low:.4f}). Marcando TP1.")
                trade["tp1_hit"] = True
                trade["remaining_size"] = max(trade["remaining_size"] - trade["position_size"] * 0.3, 0)
                changed = True

            # ── Detección de Breakeven por mecha ─────────────────────────
            if not trade.get("profit_lock_active") and hist_low <= be_thresh:
                logger.info(f"🔭 [RETRO-PM] {symbol} SHORT: Precio bajo umbral BE {be_thresh:.4f}. Activando Breakeven retroactivo.")
                await self._activate_be(symbol, trade)
                changed = True

            # ── Detección de TP2 / Trailing por mecha ────────────────────
            if tp2 is not None and not trade.get("tp2_hit") and hist_low <= tp2:
                logger.info(f"🔭 [RETRO-PM] {symbol} SHORT: Mecha detectada en TP2 {tp2:.4f} (low={hist_low:.4f}). Activando Trailing.")
                trade["tp2_hit"] = True
                trade["trailing_active"] = True
                trade["remaining_size"] = max(trade["remaining_size"] - trade["position_size"] * 0.3, 0)
                new_sl = hist_low + (1.2 * atr)
                if new_sl < trade["sl_price"]:
                    await self._push_sl(symbol, trade, new_sl)
                changed = True

            # ── Trailing activo: ajustar SL al mínimo histórico visto ─────
            elif trade.get("trailing_active") and hist_low < trade.get("highest_price", entry):
                trade["highest_price"] = hist_low
                new_sl = hist_low + (1.2 * atr)
                if new_sl < trade["sl_price"] - (atr * 0.05):
                    logger.info(f"🔭 [RETRO-PM] {symbol} Trailing retroactivo SHORT. Nuevo SL: {new_sl:.4f}")
                    await self._push_sl(symbol, trade, new_sl)
                    changed = True

            # ── Verificar si el SL fue roto ───────────────────────────────
            if hist_high >= sl and not trade.get("trailing_active"):
                logger.warning(f"🔭 [RETRO-PM] {symbol} SHORT: Mecha cruzó SL {sl:.4f} (high={hist_high:.4f}). Verificando posición...")
                await self._verify_position_closed(symbol, trade)
                return

        # ── Verificar también si la orden TP1 desapareció del exchange ─────
        if not trade.get("tp1_hit"):
            await self._verify_tp1_filled(symbol, trade)
            changed = True

        # ── Persistir cambios en DB si hubo alguno ─────────────────────────
        if changed:
            db_trade = await crud.get_trade(trade["trade_id"])
            if db_trade:
                db_trade.tp1_filled         = trade["tp1_hit"]
                db_trade.tp2_filled         = trade["tp2_hit"]
                db_trade.profit_lock_active = trade["profit_lock_active"]
                db_trade.trailing_active    = trade["trailing_active"]
                db_trade.remaining_size     = trade["remaining_size"]
                db_trade.stop_loss          = trade["sl_price"]
                await crud.save_trade(db_trade)
                logger.info(f"🔭 [RETRO-PM] {symbol} estado persistido en DB.")

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _activate_be(self, symbol: str, trade: dict):
        """Mueve el SL al precio de entrada (Breakeven) y lo empuja al exchange."""
        if trade.get("profit_lock_active"):
            return
        new_sl = trade["profit_lock_price"]  # = entry_price
        await self._push_sl(symbol, trade, new_sl)
        trade["profit_lock_active"] = True
        logger.info(f"✅ [RETRO-PM] Breakeven activado para {symbol}. SL → {new_sl:.4f}")

    async def _push_sl(self, symbol: str, trade: dict, new_sl: float):
        """Cancela el SL viejo y coloca el nuevo en el exchange."""
        new_id = await self.executor.update_sl(
            symbol,
            trade["side"],
            trade.get("sl_order_id", ""),
            new_sl,
            trade["remaining_size"]
        )
        if new_id:
            trade["sl_order_id"] = new_id
            trade["sl_price"]    = new_sl

    async def _verify_tp1_filled(self, symbol: str, trade: dict):
        """
        Verifica si la orden TP1 ya no existe en el exchange sin que el bot
        lo haya detectado (ej. WebSocket caído). Si la orden desapareció y 
        el tamaño de posición bajó, marca TP1 como ejecutado.
        """
        open_orders = await self.client.get_open_orders(symbol)
        tp1_id = trade.get("tp1_order_id")
        if not tp1_id:
            return
        found = any(str(o.get("orderId", "")) == tp1_id for o in (open_orders or []))
        if not found:
            # La orden TP1 ya no está — confirmar con tamaño real
            pos = await self.executor.verify_position_exists(symbol, trade["side"])
            if pos:
                real_size = abs(float(pos.get("positionAmt", 0)))
                original  = trade["position_size"]
                if real_size <= original * 0.75:
                    logger.info(f"🔭 [RETRO-PM] {symbol} TP1 desapareció del exchange y tamaño redujo {real_size:.4f}/{original:.4f}. Marcando TP1 llenado.")
                    trade["tp1_hit"] = True
                    trade["remaining_size"] = real_size

    async def _verify_position_closed(self, symbol: str, trade: dict):
        """Verifica si la posición realmente se cerró en el exchange."""
        pos = await self.executor.verify_position_exists(symbol, trade["side"])
        if not pos:
            logger.info(f"🔭 [RETRO-PM] {symbol} confirmado cerrado en exchange. Limpiando estado.")
            await self.engine._close_position_internal(symbol, "Cierre detectado retroactivamente por mecha de SL")
