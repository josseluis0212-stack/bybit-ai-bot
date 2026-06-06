import asyncio
import time
import json
import websockets
import gzip
from app.config import Config
from app.logger import logger
from app.exchange.bingx_client import AsyncBingXClient

SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "BNB-USDT", "DOGE-USDT", "ADA-USDT", "LINK-USDT"]
TF_MAP = {"5m": "kline_5m", "15m": "kline_15m", "1m": "kline_1m"}

class BingXWebSocket:
    """
    Production-grade WebSocket client for BingX.
    Handles market data (klines) and private order fills.
    Features: auto-reconnect, exponential backoff, ping/pong, gzip decompression.
    """
    def __init__(self, message_callback, fill_callback=None):
        self.ws_url = Config.WS_URL
        self.message_callback = message_callback
        self.fill_callback = fill_callback
        self.client = AsyncBingXClient()
        self.ws = None
        self._ping_task = None
        self.running = False
        self._reconnect_delay = 2
        self._subscribed = False

    async def _get_listen_key(self):
        try:
            res = await self.client._request("POST", "/openApi/user/auth/userDataStream", signed=True)
            if res.get("success") and res.get("data"):
                return res["data"].get("listenKey")
        except Exception as e:
            logger.error(f"Failed to get listen key: {e}")
        return None

    async def _subscribe_market_data(self, ws):
        tf_key = TF_MAP.get(Config.TIMEFRAME, "kline_5m")
        for i, symbol in enumerate(SYMBOLS):
            sub_msg = {
                "id": f"sub_kline_{i}",
                "reqType": "sub",
                "dataType": f"{symbol}@{tf_key}"
            }
            await ws.send(json.dumps(sub_msg))
            await asyncio.sleep(0.1)
        logger.info(f"Subscribed to {len(SYMBOLS)} symbols @ {Config.TIMEFRAME}")

    async def _subscribe_private_orders(self, ws, listen_key):
        if listen_key:
            sub_msg = {
                "id": "sub_orders",
                "reqType": "sub",
                "dataType": f"@listenKey"
            }
            await ws.send(json.dumps(sub_msg))
            logger.info("Subscribed to private order fill channel.")

    async def connect(self):
        self.running = True
        while self.running:
            try:
                listen_key = await self._get_listen_key()
                url = f"{self.ws_url}?listenKey={listen_key}" if listen_key else self.ws_url

                async with websockets.connect(
                    url,
                    ping_interval=None,
                    close_timeout=5,
                    max_size=10 * 1024 * 1024
                ) as ws:
                    self.ws = ws
                    self._reconnect_delay = 2  # Reset backoff on successful connect
                    logger.info(f"WebSocket connected: {url[:50]}...")

                    await self._subscribe_market_data(ws)
                    if listen_key:
                        await self._subscribe_private_orders(ws, listen_key)

                    self._ping_task = asyncio.create_task(self._keep_alive(ws))

                    async for message in ws:
                        if not self.running:
                            break
                        await self._handle_raw_message(message)

            except websockets.exceptions.ConnectionClosedOK:
                logger.warning("WebSocket closed cleanly. Reconnecting...")
            except websockets.exceptions.ConnectionClosedError as e:
                logger.error(f"WebSocket connection error: {e}. Reconnecting in {self._reconnect_delay}s...")
            except Exception as e:
                logger.error(f"WebSocket unexpected error: {e}. Reconnecting in {self._reconnect_delay}s...")

            if self.running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)  # Exponential backoff cap 60s

    async def _handle_raw_message(self, message):
        try:
            if isinstance(message, bytes):
                try:
                    message = gzip.decompress(message).decode('utf-8')
                except Exception:
                    message = message.decode('utf-8')

            if message in ("Ping", "ping"):
                if self.ws and not self.ws.closed:
                    await self.ws.send("Pong")
                return

            data = json.loads(message)

            if data.get("ping"):
                if self.ws and not self.ws.closed:
                    await self.ws.send(json.dumps({"pong": data["ping"]}))
                return

            # Detect order fill events (private channel)
            if data.get("e") in ("ORDER_TRADE_UPDATE", "executionReport") and self.fill_callback:
                await self.fill_callback(data)
                return

            # Route to market data callback
            await self.message_callback(data)

        except json.JSONDecodeError:
            pass  # Ignore non-JSON messages
        except Exception as e:
            logger.error(f"Error handling WS message: {e}")

    async def _keep_alive(self, ws):
        while self.running:
            try:
                if ws and not ws.closed:
                    await ws.send(json.dumps({"ping": int(time.time() * 1000)}))
                await asyncio.sleep(20)
            except Exception:
                break

    async def stop(self):
        self.running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self.ws and not self.ws.closed:
            await self.ws.close()
        logger.info("WebSocket stopped.")