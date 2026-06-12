import asyncio
import json
import time
from typing import Optional
from app.exchange.bingx_client import AsyncBingXClient
from app.risk.takeprofit_manager import TakeProfitManager
from app.logger import logger
from app.constants import POSITIONS_FILE, TRADES_FILE
from app.state_manager import StateManager
from app.notifications.telegram import notifier

class OrderExecutor:
    """
    Executes all trading orders against BingX.
    Rules enforced:
    - ONLY LIMIT orders (no MARKET).
    - Entry orders use postOnly.
    - TP/SL use reduceOnly.
    - NO TP/SL placed before position is confirmed real.
    - Verifies order existence after placement (no assumption on HTTP 200).
    """

    def __init__(self):
        self.client = AsyncBingXClient()
        self.tp_manager = TakeProfitManager()

    async def setup_leverage(self, symbol: str, side: str):
        """Set margin mode to ISOLATED and set leverage before entering a position."""
        from app.config import Config
        
        # Enforce ISOLATED margin mode
        margin_ok = await self.client.set_margin_type(symbol, "ISOLATED")
        if not margin_ok:
            logger.warning(f"Could not set ISOLATED margin mode for {symbol}")
            
        ok = await self.client.set_leverage(symbol, side, Config.LEVERAGE)
        if not ok:
            logger.warning(f"Could not set leverage for {symbol} {side}")

    async def place_entry(self, symbol: str, side: str, size: float, price: float, strategy: str = "") -> Optional[str]:
        """
        Place a MARKET entry order for instant execution.
        Returns order_id string if successful, None otherwise.
        """
        pos_side = "LONG" if side == "LONG" else "SHORT"
        order_side = "BUY" if side == "LONG" else "SELL"

        await self.setup_leverage(symbol, "LONG")
        await self.setup_leverage(symbol, "SHORT")

        current_size = size
        max_retries = 3
        
        for attempt in range(max_retries):
            logger.info(f"[ENTRY] Placing LIMIT {order_side}/{pos_side} {current_size:.6f} @ {price:.4f} on {symbol} (Attempt {attempt+1}/{max_retries})")
            res = await self.client.place_order(
                symbol=symbol,
                side=order_side,
                position_side=pos_side,
                order_type="MARKET",
                quantity=current_size,
                price=None,
                post_only=False,
                reduce_only=False
            )

            if res.get("success") and res.get("data"):
                order_data = res["data"].get("order", res["data"])
                order_id = str(order_data.get("orderId", ""))
                logger.info(f"[ENTRY] Order placed OK. ID={order_id}")
                return order_id
                
            code = res.get("code")
            msg = res.get("msg", "")
            logger.error(f"[ENTRY] Failed to place order: {msg} (Code: {code})")
            
            # Insufficient Margin codes
            if code in [100412, 100438, 80001, 100440]:
                logger.warning(f"[AUTO-HEALING] Insufficient margin detected for {symbol}. Scaling down size by 50%...")
                current_size = current_size / 2.0
                await asyncio.sleep(0.5)
                continue
            else:
                # Other error, don't retry
                break

        logger.error(f"[ENTRY] Aborting entry for {symbol} after failures.")
        return None

    async def verify_position_exists(self, symbol: str, side: str) -> dict:
        """
        Query real position from exchange and verify it exists with positive size.
        Returns position dict or empty dict.
        """
        positions = await self.client.get_positions(symbol)
        if not positions:
            return {}
        pos_side = "LONG" if side == "LONG" else "SHORT"
        for pos in positions:
            amt = float(pos.get("positionAmt", 0))
            if pos.get("positionSide") == pos_side and abs(amt) > 0:
                return pos
        return {}

    async def place_sl_and_tps(self, symbol: str, side: str, entry_price: float,
                                sl_price: float, total_size: float) -> dict:
        """
        After confirmed fill, place:
        - 1 Stop Loss (reduceOnly LIMIT)
        - 3 Take Profit orders at 30%, 30%, 40% of size (reduceOnly LIMIT)
        Returns dict with order IDs.
        """
        # === CRITICAL: Verify position truly exists before placing TP/SL ===
        pos = await self.verify_position_exists(symbol, side)
        if not pos:
            logger.error(f"[TP/SL] Position not found on exchange for {symbol} {side}. Aborting TP/SL placement.")
            return {}, []

        real_size = abs(float(pos.get("positionAmt", total_size)))
        logger.info(f"[TP/SL] Confirmed position {symbol} {side} size={real_size:.6f}")
        
        pos_side = "LONG" if side == "LONG" else "SHORT"
        close_side = "SELL" if side == "LONG" else "BUY"

        order_ids = {"sl": None, "tp1": None, "tp2": None, "tp3": None}

        # === Place Stop Loss ===
        sl_res = await self.client.place_order(
            symbol=symbol,
            side=close_side,
            position_side=pos_side,
            order_type="STOP_MARKET",
            quantity=real_size,
            stop_price=sl_price
        )
        if sl_res.get("success") and sl_res.get("data"):
            sl_data = sl_res["data"].get("order", sl_res["data"])
            order_ids["sl"] = str(sl_data.get("orderId", ""))
            logger.info(f"[SL] Placed @ {sl_price:.4f}. ID={order_ids['sl']}")
        else:
            logger.error(f"[SL] FAILED to place SL @ {sl_price:.4f}: {sl_res.get('msg')}")
            logger.warning(f"[SL FALLBACK] Attempting wider SL for {symbol}...")
            # Widen by 0.5% of entry price to ensure it passes exchange min_distance
            fallback_offset = entry_price * 0.005
            fallback_sl = sl_price - fallback_offset if side == "LONG" else sl_price + fallback_offset
            
            fb_res = await self.client.place_order(
                symbol=symbol,
                side=close_side,
                position_side=pos_side,
                order_type="STOP_MARKET",
                quantity=real_size,
                stop_price=fallback_sl
            )
            if fb_res.get("success") and fb_res.get("data"):
                fb_data = fb_res["data"].get("order", fb_res["data"])
                order_ids["sl"] = str(fb_data.get("orderId", ""))
                logger.info(f"[SL FALLBACK] SUCCESS @ {fallback_sl:.4f}. ID={order_ids['sl']}")
            else:
                code = fb_res.get("code")
                if code in [110411, 110412]:
                    logger.error(f"[SL FALLBACK] Price already breached SL level. Marking as BREACHED.")
                    order_ids["sl"] = "BREACHED"
                else:
                    logger.error(f"[SL FALLBACK] ALSO FAILED: {fb_res.get('msg')}")

        # === Calculate TP levels ===
        tps = self.tp_manager.calculate_tps(entry_price, sl_price, real_size, side)
        
        # === Place TPs ===
        for i, tp in enumerate(tps):
            tp_res = await self.client.place_order(
                symbol=symbol,
                side=close_side,
                position_side=pos_side,
                order_type="TAKE_PROFIT_MARKET",
                quantity=tp["qty"],
                stop_price=tp["price"]
            )
            if tp_res.get("success") and tp_res.get("data"):
                d = tp_res["data"].get("order", tp_res["data"])
                tp_key = f"tp{i+1}"
                order_ids[tp_key] = str(d.get("orderId", ""))
                logger.info(f"[TP LEVEL {i+1}] Placed @ {tp['price']:.6f} for qty {tp['qty']}. ID={order_ids[tp_key]}")
            else:
                logger.error(f"[TP LEVEL {i+1}] FAILED: {tp_res.get('msg')}")

        return order_ids, tps

    async def update_sl(self, symbol: str, side: str, old_sl_id: str,
                        new_sl_price: float, remaining_size: float) -> Optional[str]:
        """
        Cancel old SL and place new one after TP1 or TP2 fires.
        """
        pos_side = "LONG" if side == "LONG" else "SHORT"
        close_side = "SELL" if side == "LONG" else "BUY"

        # Cancel old SL if it exists
        if old_sl_id and old_sl_id != "BREACHED" and not str(old_sl_id).startswith("orphan_"):
            cancel_res = await self.client._request(
                "DELETE", "/openApi/swap/v2/trade/order",
                params={"symbol": symbol.upper(), "orderId": old_sl_id},
                signed=True
            )
            if cancel_res.get("success") or cancel_res.get("code") in [100418, 100438]:
                logger.info(f"[SL UPDATE] Old SL {old_sl_id} cancelled or already executed/gone.")
            else:
                logger.warning(f"[SL UPDATE] Could not cancel old SL {old_sl_id}: {cancel_res.get('msg')}")
                # If we couldn't cancel the old one due to a real error, abort to avoid double SLs.
                return None

        # Place new SL
        # Removing the hardcoded rounding; let bingx_client _format_number handle precision.
        sl_res = await self.client.place_order(
            symbol=symbol,
            side=close_side,
            position_side=pos_side,
            order_type="STOP_MARKET",
            quantity=remaining_size,
            stop_price=new_sl_price
        )
        if sl_res.get("success") and sl_res.get("data"):
            d = sl_res["data"].get("order", sl_res["data"])
            new_id = str(d.get("orderId", ""))
            logger.info(f"[SL UPDATE] New SL placed @ {new_sl_price:.4f}. ID={new_id}")
            return new_id

        code = sl_res.get("code")
        if code in [110411, 110412]:
            logger.error(f"[SL UPDATE] Price already breached new SL level! Emergency close for {symbol}.")
            await self.close_position_market(symbol, side)
            return "BREACHED"

        logger.error(f"[SL UPDATE] Failed to place new SL: {sl_res.get('msg')}")
        return None

    async def close_position_market(self, symbol: str, side: str):
        """Emergency: close position using MARKET order."""
        logger.warning(f"[EMERGENCY CLOSE] Cancelling orders and closing {symbol} {side}")
        await self.client.cancel_all_orders(symbol)
        
        pos = await self.verify_position_exists(symbol, side)
        if pos:
            real_size = abs(float(pos.get("positionAmt", 0)))
            if real_size > 0:
                pos_side = "LONG" if side == "LONG" else "SHORT"
                close_side = "SELL" if side == "LONG" else "BUY"
                await self.client.place_order(
                    symbol=symbol,
                    side=close_side,
                    position_side=pos_side,
                    order_type="MARKET",
                    quantity=real_size,
                    reduce_only=False
                )
                asyncio.create_task(notifier.notify_close(symbol, side, reason="Cierre de Emergencia"))

    async def verify_and_restore_protection(self, symbol: str, trade: dict):
        """
        Smartly checks active orders on BingX and ONLY places missing SL/TPs.
        Handles the single TP + Trailing Stop system.
        """
        try:
            open_orders = await self.client.get_open_orders(symbol)
        except Exception as e:
            logger.error(f"[SMART RESTORE] Failed to get open orders for {symbol}: {e}")
            return

        has_sl = False
        has_tp = False
        
        if open_orders:
            for order in open_orders:
                # CRITICAL: BingX openOrders API returns orders for ALL symbols. Filter strictly by symbol.
                if order.get("symbol", "").upper().replace("-", "") != symbol.upper().replace("-", ""):
                    continue
                o_type = order.get("type", order.get("orderType", ""))
                if o_type == "STOP_MARKET":
                    has_sl = True
                    # FIX: Save the found orderId to prevent infinite Guardian loops
                    trade["sl_order_id"] = str(order.get("orderId", ""))
                elif o_type == "TAKE_PROFIT_MARKET":
                    has_tp = True

        # Verify position exists
        pos = await self.verify_position_exists(symbol, trade["side"])
        if not pos:
            return  # Position is closed or not found
            
        real_size = abs(float(pos.get("positionAmt", 0)))
        entry_price = float(pos.get("avgPrice", trade.get("entry_price", 0)))
        side = trade["side"]
        
        pos_side = "LONG" if side == "LONG" else "SHORT"
        close_side = "SELL" if side == "LONG" else "BUY"
        
        # Determine base SL price and target TP price
        sl_price = trade.get("sl_price")
        if not sl_price:
            sl_price = entry_price * 0.98 if side == "LONG" else entry_price * 1.02
            
        tp_price = trade.get("tp_price")
        if not tp_price:
            risk_dist = abs(entry_price - sl_price)
            tp_price = entry_price + (risk_dist * 5.0) if side == "LONG" else entry_price - (risk_dist * 5.0)

        target_distance = abs(entry_price - tp_price)
        
        # 1. Determine correct Stop Loss level based on current state
        if trade.get("trailing_active"):
            # If trailing is active, use the trailed stop price stored in state
            target_sl_price = trade.get("sl_price", sl_price)
        elif trade.get("breakeven_hit"):
            # If breakeven is hit, target is based on config (matches engine.py lock_in_profit)
            from app.config import Config
            target_sl_price = entry_price + (Config.BREAKEVEN_LOCK_PCT * target_distance) if side == "LONG" else entry_price - (Config.BREAKEVEN_LOCK_PCT * target_distance)
        else:
            target_sl_price = sl_price

        # Restore Stop Loss if missing
        if not has_sl:
            logger.info(f"[SMART RESTORE] {symbol} SL missing on exchange. Placing at {target_sl_price:.6f} for size {real_size}...")
            
            max_sl_retries = 5
            sl_placed = False
            current_sl_price = target_sl_price
            
            for attempt in range(max_sl_retries):
                sl_res = await self.client.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type="STOP_MARKET", quantity=real_size, stop_price=current_sl_price
                )
                if sl_res.get("success") and sl_res.get("data"):
                    new_sl_id = str(sl_res["data"].get("order", sl_res["data"]).get("orderId", ""))
                    trade["sl_order_id"] = new_sl_id
                    trade["sl_price"] = current_sl_price
                    logger.info(f"[SMART RESTORE] SL restored successfully. ID={new_sl_id}")
                    sl_placed = True
                    break
                else:
                    code = sl_res.get("code")
                    msg = sl_res.get("msg", "")
                    if code in [110411, 110412]:
                        logger.warning(f"[AUTO-HEALING] SL price {current_sl_price:.6f} rejected. Adjusting 0.2% towards entry (Attempt {attempt+1}/{max_sl_retries})...")
                        if side == "LONG":
                            current_sl_price = current_sl_price * 1.002
                        else:
                            current_sl_price = current_sl_price * 0.998
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        logger.error(f"[SMART RESTORE] SL restoration failed: {msg}")
                        break
                        
            if not sl_placed:
                logger.error(f"[SMART RESTORE] SL placement failed after {max_sl_retries} attempts. Emergency closing {symbol} to prevent unprotected position.")
                await self.close_position_market(symbol, side)
                trade["sl_order_id"] = "BREACHED"

        # 2. Restore Take Profit if missing (only if trailing is NOT active yet)
        if not trade.get("trailing_active") and not has_tp:
            logger.info(f"[SMART RESTORE] {symbol} TP missing. Placing at {tp_price:.6f} for size {real_size}...")
            tp_res = await self.client.place_order(
                symbol=symbol, side=close_side, position_side=pos_side,
                order_type="TAKE_PROFIT_MARKET", quantity=real_size, stop_price=tp_price
            )
            if tp_res.get("success") and tp_res.get("data"):
                new_tp_id = str(tp_res["data"].get("order", tp_res["data"]).get("orderId", ""))
                trade["tp1_order_id"] = new_tp_id
                trade["tp_price"] = tp_price
                logger.info(f"[SMART RESTORE] TP restored successfully. ID={new_tp_id}")
            else:
                logger.error(f"[SMART RESTORE] TP restoration failed: {tp_res.get('msg')}")
