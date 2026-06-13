import asyncio
from app.exchange.bybit_client import AsyncBybitClient
async def main():
    client = AsyncBybitClient()
    p = await client.get_contract_precisions()
    print('QAIT-USDT:', p.get('QAIT-USDT'))
    print('1000BONK-USDT:', p.get('1000BONK-USDT'))
asyncio.run(main())
