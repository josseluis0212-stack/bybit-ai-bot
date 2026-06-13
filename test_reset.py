import asyncio
from app.core.engine import Engine
from app.exchange.bybit_client import AsyncBybitClient
from app.exchange.websocket_client import BingXWebSocket

async def test():
    client = AsyncBybitClient()
    e = Engine(client, BingXWebSocket(client))
    await e.reset_state()

asyncio.run(test())
