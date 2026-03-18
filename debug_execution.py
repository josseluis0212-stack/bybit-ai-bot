import asyncio
import logging
from api.bybit_client import bybit_client
from execution_engine.executor import executor
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_live_signal():
    print("--- DEBUG: FORZANDO EJECUCIÓN DE SEÑAL EN VIVO ---")
    
    # 1. Simular una de las señales que encontraste
    # ACTUSDT fue la detectada que no abrió
    symbol = "ACTUSDT"
    
    print(f"\n1. Obteniendo precio actual para {symbol}...")
    tickers = bybit_client.get_tickers()
    ticker = next((t for t in tickers if t['symbol'] == symbol), None)
    
    if not ticker:
        print(f"[ERROR] No se encontró el ticker para {symbol}")
        return

    price = float(ticker['lastPrice'])
    print(f"[OK] Precio actual: {price}")

    # 2. Crear data de señal falsa basada en la estrategia
    # LONG: Entry actual, SL 2% abajo, TP 4% arriba
    signal_data = {
        "symbol": symbol,
        "signal": "LONG",
        "entry_price": price,
        "sl": price * 0.98,
        "tp": price * 1.04,
        "info": "DEBUG FORCE SIGNAL"
    }

    print("\n2. Intentando ejecutar señal a través del ejecutor real...")
    # El ejecutor hace: check limits -> check balance -> calculate qty -> place order
    success = await executor.try_execute_signal(signal_data)
    
    if success:
        print(f"\n[ÉXITO] La orden para {symbol} se colocó correctamente.")
    else:
        print(f"\n[FALLO] El ejecutor rechazó o falló al colocar la orden.")
        print("Revisa los logs de arriba para ver el motivo (límite alcanzado, balance insuficiente, etc.)")

    # 3. Verificar Balance disponible para asegurar que no es ese el problema
    print("\n3. Verificando balance de billetera...")
    balance = bybit_client.get_wallet_balance()
    print(f"Respuesta Balance: {balance}")

if __name__ == '__main__':
    asyncio.run(debug_live_signal())
