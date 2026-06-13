import asyncio
from app.exchange.bybit_client import AsyncBybitClient
async def main():
    client = AsyncBybitClient()
    res = await client._request('GET', '/openApi/swap/v2/quote/contracts', signed=False)
    if res and 'data' in res:
        print(res['data'][0])
asyncio.run(main())
