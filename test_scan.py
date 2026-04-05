import asyncio
import yaml
from core.bybit_client import BybitClient
from strategy.execution_engine import ExecutionEngine
from unittest.mock import MagicMock

async def main():
    with open('config/config.yaml', 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    
    client = BybitClient(testnet=False, demo=True)
    telegram_mock = MagicMock()
    
    engine = ExecutionEngine(client, None, None, config, telegram_mock)
    
    simbolos = config.get('simbolos', [])
    print(f'Escanendo mercado con estrategia HYPER SCALPER...')
    
    for symbol in simbolos:
        print(f'Analizando {symbol} (1m)...')
        signal = await engine.check_signal(symbol)
        if signal:
            print(f'  [!!!] SEÑAL ENCONTRADA en {symbol}: {signal}')
        else:
            print(f'  [ok] Sin señal en {symbol}')

if __name__ == '__main__':
    asyncio.run(main())
