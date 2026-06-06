import asyncio
import json
import time
import os
from collections import defaultdict
from app.logger import logger
from app.config import Config
from app.exchange.websocket_client import BingXWebSocket
from app.exchange.bingx_client import AsyncBingXClient
from app.exchange.order_executor import OrderExecutor
from app.exchange.position_manager import PositionManager
from app.data.candle_buffer import CandleBuffer
from app.strategy.quantum_v10_pro import evaluate_v10_pro
from app.strategy.quantum_divergence import evaluate_divergence
from app.strategy.volatility_filter import check_macro_shock
from app.database.crud import init_db, get_all_active_trades, save_trade, delete_trade, add_history, is_on_cooldown, set_cooldown
from app.database.models import TradeState
from app.risk.risk_manager import RiskManager
from app.risk.takeprofit_manager import TakeProfitManager
from app.constants import POSITIONS_FILE, TRADES_FILE, RECONCILIATION_INTERVAL
from app.state_manager import StateManager

# ============================================================
# Trade State Schema (persisted to JSON)
# ============================================================
# {
#   "BTC-USDT": {
#     "side": "LONG",
#     "entry_price": 65000.0,
#     "sl_price": 64500.0,
#     "total_size": 0.01,
#     "remaining_size": 0.01,
#     "entry_order_id": "123",
#     "sl_order_id": "456",
#     "tp1_order_id": "789",
#     "tp2_order_id": "790",
#     "tp3_order_id": "791",
#     "tp1_hit": false,
#     "tp2_hit": false,
#     "tp3_hit": false,
#     "filled": false,
#     "cooldown_until": 0,
#     "timestamp": 1234567890
#   }
# }

# Kline polling interval in seconds (poll every 60s)
KLINE_POLL_INTERVAL = Config.SCAN_INTERVAL_SECONDS

