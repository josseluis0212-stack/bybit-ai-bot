import asyncio
import logging
from api.bybit_client import bybit_client
from execution_engine.executor import executor
from config.settings import settings

logging.basicConfig(level=logging.INFO)

async def test_order():
    settings.BYBIT_DEMO = True
    print("Obteniendo info del instrumento...")
    info = bybit_client.get_instruments_info()
    
    symbol = "TAIKOUSDT"
    if info and symbol in info:
        print(f"Propiedades de {symbol}: {info[symbol]}")
        
    signal_data = {
        'symbol': symbol,
        'signal': 'LONG',
        'entry_price': 1.11953,  # Precio ficticio en zona actual
        'sl': 1.11,
        'tp': 1.13
    }
    
    print("\nSimulando señal...")
    result = await executor.try_execute_signal(signal_data)
    print(f"\nResultado final: {result}")

if __name__ == "__main__":
    asyncio.run(test_order())
