import asyncio
from app.exchange.bybit_client import AsyncBybitClient
async def main():
    client = AsyncBybitClient()
    inc = await client.get_income(limit=5)
    print(inc)
asyncio.run(main())
