import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.exchange.bybit_client import AsyncBybitClient

async def main():
    client = AsyncBybitClient()
    res = await client._request('GET', '/v5/position/list', {'category': 'linear', 'settleCoin': 'USDT'}, signed=True)
    if res and res.get("data"):
        for p in res["data"].get("list", []):
            print(f"Sym: {p.get('symbol')}, idx: {p.get('positionIdx')}, side: {p.get('side')}, size: {p.get('size')}, unrealisedPnl: {p.get('unrealisedPnl')}")
    else:
        print(f"Error: {res}")
    await client.session.close()

if __name__ == "__main__":
    asyncio.run(main())
