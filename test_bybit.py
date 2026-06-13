import asyncio
import os
import sys
# Ensure app module can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.exchange.bybit_client import AsyncBybitClient
from app.config import Config

async def main():
    print(f"Using API KEY: {Config.API_KEY[:5]}***")
    client = AsyncBybitClient()
    res = await client.get_positions()
    for p in res:
        print(f"Symbol: {p['symbol']}, entryPrice: {p['entryPrice']}, unrealizedProfit: {p['unrealizedProfit']}, posAmt: {p['positionAmt']}")
    await client.session.close()

if __name__ == "__main__":
    asyncio.run(main())