class Engine:
    """
    Core trading engine. HYBRID approach:
    - WebSocket: ONLY for private order fill events.
    - REST polling: klines fetched every 60s for all SYMBOLS.
      Closed candles are detected by timestamp change and fed into buffers.
    - Runs LRMC PRO strategy on each closed candle.
    - Places LIMIT entries, then TP1/TP2/TP3 + SL after confirmed fill.
    - Reconciles state every 30 seconds.
    - asyncio.Lock per symbol prevents race conditions.
    """

    def __init__(self):
        self.client = AsyncBingXClient()
        self.executor = OrderExecutor()
        self.risk = RiskManager()
        self.pos_manager = PositionManager()
        self.tp_manager = TakeProfitManager()
        self.ws = BingXWebSocket(
            message_callback=self._noop_ws_message,  # Klines via REST; WS only for fills
            fill_callback=self.on_fill_event
        )
        self.buffers: dict[str, CandleBuffer] = defaultdict(CandleBuffer)
        self.trade_state: dict = {}  # symbol -> trade info
        self.running = False
        self._reconcile_task = None
        self._polling_task = None
        self._symbol_updater_task = None
        self.tracked_symbols = []
        # Track last closed candle timestamp per symbol to avoid reprocessing
        self._last_candle_time: dict[str, int] = {}
        self.global_trade_lock = asyncio.Lock()
        self.btc_blocked_until = 0.0
        self.btc_block_reason = ""

    # ──────────────────────────────────────────────────────────────
    # STARTUP & SHUTDOWN
    # ──────────────────────────────────────────────────────────────
    async def start(self):
        self.running = True
        logger.info("=== LRMC PRO Engine Starting (HYBRID: REST polling + WS fills) ===")

        # Restore persisted state (survive restarts)
        await init_db()
        db_trades = await get_all_active_trades()
        self.trade_state = {}
        for t in db_trades:
            self.trade_state[t.symbol] = {
                "side": t.signal,
                "entry_price": t.entry_price,
                "sl_price": t.sl_price,
                "target_distance": t.target_distance,
                "tp_price": t.entry_price + t.target_distance if t.signal == "LONG" else t.entry_price - t.target_distance,
                "qty": t.qty,
                "total_size": t.qty,
                "remaining_size": t.qty,
                "filled": t.filled,
                "entry_order_id": t.entry_order_id,
                "sl_order_id": t.sl_order_id,
                "tp1_order_id": t.tp1_order_id,
                "trailing_active": t.trailing_active,
                "highest_price": t.highest_price,
                "breakeven_hit": t.breakeven_hit,
                "timestamp": int(t.created_at.timestamp()) if t.created_at else int(time.time()),
                "cooldown_until": 0
            }
        logger.info(f"Restored {len(self.trade_state)} active positions from SQLite storage.")

        # Restore BTC block state
        from app.constants import BTC_BLOCK_FILE
        if os.path.exists(BTC_BLOCK_FILE):
            try:
                with open(BTC_BLOCK_FILE, "r") as f:
                    block_data = json.load(f)
                    self.btc_blocked_until = float(block_data.get("blocked_until", 0.0))
                    self.btc_block_reason = block_data.get("reason", "")
                    if self.btc_blocked_until > time.time():
                        remaining = self.btc_blocked_until - time.time()
                        from datetime import datetime
                        expire_str = datetime.fromtimestamp(self.btc_blocked_until).strftime('%Y-%m-%d %H:%M:%S')
                        logger.warning(f"[BTC BLOCK] Restored active BTC block! Blocked until {expire_str} ({remaining/60:.1f}m remaining). Reason: {self.btc_block_reason}")
            except Exception as e:
                logger.error(f"[BTC BLOCK] Error loading btc_block.json: {e}")

        # Force BTC-USDT to be tracked immediately
        if "BTC-USDT" not in self.tracked_symbols:
            self.tracked_symbols.append("BTC-USDT")

        # CRITICAL: Fetch contract precisions first. If banned, wait until we can fetch them.
        while True:
            precisions = await self.client.get_contract_precisions()
            if precisions:
                logger.info(f"Successfully loaded precisions for {len(precisions)} contracts.")
                break
            logger.error("[SYSTEM] Could not load contract precisions (API Ban active?). Waiting 60s...")
            await asyncio.sleep(60)

        # ADOPT ORPHANS: Re-adopt any active BingX positions not in our local state
        try:
            real_positions = await self.client.get_positions()
            if real_positions:
                for p in real_positions:
                    symbol = p.get("symbol")
                    side = p.get("positionSide")
                    amt = abs(float(p.get("positionAmt", 0)))
                    if amt > 0 and symbol and side and (symbol not in self.trade_state or not self.trade_state[symbol].get("entry_order_id")):
                        logger.warning(f"[ORPHAN ADOPTION] Adopting unmanaged position {symbol} {side} from BingX!")
                        avg_price = float(p.get("avgPrice", 0))
                        sl_price = avg_price * 0.98 if side == "LONG" else avg_price * 1.02
                        risk_dist = abs(avg_price - sl_price)
                        tp_price = avg_price + (risk_dist * 2.0) if side == "LONG" else avg_price - (risk_dist * 2.0)
                        target_dist = abs(avg_price - tp_price)
                        # Create fallback state so Guardian and Reconcile can manage it
                        self.trade_state[symbol] = {
                            "side": "LONG" if side == "LONG" else "SHORT",
                            "entry_price": avg_price,
                            "sl_price": sl_price,
                            "tp_price": tp_price,
                            "target_distance": target_dist,
                            "breakeven_hit": False,
                            "trailing_active": False,
                            "highest_price": 0.0,
                            "total_size": amt,
                            "remaining_size": amt,
                            "entry_order_id": f"orphan_{int(time.time())}",
                            "sl_order_id": None,
                            "tp1_order_id": None,
                            "tp1_hit": False,
                            "filled": True,
                            "score": 50,
                            "cooldown_until": 0,
                            "timestamp": int(time.time())
                        }
        except Exception as e:
            logger.error(f"[SYSTEM] Error adopting orphans: {e}")

        # Start reconciliation loop
        self._reconcile_task = asyncio.create_task(self._reconciliation_loop())

        # Start top symbols updater loop
        self._symbol_updater_task = asyncio.create_task(self._symbol_updater_loop())

        # Start kline polling loop concurrently
        self._polling_task = asyncio.create_task(self._kline_polling_loop())

        # Start fast trailing loop
        self._fast_trailing_task = asyncio.create_task(self._fast_trailing_loop())

        # Start WebSocket (blocking – only handles private fills now)
        await self.ws.connect()

    async def stop(self):
        self.running = False
        if self._reconcile_task:
            self._reconcile_task.cancel()
        if self._polling_task:
            self._polling_task.cancel()
        if self._symbol_updater_task:
            self._symbol_updater_task.cancel()
        if hasattr(self, '_fast_trailing_task') and self._fast_trailing_task:
            self._fast_trailing_task.cancel()
        await self.ws.stop()
        await self._save_state()
        logger.info("Engine stopped.")

    async def _symbol_updater_loop(self):
        """Updates the top 50 volume symbols every 4 hours."""
        while self.running:
            try:
                symbols = await self.client.get_top_volume_symbols(50)
                if symbols:
                    if "BTC-USDT" not in symbols:
                        symbols.append("BTC-USDT")
                    self.tracked_symbols = symbols
                    logger.info(f"[SYSTEM] Tracking top {len(symbols)} volume symbols: {symbols[:5]}...")
                else:
                    logger.warning("[SYSTEM] Failed to fetch top symbols. Retrying later.")
            except Exception as e:
                logger.error(f"[SYSTEM] Error updating top symbols: {e}")
            await asyncio.sleep(4 * 3600)  # 4 hours

    # ──────────────────────────────────────────────────────────────
    # KLINE POLLING LOOP  (replaces WebSocket kline handling)
    # ──────────────────────────────────────────────────────────────
    async def _kline_polling_loop(self):
        """
        Polls BingX REST API every KLINE_POLL_INTERVAL seconds for the last
        20 klines per symbol.  Feeds closed candles into buffers and triggers
        strategy evaluation whenever a new closed candle is detected.
        """
        logger.info(f"[POLL] Kline polling loop started. Interval={KLINE_POLL_INTERVAL}s, TF={Config.TIMEFRAME}")

        # Brief initial delay so the WS connection can establish first
        await asyncio.sleep(5)

        while self.running:
            if not self.tracked_symbols:
                await asyncio.sleep(5)
                continue

            for symbol in self.tracked_symbols:
                try:
                    await self._poll_klines_for_symbol(symbol)
                except Exception as e:
                    logger.error(f"[POLL] Error polling {symbol}: {e}")
                
                # Small delay to avoid API rate limits when fetching 80 pairs
                await asyncio.sleep(0.1)

            await asyncio.sleep(KLINE_POLL_INTERVAL)

    async def _poll_klines_for_symbol(self, symbol: str):
        """Fetches klines via REST, updates candle buffer, and triggers strategy."""
        raw_klines = await self.client.get_klines(symbol, Config.TIMEFRAME, 60)
        if not raw_klines:
            logger.warning(f"[POLL] No klines returned for {symbol}")
            return

        # BingX REST kline format: list of dicts with keys:
        # time (open time ms), open, high, low, close, volume
        # They come in ascending order (oldest first).
        candles = []
        for k in raw_klines:
            try:
                candles.append({
                    "open":   float(k.get("open",   k.get("o", 0))),
                    "high":   float(k.get("high",   k.get("h", 0))),
                    "low":    float(k.get("low",    k.get("l", 0))),
                    "close":  float(k.get("close",  k.get("c", 0))),
                    "volume": float(k.get("volume", k.get("v", 0))),
                    "time":   int(k.get("time",     k.get("t", k.get("T", 0)))),
                    "closed": True,  # overridden below for the last entry
                })
            except (ValueError, TypeError) as e:
                logger.warning(f"[POLL] {symbol} – skipping malformed kline: {k} | {e}")
                continue

        if not candles:
            return

        # BingX returns klines in DESCENDING order (newest first).
        # Sort ascending so CandleBuffer receives them oldest → newest.
        candles.sort(key=lambda c: c["time"])

        # Last kline in the list = currently open (live) candle
        candles[-1]["closed"] = False

        # Feed all candles into the buffer
        for candle in candles:
            self.buffers[symbol].add_candle(candle)

        # Detect if a new closed candle has appeared since last poll
        # The newest closed bar is candles[-2] (second-to-last)
        if len(candles) < 2:
            return

        newest_closed = candles[-2]
        newest_closed_time = newest_closed["time"]
        prev_time = self._last_candle_time.get(symbol, 0)

        if newest_closed_time != prev_time:
            self._last_candle_time[symbol] = newest_closed_time
            logger.info(
                f"[POLL] {symbol} – NEW closed candle detected @ "
                f"ts={newest_closed_time} "
                f"O={newest_closed['open']:.4f} H={newest_closed['high']:.4f} "
                f"L={newest_closed['low']:.4f} C={newest_closed['close']:.4f} "
                f"V={newest_closed['volume']:.2f}"
            )
            if symbol == "BTC-USDT":
                await self._check_btc_volatility(symbol)
            await self._on_closed_candle(symbol)
        else:
            if symbol == "BTC-USDT":
                await self._check_btc_volatility(symbol)
            logger.debug(f"[POLL] {symbol} – no new closed candle (ts={newest_closed_time})")

    async def _check_btc_volatility(self, symbol: str):
        """
        Checks BTC-USDT candles in the buffer for sharp/sudden price movements.
        Triggers a 2-hour trading block if thresholds are breached.
        """
        try:
            recent = self.buffers[symbol].get_recent(2)
            if not recent or len(recent) < 2:
                return

            closed_candle = recent[-2]

            if check_macro_shock(closed_candle, Config.BTC_VOL_CUMUL_BODY_PCT / 100.0):
                reason = f"BTC Volatility Macro Shock Detected > {Config.BTC_VOL_CUMUL_BODY_PCT}%"
                await self._trigger_btc_block(reason)
                return

        except Exception as e:
            logger.error(f"[BTC BLOCK] Error checking BTC volatility: {e}")

    async def _trigger_btc_block(self, reason: str):
        """Activates a 2-hour trading block and persists it to disk."""
        now = time.time()
        new_blocked_until = now + Config.BTC_VOLATILITY_BLOCK_DURATION
        if new_blocked_until > self.btc_blocked_until + 10:  # 10s grace
            self.btc_blocked_until = new_blocked_until
            self.btc_block_reason = reason
            
            from datetime import datetime
            expire_str = datetime.fromtimestamp(self.btc_blocked_until).strftime('%Y-%m-%d %H:%M:%S')
            logger.warning(f"[BTC BLOCK] !!! VOLATILITY SPARK DETECTED! Blocking all new entries for 2 hours (until {expire_str}). Reason: {reason}")
            
            # Persist block state to file
            from app.constants import BTC_BLOCK_FILE
            try:
                block_data = {
                    "blocked_until": self.btc_blocked_until,
                    "reason": reason
                }
                with open(BTC_BLOCK_FILE, "w") as f:
                    json.dump(block_data, f, indent=4)
            except Exception as e:
                logger.error(f"[BTC BLOCK] Error saving block to file: {e}")

    # ──────────────────────────────────────────────────────────────
    # WEBSOCKET: no-op for market data (klines now via REST)
    # ──────────────────────────────────────────────────────────────
    async def _noop_ws_message(self, data: dict):
        """
        Market kline data is handled by REST polling.
        WebSocket is kept ONLY for private order fill events.
        This callback safely discards any market data messages.
        """
        pass  # intentionally empty

    async def on_fill_event(self, data: dict):
        """Handles private order fill events from WebSocket."""
        try:
            order_id = str(data.get("i", data.get("orderId", "")))
            status = data.get("X", data.get("status", ""))
            symbol = data.get("s", data.get("symbol", ""))

            if status != "FILLED":
                return

            logger.info(f"[FILL EVENT] {symbol} Order {order_id} status={status}")

            trade = self.trade_state.get(symbol)
            if not trade:
                return

            lock = self.pos_manager.get_lock(symbol)
            async with lock:
                # If entry order filled → place TP/SL
                if order_id == trade.get("entry_order_id") and not trade.get("filled"):
                    logger.info(f"[FILL] Entry order filled for {symbol}! Placing TP/SL...")
                    trade["filled"] = True
                    await self._place_tp_sl_for_symbol(symbol, trade)

                # If TP1 (single TP) filled → trade complete
                elif order_id == trade.get("tp1_order_id") and not trade.get("tp1_hit"):
                    trade["tp1_hit"] = True
                    logger.info(f"[TP HIT] {symbol}. Full position closed. 🎉")
                    await self._close_trade(symbol, reason="TP_HIT")

                await self._save_state()

        except Exception as e:
            logger.error(f"[FILL EVENT] Error: {e}")

    # ──────────────────────────────────────────────────────────────
    # STRATEGY EVALUATION
    # ──────────────────────────────────────────────────────────────
    async def _on_closed_candle(self, symbol: str):
        """Called on each confirmed closed candle for a symbol."""
        if time.time() < self.btc_blocked_until:
            remaining = self.btc_blocked_until - time.time()
            rem_h = int(remaining // 3600)
            rem_m = int((remaining % 3600) // 60)
            rem_s = int(remaining % 60)
            logger.warning(f"[{symbol}] Signal analysis aborted. BTC Volatility Block active. Remaining: {rem_h:02d}h {rem_m:02d}m {rem_s:02d}s. Reason: {self.btc_block_reason}")
            return

        try:
            lock = self.pos_manager.get_lock(symbol)
            async with lock:
                # Check cooldown from DB
                trade = self.trade_state.get(symbol, {})
                if await is_on_cooldown(symbol):
                    logger.debug(f"[{symbol}] In cooldown. Skipping.")
                    return

                # Skip if already in active trade
                if trade.get("entry_order_id"):
                    logger.debug(f"[{symbol}] Active trade exists. Skipping new signal.")
                    return

                # === Dual Strategy Pipeline ===
                sweep_result = await evaluate_v10_pro(self.client, symbol)
                if sweep_result["signal"] == "NONE":
                    sweep_result = await evaluate_divergence(self.client, symbol)
                
                if sweep_result["signal"] == "NONE":
                    return
                
                score = 100
                logger.info(f"[{symbol}] Strategy: {sweep_result['strategy']} triggered -> signal={sweep_result['signal']} | "
                            f"entry={sweep_result.get('entry_price', 'N/A')} | "
                            f"sl={sweep_result.get('sl_price', 'N/A')}")

                # === Critical Section: Max Trades Check & Entry ===
                async with self.global_trade_lock:
                    # Check max open trades strictly using in-memory state to avoid race conditions
                    open_count = len([s for s, t in self.trade_state.items() if t.get("entry_order_id")])
                    if not await self.risk.can_open_trade(open_count):
                        return
                        
                    balance = await self.client.get_balance()
                    
                    # Fetch live ticker to place order "closer" (best bid/ask) to open immediately
                    entry_price = sweep_result["entry_price"]  # fallback
                    try:
                        ticker = await self.client.get_ticker(symbol)
                        if ticker:
                            if sweep_result["signal"] == "LONG":
                                # For LONG, use best bid (maker) to place close limit
                                entry_price = float(ticker.get("bidPrice") or ticker.get("lastPrice") or entry_price)
                            else:
                                # For SHORT, use best ask (maker) to place close limit
                                entry_price = float(ticker.get("askPrice") or ticker.get("lastPrice") or entry_price)
                            logger.info(f"[{symbol}] Ticker fetched. Live Entry Price: {entry_price:.6f} (Original: {sweep_result['entry_price']:.6f})")
                    except Exception as e:
                        logger.error(f"[{symbol}] Error fetching ticker for entry price: {e}")

                    sl_price = sweep_result["sl_price"]
                    sl_dist_pct = abs(entry_price - sl_price) / entry_price
                    if sl_dist_pct > 0.02:
                        logger.warning(f"[{symbol}] Entry rejected: Live SL distance {sl_dist_pct:.2%} is too large (> 2.0%)")
                        return
                    if sl_dist_pct < 0.005:
                        # Re-adjust SL price to maintain minimum distance
                        sl_price = entry_price * 0.995 if sweep_result["signal"] == "LONG" else entry_price * 1.005
                        logger.info(f"[{symbol}] Adjusting SL to maintain min distance of 0.5%: {sl_price:.6f}")

                    size = self.risk.calculate_position_size(
                        entry_price, sl_price, balance
                    )
                    if size <= 0:
                        logger.warning(f"[{symbol}] Calculated size = 0. Skipping.")
                        return

                    logger.info(
                        f"[SIGNAL] {symbol} {sweep_result['signal']} | Score={score} | "
                        f"Entry={entry_price:.4f} | SL={sl_price:.4f}"
                    )

                    order_id = await self.executor.place_entry(
                        symbol, sweep_result["signal"], size, entry_price
                    )
                    if not order_id:
                        return

                    # Persist pending trade
                    risk_dist = abs(entry_price - sl_price)
                    # TP at 5.0x ATR, SL at 2.5x ATR => TP distance = 2.0 * SL distance
                    tp_price = entry_price + (risk_dist * 2.0) if sweep_result["signal"] == "LONG" else entry_price - (risk_dist * 2.0)
                    target_dist = abs(entry_price - tp_price)

                    self.trade_state[symbol] = {
                        "side": sweep_result["signal"],
                        "entry_price": entry_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "target_distance": target_dist,
                        "breakeven_hit": False,
                        "trailing_active": False,
                        "highest_price": 0.0,
                        "total_size": size,
                        "remaining_size": size,
                        "entry_order_id": order_id,
                        "sl_order_id": None,
                        "tp1_order_id": None,
                        "tp1_hit": False,
                        "filled": False,
                        "score": score,
                        "cooldown_until": 0,
                        "timestamp": int(time.time())
                    }
                await self._save_state()

        except Exception as e:
            logger.error(f"[{symbol}] Error in _on_closed_candle: {e}")

    async def _place_tp_sl_for_symbol(self, symbol: str, trade: dict):
        """Places SL + TP after confirmed position fill."""
        order_ids = await self.executor.place_sl_and_tps(
            symbol=symbol,
            side=trade["side"],
            entry_price=trade["entry_price"],
            sl_price=trade["sl_price"],
            total_size=trade["total_size"]
        )
        if order_ids:
            trade["sl_order_id"] = order_ids.get("sl")
            trade["tp1_order_id"] = order_ids.get("tp1")

    # ──────────────────────────────────────────────────────────────
    # RECONCILIATION LOOP (every 30 seconds)
    # ──────────────────────────────────────────────────────────────
    async def _reconciliation_loop(self):
        """
        Every 30s: compare our internal state vs real exchange positions.
        Restores missing TP/SL if the bot restarted mid-trade.
        Cleans up positions closed externally.
        """
        block_was_active = False
        while self.running:
            now = time.time()
            if now < self.btc_blocked_until:
                remaining = self.btc_blocked_until - now
                rem_h = int(remaining // 3600)
                rem_m = int((remaining % 3600) // 60)
                rem_s = int(remaining % 60)
                logger.info(f"[BTC BLOCK ACTIVE] Trading is BLOCKED. Remaining: {rem_h:02d}h {rem_m:02d}m {rem_s:02d}s. Reason: {self.btc_block_reason}")
                block_was_active = True
            elif block_was_active:
                logger.warning("[BTC BLOCK EXPIRED] Volatility block has expired! Bot is now allowed to trade again.")
                block_was_active = False
                from app.constants import BTC_BLOCK_FILE
                if os.path.exists(BTC_BLOCK_FILE):
                    try:
                        os.remove(BTC_BLOCK_FILE)
                    except Exception as e:
                        logger.error(f"Error removing btc_block.json: {e}")

            await asyncio.sleep(RECONCILIATION_INTERVAL)
            try:
                await self._reconcile()
            except Exception as e:
                logger.error(f"[RECONCILE] Error: {e}")

    async def _reconcile(self):
        logger.debug("[RECONCILE] Checking state vs exchange...")
        real_positions = await self.client.get_positions()

        real_open = {}
        if real_positions:
            for pos in real_positions:
                amt = float(pos.get("positionAmt", 0))
                if abs(amt) > 0:
                    sym = pos.get("symbol", "")
                    real_open[sym] = pos
                    
                    # DYNAMIC ORPHAN ADOPTION: If user opens a trade manually, bot takes over instantly.
                    if sym not in self.trade_state or not self.trade_state[sym].get("entry_order_id"):
                        side = pos.get("positionSide")
                        if side:
                            logger.warning(f"[ORPHAN ADOPTION] Real-time detection of unmanaged position {sym} {side}! The Guardian Agent is taking over.")
                            avg_price = float(pos.get("avgPrice", 0))
                            sl_price = avg_price * 0.98 if side == "LONG" else avg_price * 1.02
                            risk_dist = abs(avg_price - sl_price)
                            tp_price = avg_price + (risk_dist * 2.0) if side == "LONG" else avg_price - (risk_dist * 2.0)
                            target_dist = abs(avg_price - tp_price)
                            self.trade_state[sym] = {
                                "side": "LONG" if side == "LONG" else "SHORT",
                                "entry_price": avg_price,
                                "sl_price": sl_price,
                                "tp_price": tp_price,
                                "target_distance": target_dist,
                                "breakeven_hit": False,
                                "trailing_active": False,
                                "highest_price": 0.0,
                                "total_size": abs(amt),
                                "remaining_size": abs(amt),
                                "entry_order_id": f"orphan_rt_{int(time.time())}",
                                "sl_order_id": None,
                                "tp1_order_id": None,
                                "tp1_hit": False,
                                "filled": True,
                                "score": 50,
                                "cooldown_until": 0,
                                "timestamp": int(time.time())
                            }

        # Check each tracked symbol
        for symbol, trade in list(self.trade_state.items()):
            try:
                async with self.pos_manager.get_lock(symbol):
                    if not trade.get("entry_order_id"):
                        continue

                    if trade.get("filled"):
                        # If we think position is open but exchange says it's closed
                        if symbol not in real_open:
                            logger.warning(f"[RECONCILE] {symbol} position closed externally. Cleaning state.")
                            await self._close_trade(symbol, reason="EXTERNAL_CLOSE")
                            continue

                        pos_data = real_open[symbol]
                        pos_amt = abs(float(pos_data.get("positionAmt", 0)))
                        entry_price = trade["entry_price"]
                        sl_price = trade["sl_price"]
                        
                        # Get current price (mark price)
                        mark_price = float(pos_data.get("markPrice") or pos_data.get("avgPrice") or 0.0)
                        if mark_price == 0.0:
                            recent = self.buffers[symbol].get_recent(1)
                            if recent:
                                mark_price = recent[0]["close"]
                            else:
                                mark_price = entry_price

                        # Ensure state variables are present
                        side = trade["side"]
                        if "tp_price" not in trade:
                            risk_dist = abs(entry_price - sl_price)
                            trade["tp_price"] = entry_price + (risk_dist * 2.0) if side == "LONG" else entry_price - (risk_dist * 2.0)
                        if "target_distance" not in trade:
                            trade["target_distance"] = abs(entry_price - trade["tp_price"])
                        if "breakeven_hit" not in trade:
                            trade["breakeven_hit"] = False
                        if "trailing_active" not in trade:
                            trade["trailing_active"] = False
                        if "highest_price" not in trade or trade["highest_price"] == 0.0:
                            trade["highest_price"] = mark_price

                        # Evaluate Trailing and Breakeven
                        await self._evaluate_trailing_and_breakeven(symbol, trade, mark_price, pos_amt)

                        # Smartly verify and restore protections to ensure positions are never left unprotected
                        await self.executor.verify_and_restore_protection(symbol, trade)

                    elif trade.get("entry_order_id") and not trade.get("filled"):
                        # REST-based fill detection: WS may have missed the fill event
                        pos = await self.executor.verify_position_exists(symbol, trade["side"])
                        if pos:
                            actual_filled_size = abs(float(pos.get("positionAmt", 0)))
                            logger.info(f"[RECONCILE] {symbol} fill detected via REST! Actual size: {actual_filled_size}. Placing TP/SL...")
                            trade["filled"] = True
                            trade["total_size"] = actual_filled_size
                            trade["remaining_size"] = actual_filled_size
                            await self._place_tp_sl_for_symbol(symbol, trade)
                        else:
                            # Entry order not filled yet: check if it's stale
                            age = time.time() - trade.get("timestamp", time.time())
                            if age > Config.ENTRY_ORDER_MAX_AGE:
                                logger.warning(f"[RECONCILE] {symbol} entry order stale ({age:.0f}s > {Config.ENTRY_ORDER_MAX_AGE}s). Cancelling.")
                                await self.client.cancel_all_orders(symbol)
                                await self._close_trade(symbol, reason="STALE_ENTRY")
            except Exception as e:
                logger.error(f"[RECONCILE] Exception processing {symbol}: {e}")

        await self._save_state()

    async def _evaluate_trailing_and_breakeven(self, symbol, trade, mark_price, pos_amt):
        target_dist = trade.get("target_distance", 0)
        entry_price = trade.get("entry_price", 0)
        side = trade.get("side")

        if target_dist > 0:
            if side == "LONG":
                progress = (mark_price - entry_price) / target_dist
            else:
                progress = (entry_price - mark_price) / target_dist
        else:
            progress = 0.0

        # --- Early Exit (-40% of Risk) ---
        # SL distance is exactly 50% of target_dist. 40% of SL distance is 20% of target_dist.
        if progress <= -0.20 and not trade.get("trailing_active") and not trade.get("breakeven_hit"):
            trade_age = time.time() - trade.get("timestamp", time.time())
            if trade_age <= Config.EARLY_EXIT_LOOKBACK_MINUTES * 60:
                if symbol in self.buffers:
                    recent = self.buffers[symbol].get_recent(10)
                    if recent and len(recent) > 5:
                        avg_vol = sum(c["volume"] for c in recent[:-3]) / max(1, len(recent[:-3]))
                        current_vol = sum(c["volume"] for c in recent[-3:]) / 3.0
                        if current_vol >= Config.EARLY_EXIT_VOL_MULT * avg_vol:
                            logger.info(f"[EARLY EXIT] {symbol} Price rejecting. PnL reached -40% of risk and adverse volume detected. Cutting losses.")
                            await self._close_trade(symbol, reason="EARLY_EXIT_REJECTION")
                            return

        # --- Trailing Stop (75% of TP) ---
        if progress >= 0.75 and not trade.get("trailing_active"):
            logger.info(f"[TRAILING ACTIVATE] {symbol} progress reached {progress:.2%} (>= 75%). Cancelling TP and activating trailing stop.")
            tp_id = trade.get("tp1_order_id")
            tp_cancelled = True
            if tp_id:
                cancel_res = await self.client._request(
                    "DELETE", "/openApi/swap/v2/trade/order",
                    params={"symbol": symbol.upper(), "orderId": tp_id},
                    signed=True
                )
                if cancel_res.get("success") or cancel_res.get("code") in [100418, 100438]:
                    logger.info(f"[TRAILING ACTIVATE] TP order {tp_id} cancelled.")
                else:
                    logger.warning(f"[TRAILING ACTIVATE] TP cancel failed: {cancel_res.get('msg')}")
                    tp_cancelled = False

            if tp_cancelled:
                if side == "LONG":
                    # Floor is the Breakeven lock-in level
                    floor_sl = entry_price + 0.10 * target_dist
                    # Trailing distance: 15% of total TP target
                    trailing_sl = mark_price - 0.15 * target_dist
                    target_sl = max(floor_sl, trailing_sl)
                else:
                    floor_sl = entry_price - 0.10 * target_dist
                    trailing_sl = mark_price + 0.15 * target_dist
                    target_sl = min(floor_sl, trailing_sl)

                new_sl_id = await self.executor.update_sl(symbol, side, trade.get("sl_order_id"), target_sl, pos_amt)
                if new_sl_id:
                    trade["trailing_active"] = True
                    trade["highest_price"] = mark_price
                    trade["sl_order_id"] = new_sl_id
                    trade["sl_price"] = target_sl
                    logger.info(f"[TRAILING ACTIVATE] Trailing active. SL updated to {target_sl:.6f}.")
        
        elif trade.get("trailing_active"):
            highest_price = trade.get("highest_price", mark_price)
            if side == "LONG":
                if mark_price > highest_price:
                    trade["highest_price"] = mark_price
                    highest_price = mark_price
                trailing_sl = highest_price - 0.15 * target_dist
                floor_sl = entry_price + 0.10 * target_dist
                target_sl = max(trailing_sl, floor_sl)
                
                if target_sl > trade.get("sl_price", 0):
                    new_sl_id = await self.executor.update_sl(symbol, side, trade.get("sl_order_id"), target_sl, pos_amt)
                    if new_sl_id:
                        trade["sl_order_id"] = new_sl_id
                        trade["sl_price"] = target_sl
            else:
                if mark_price < highest_price:
                    trade["highest_price"] = mark_price
                    highest_price = mark_price
                trailing_sl = highest_price + 0.15 * target_dist
                floor_sl = entry_price - 0.10 * target_dist
                target_sl = min(trailing_sl, floor_sl)
                
                if target_sl < trade.get("sl_price", 0):
                    new_sl_id = await self.executor.update_sl(symbol, side, trade.get("sl_order_id"), target_sl, pos_amt)
                    if new_sl_id:
                        trade["sl_order_id"] = new_sl_id
                        trade["sl_price"] = target_sl

        # --- Breakeven (50% of TP) ---
        elif progress >= 0.50 and not trade.get("breakeven_hit"):
            lock_in_profit = 0.10 * target_dist
            new_sl = entry_price + lock_in_profit if side == "LONG" else entry_price - lock_in_profit
            logger.info(f"[BREAKEVEN] {symbol} progress reached {progress:.2%} (>= 50%). Moving SL to {new_sl:.6f} (+10% of TP).")
            new_sl_id = await self.executor.update_sl(symbol, side, trade.get("sl_order_id"), new_sl, pos_amt)
            if new_sl_id:
                trade["sl_order_id"] = new_sl_id
                trade["sl_price"] = new_sl
                trade["breakeven_hit"] = True

    async def _fast_trailing_loop(self):
        """
        Runs every 3 seconds. Queries get_ticker for active trades to catch fast wicks
        and activate trailing stop instantly.
        """
        await asyncio.sleep(5)
        while self.running:
            try:
                active_trades = [(sym, t) for sym, t in self.trade_state.items() if t.get("filled")]
                for symbol, trade in active_trades:
                    ticker = await self.client.get_ticker(symbol)
                    if ticker:
                        mark_price = float(ticker.get("lastPrice") or 0.0)
                        if mark_price > 0:
                            pos_amt = trade.get("remaining_size", trade.get("total_size", 0))
                            await self._evaluate_trailing_and_breakeven(symbol, trade, mark_price, pos_amt)
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"[FAST TRAILING] Error: {e}")
                await asyncio.sleep(3)

    def _timeframe_seconds(self) -> int:
        tf = Config.TIMEFRAME
        if tf.endswith("m"):
            return int(tf[:-1]) * 60
        if tf.endswith("h"):
            return int(tf[:-1]) * 3600
        return 300  # default 5m

    # ──────────────────────────────────────────────────────────────
    # STATE MANAGEMENT
    # ──────────────────────────────────────────────────────────────
    async def _close_trade(self, symbol: str, reason: str = "UNKNOWN"):
        """Remove symbol from active trades and set cooldown."""
        try:
            logger.info(f"[CLOSE TRADE] Cancelling all remaining orders for {symbol} on trade close (Reason: {reason})...")
            await self.client.cancel_all_orders(symbol)
        except Exception as e:
            logger.error(f"[CLOSE TRADE] Error cancelling remaining orders for {symbol}: {e}")

        trade = self.trade_state.pop(symbol, {})
        if trade:
            await self._log_closed_trade(symbol, trade, reason)
            await delete_trade(symbol)
            cooldown_mins = Config.COOLDOWN_MINUTES
            logger.info(f"[TRADE CLOSED] {symbol} reason={reason}. Cooldown {cooldown_mins}min aplicado.")
        else:
            cooldown_mins = Config.COOLDOWN_MINUTES
            
        await set_cooldown(symbol, cooldown_mins)

    async def _log_closed_trade(self, symbol: str, trade: dict, reason: str):
        """Append closed trade to trades log."""
        trade_log = await StateManager.load(TRADES_FILE, default=[])
        
        # Calculate PnL based on entry, exit (SL or TP) and size
        entry_price = trade.get("entry_price", 0.0)
        total_size = trade.get("total_size", 0.0)
        side = trade.get("side", "LONG")
        
        if reason == "TP_HIT" or trade.get("tp1_hit"):
            exit_price = trade.get("tp_price", entry_price)
        elif reason == "EXTERNAL_CLOSE":
            exit_price = trade.get("sl_price", entry_price)
        else:
            exit_price = entry_price
            
        pnl = total_size * (exit_price - entry_price) if side == "LONG" else total_size * (entry_price - exit_price)
        pnl = round(pnl, 4)
            
        trade_log.append({
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "sl_price": trade.get("sl_price"),
            "total_size": total_size,
            "tp_price": trade.get("tp_price"),
            "tp1_hit": trade.get("tp1_hit"),
            "breakeven_hit": trade.get("breakeven_hit", False),
            "trailing_active": trade.get("trailing_active", False),
            "score": trade.get("score"),
            "close_reason": reason,
            "pnl": pnl,
            "timestamp": trade.get("timestamp"),
            "close_timestamp": int(time.time())
        })
        await StateManager.save(TRADES_FILE, trade_log)

    async def _save_state(self):
        for sym, t in self.trade_state.items():
            db_trade = TradeState(
                symbol=sym,
                signal=t.get("side"),
                entry_price=t.get("entry_price"),
                sl_price=t.get("sl_price"),
                target_distance=t.get("target_distance"),
                qty=t.get("total_size"),
                filled=t.get("filled"),
                entry_order_id=t.get("entry_order_id"),
                sl_order_id=t.get("sl_order_id"),
                tp1_order_id=t.get("tp1_order_id"),
                trailing_active=t.get("trailing_active"),
                highest_price=t.get("highest_price"),
                breakeven_hit=t.get("breakeven_hit")
            )
            await save_trade(db_trade)

    async def reset_state(self):
        """Emergency Reset: Cancels all orders, closes all positions, and wipes state."""
        logger.warning("=== EMERGENCY RESET INITIATED ===")
        # Stop polling
        self.running = False
        if self._reconcile_task: self._reconcile_task.cancel()
        if self._polling_task: self._polling_task.cancel()
        if self._symbol_updater_task: self._symbol_updater_task.cancel()
        
        # Close all active positions
        real_positions = await self.client.get_positions()
        if real_positions:
            for p in real_positions:
                symbol = p.get("symbol")
                side = p.get("positionSide")
                amt = abs(float(p.get("positionAmt", 0)))
                if amt > 0 and symbol and side:
                    logger.warning(f"Reset: Canceling orders and closing {symbol} {side}")
                    await self.executor.close_position_market(symbol, side)
        
        # Clear state
        self.trade_state = {}
        await self._save_state()

        # Capture PNL Offset to normalize UI to 0.00
        try:
            income_data = await self.client.get_income(limit=1000)
            now_ms = int(time.time() * 1000)
            day_ms = 24 * 60 * 60 * 1000
            week_ms = 7 * day_ms
            month_ms = 30 * day_ms
            p_today = 0.0; p_week = 0.0; p_month = 0.0; p_total = 0.0
            for item in income_data:
                if str(item.get("incomeType")) in ["2", "4", "REALIZED_PNL", "TRADING_FEE", "FUNDING_FEE"]:
                    amt = float(item.get("income", 0.0))
                    ts = int(item.get("time", 0))
                    p_total += amt
                    if now_ms - ts <= day_ms: p_today += amt
                    if now_ms - ts <= week_ms: p_week += amt
                    if now_ms - ts <= month_ms: p_month += amt
            offset = {"pnl_today": p_today, "pnl_week": p_week, "pnl_month": p_month, "pnl_total": p_total}
            from app.constants import PNL_OFFSET_FILE
            import json
            with open(PNL_OFFSET_FILE, "w") as f:
                json.dump(offset, f)
            logger.info("Saved PNL offset to normalize dashboard to 0.")
        except Exception as e:
            logger.error(f"Error capturing PNL offset: {e}")
            
        # Save dynamic PNL start time to allow filtering stats to zero
        pnl_start_time_file = os.path.join(Config.STORAGE_DIR, "pnl_start_time.txt")
        try:
            with open(pnl_start_time_file, "w") as f:
                f.write(str(int(time.time() * 1000)))
            logger.info(f"Saved dynamic PNL start time to zero out dashboard counters.")
        except Exception as e:
            logger.error(f"Error saving dynamic PNL start time: {e}")
        
        # Wipe trades history and counters in DB
        from app.database.crud import clear_all_data
        await clear_all_data()
        logger.warning("=== RESET COMPLETED (Including History/Counters) ===")