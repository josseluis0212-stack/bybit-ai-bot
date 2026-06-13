import asyncio
import time
import json
import websockets
import hmac
import hashlib
from app.config import Config
from app.logger import logger
from app.exchange.bybit_client import AsyncBybitClient

# Replace hyphens for Bybit: BTC-USDT -> BTCUSDT
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
TF_MAP = {"5m": "5", "15m": "15", "1m": "1"}

class BybitWebSocket:
    def __init__(self, message_callback, fill_callback=None, mark_price_callback=None):
        self.ws_public_url = Config.WS_URL
        self.ws_private_url = "wss://stream-testnet.bybit.com/v5/private" if Config.DEMO_MODE else "wss://stream.bybit.com/v5/private"
        self.message_callback = message_callback
        self.fill_callback = fill_callback
        self.mark_price_callback = mark_price_callback
        self.ws_public = None
        self.ws_private = None
        self.running = False
        self._reconnect_delay = 2

    async def subscribe_mark_price(self, symbol: str):
        if self.ws_public and not self.ws_public.closed:
            symbol = symbol.replace("-", "")
            sub_msg = {"op": "subscribe", "args": [f"tickers.{symbol}"]}
            await self.ws_public.send(json.dumps(sub_msg))

    async def unsubscribe_mark_price(self, symbol: str):
        if self.ws_public and not self.ws_public.closed:
            symbol = symbol.replace("-", "")
            unsub_msg = {"op": "unsubscribe", "args": [f"tickers.{symbol}"]}
            await self.ws_public.send(json.dumps(unsub_msg))

    async def connect(self):
        self.running = True
        asyncio.create_task(self._connect_public())
        asyncio.create_task(self._connect_private())

    async def _connect_public(self):
        while self.running:
            try:
                async with websockets.connect(self.ws_public_url) as ws:
                    self.ws_public = ws
                    logger.info(f"Public WS connected to {self.ws_public_url}")
                    
                    tf_key = TF_MAP.get(Config.TIMEFRAME, "5")
                    args = [f"kline.{tf_key}.{sym}" for sym in SYMBOLS]
                    await ws.send(json.dumps({"op": "subscribe", "args": args}))
                    
                    async for message in ws:
                        if not self.running: break
                        await self._handle_public_message(message)
            except Exception as e:
                logger.error(f"Public WS Error: {e}")
            
            if self.running:
                await asyncio.sleep(self._reconnect_delay)

    async def _connect_private(self):
        while self.running:
            try:
                async with websockets.connect(self.ws_private_url) as ws:
                    self.ws_private = ws
                    logger.info(f"Private WS connected to {self.ws_private_url}")
                    
                    # Auth
                    expires = int((time.time() + 10) * 1000)
                    sig = hmac.new(Config.SECRET_KEY.encode(), f"GET/realtime{expires}".encode(), hashlib.sha256).hexdigest()
                    await ws.send(json.dumps({"op": "auth", "args": [Config.API_KEY, expires, sig]}))
                    
                    await asyncio.sleep(1)
                    await ws.send(json.dumps({"op": "subscribe", "args": ["order", "execution"]}))
                    
                    async for message in ws:
                        if not self.running: break
                        await self._handle_private_message(message)
            except Exception as e:
                logger.error(f"Private WS Error: {e}")
                
            if self.running:
                await asyncio.sleep(self._reconnect_delay)

    async def _handle_public_message(self, message):
        try:
            data = json.loads(message)
            if "topic" in data:
                topic = data["topic"]
                if topic.startswith("kline"):
                    # Map back to BingX expected format
                    symbol = topic.split(".")[-1]
                    # Format as BTC-USDT
                    bingx_sym = symbol.replace("USDT", "-USDT")
                    # data["data"][0] has start, open, high, low, close, volume
                    kline = data["data"][0]
                    fake_bingx_data = {
                        "dataType": f"{bingx_sym}@{TF_MAP.get(Config.TIMEFRAME, '5')}m",
                        "data": [{
                            "c": kline["close"],
                            "T": int(kline["start"]),
                            "v": kline["volume"]
                        }]
                    }
                    await self.message_callback(fake_bingx_data)
                elif topic.startswith("tickers") and self.mark_price_callback:
                    # Map to mark price
                    symbol = topic.split(".")[-1]
                    bingx_sym = symbol.replace("USDT", "-USDT")
                    fake_bingx_data = {
                        "dataType": f"{bingx_sym}@markPrice",
                        "data": {
                            "p": data["data"].get("markPrice", data["data"].get("lastPrice", 0))
                        }
                    }
                    await self.mark_price_callback(fake_bingx_data)
        except Exception:
            pass

    async def _handle_private_message(self, message):
        try:
            data = json.loads(message)
            if data.get("topic") == "execution" and self.fill_callback:
                for exec_data in data.get("data", []):
                    # Fake bingX fill format
                    fake_fill = {
                        "e": "ORDER_TRADE_UPDATE",
                        "data": {
                            "orderId": exec_data.get("orderId"),
                            "s": exec_data.get("symbol").replace("USDT", "-USDT"),
                            "X": "FILLED"
                        }
                    }
                    await self.fill_callback(fake_fill)
        except Exception:
            pass

    async def stop(self):
        self.running = False
        if self.ws_public: await self.ws_public.close()
        if self.ws_private: await self.ws_private.close()