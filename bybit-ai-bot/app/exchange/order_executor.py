import asyncio
from typing import Optional, Tuple
from app.exchange.bybit_client import AsyncBybitClient
from app.risk.takeprofit_manager import TakeProfitManager
from app.logger import logger
from app.config import Config
from app.notifications.discord import discord_notifier

class OrderExecutor:
    """
    Executes trading orders strictly according to new logic.
    - Entry: LIMIT order
    - Entry uses postOnly=False (we want immediate execution if possible but as LIMIT).
    - TP/SL: reduceOnly=True
    """
    def __init__(self):
        self.client = AsyncBybitClient()

    async def setup_leverage(self, symbol: str, side: str):
        margin_ok = await self.client.set_margin_type(symbol, "ISOLATED")
        ok = await self.client.set_leverage(symbol, side, Config.LEVERAGE)

    async def get_current_price(self, symbol: str) -> float:
        ticker = await self.client.get_ticker(symbol)
        return float(ticker.get("lastPrice", 0.0))

    async def place_entry(self, symbol: str, side: str, size: float, entry_price: float = None) -> Optional[str]:
        pos_side = "LONG" if side == "LONG" else "SHORT"
        order_side = "BUY" if side == "LONG" else "SELL"
        await self.setup_leverage(symbol, "LONG")
        await self.setup_leverage(symbol, "SHORT")

        if entry_price is None or entry_price <= 0:
            ticker = await self.client.get_ticker(symbol)
            entry_price = float(ticker.get("askPrice", 0)) if side == "LONG" else float(ticker.get("bidPrice", 0))
            if entry_price <= 0:
                entry_price = float(ticker.get("lastPrice", 0))
            
        logger.info(f"[ENTRY] Placing LIMIT {order_side}/{pos_side} {size:.6f} @ {entry_price:.4f} on {symbol}")
        res = await self.client.place_order(
            symbol=symbol,
            side=order_side,
            position_side=pos_side,
            order_type="LIMIT",
            quantity=size,
            price=entry_price,
            post_only=False,
            reduce_only=False
        )

        if res.get("success") and res.get("data"):
            order_data = res["data"].get("order", res["data"])
            order_id = str(order_data.get("orderId", ""))
            logger.info(f"[ENTRY] Order placed OK. ID={order_id}")
            return order_id
        
        logger.error(f"[ENTRY] Failed to place order: {res.get('msg')} (Code: {res.get('code')})")
        return None

    async def verify_position_exists(self, symbol: str, side: str) -> dict:
        positions = await self.client.get_positions(symbol)
        if not positions:
            return {}
        pos_side = "LONG" if side == "LONG" else "SHORT"
        for pos in positions:
            amt = float(pos.get("positionAmt", 0))
            if pos.get("positionSide") == pos_side and abs(amt) > 0:
                return pos
        return {}

    async def place_sl_and_tps(self, symbol: str, side: str, sl_price: float, tp1_price: float, tp2_price: float, total_size: float) -> dict:
        pos = await self.verify_position_exists(symbol, side)
        if not pos:
            logger.error(f"[TP/SL] Position not found on exchange for {symbol} {side}.")
            return {}

        real_size = abs(float(pos.get("positionAmt", total_size)))
        pos_side = "LONG" if side == "LONG" else "SHORT"
        close_side = "SELL" if side == "LONG" else "BUY"

        order_ids = {"sl": None, "tp1": None, "tp2": None}

        # Place Stop Loss
        sl_res = await self.client.place_order(
            symbol=symbol, side=close_side, position_side=pos_side,
            order_type="STOP_MARKET", quantity=real_size, stop_price=sl_price, reduce_only=True
        )
        if sl_res.get("success") and sl_res.get("data"):
            order_ids["sl"] = str(sl_res["data"].get("order", sl_res["data"]).get("orderId", ""))
            logger.info(f"[SL] Placed @ {sl_price:.4f}. ID={order_ids['sl']}")

        tp1_qty, tp2_qty = TakeProfitManager.calculate_tp_quantities(real_size)
        
        if tp1_price is not None:
            # Place TP1
            tp1_res = await self.client.place_order(
                symbol=symbol, side=close_side, position_side=pos_side,
                order_type="TAKE_PROFIT_MARKET", quantity=tp1_qty, stop_price=tp1_price, reduce_only=True
            )
            if tp1_res.get("success") and tp1_res.get("data"):
                order_ids["tp1"] = str(tp1_res["data"].get("order", tp1_res["data"]).get("orderId", ""))
                
        if tp2_price is not None:
            # Place TP2
            tp2_res = await self.client.place_order(
                symbol=symbol, side=close_side, position_side=pos_side,
                order_type="TAKE_PROFIT_MARKET", quantity=tp2_qty, stop_price=tp2_price, reduce_only=True
            )
            if tp2_res.get("success") and tp2_res.get("data"):
                order_ids["tp2"] = str(tp2_res["data"].get("order", tp2_res["data"]).get("orderId", ""))

        return order_ids

    async def place_single_tp(self, symbol: str, side: str, tp_price: float, qty: float) -> Optional[str]:
        pos_side = "LONG" if side == "LONG" else "SHORT"
        close_side = "SELL" if side == "LONG" else "BUY"
        
        res = await self.client.place_order(
            symbol=symbol, side=close_side, position_side=pos_side,
            order_type="TAKE_PROFIT_MARKET", quantity=qty, stop_price=tp_price, reduce_only=True
        )
        if res.get("success") and res.get("data"):
            new_id = str(res["data"].get("order", res["data"]).get("orderId", ""))
            logger.info(f"[TP RECOVERY] Re-placed TP @ {tp_price:.4f}. ID={new_id}")
            return new_id
        return None

    async def update_sl(self, symbol: str, side: str, old_sl_id: str, new_sl_price: float, remaining_size: float) -> Optional[str]:
        pos_side = "LONG" if side == "LONG" else "SHORT"
        close_side = "SELL" if side == "LONG" else "BUY"

        if old_sl_id and old_sl_id != "BREACHED":
            cancel_res = await self.client.cancel_order(symbol, old_sl_id)

        new_res = await self.client.place_order(
            symbol=symbol, side=close_side, position_side=pos_side,
            order_type="STOP_MARKET", quantity=remaining_size, stop_price=new_sl_price, reduce_only=True
        )
        if new_res.get("success") and new_res.get("data"):
            new_id = str(new_res["data"].get("order", new_res["data"]).get("orderId", ""))
            logger.info(f"[SL UPDATE] New SL placed @ {new_sl_price:.4f}. ID={new_id}")
            return new_id
            
        return None

    async def close_position_market(self, symbol: str, side: str, reason: str = ""):
        logger.warning(f"[CLOSE] Cancelling orders and closing {symbol} {side}")
        await self.client.cancel_all_orders(symbol)
        pos = await self.verify_position_exists(symbol, side)
        if pos:
            real_size = abs(float(pos.get("positionAmt", 0)))
            if real_size > 0:
                pos_side = "LONG" if side == "LONG" else "SHORT"
                close_side = "SELL" if side == "LONG" else "BUY"
                await self.client.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type="MARKET", quantity=real_size, reduce_only=False
                )
                await discord_notifier.notify_close(symbol, side, reason)
