import os
import sys
# Agregar el directorio raíz al path para encontrar los módulos
sys.path.append(os.getcwd())

from dotenv import load_dotenv
from core.bybit_client import BybitClient
import yaml

def test_connection():
    load_dotenv()
    
    print("--- OPERACIÓN DE PRUEBA: BYBIT DEMO TRADING ---")
    client = BybitClient(testnet=False, demo=True)
    
    balance = client.get_balance()
    print(f"Balance detectado: {balance} USDT")
    
    if balance > 0:
        symbol = "BTCUSDT"
        print(f"Abriendo operación de prueba en {symbol} (LONG 0.001)...")
        
        # Intentar colocar orden
        response = client.place_order(
            symbol=symbol,
            side="Buy",
            order_type="Market",
            qty=0.001
        )
        
        if response and response['retCode'] == 0:
            print("✅ ¡OPERACIÓN EXITOSA!")
            print(f"Orden ID: {response['result']['orderId']}")
            print("Verifica tu panel de Bybit Demo, deberías ver la posición abierta.")
        else:
            print(f"❌ Error al operar: {response['retMsg'] if response else 'Sin respuesta'}")
    else:
        print("❌ Error: No se detectó balance suficiente.")

if __name__ == "__main__":
    test_connection()
