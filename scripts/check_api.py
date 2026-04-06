import asyncio
import logging
import sys
import os
from pybit.unified_trading import HTTP
from dotenv import load_dotenv

# Ensure we are in the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

# Logger setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_bybit_credentials():
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    is_demo = os.getenv("BYBIT_DEMO", "True").lower() == "true"
    
    print("\n" + "="*50)
    print(f"📊 DIAGNÓSTICO DE CREDENCIALES BYBIT")
    print("="*50)
    print(f"Llave API:  {api_key[:6]}...{api_key[-4:] if api_key else 'VACÍA'}")
    print(f"Entorno:    {'MODO DEMO (Simulación)' if is_demo else 'MODO REAL (Mainnet)'}")
    print("-" * 50)

    session = HTTP(
        demo=is_demo,
        api_key=api_key,
        api_secret=api_secret
    )

    try:
        # Prueba 1: Get Balance
        response = session.get_wallet_balance(accountType="UNIFIED")
        if response.get("retCode") == 0:
            print("[✅] CONEXIÓN EXITOSA!")
            coins = response['result']['list'][0]['coin']
            usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
            if usdt:
                print(f"    Saldo disponible: {float(usdt['walletBalance']):.2f} USDT")
            else:
                print("    Saldo: Conectado, pero no se encontró balance en USDT.")
        else:
            ret_code = response.get("retCode")
            msg = response.get("retMsg", "Error desconocido")
            print(f"[❌] ERROR DE CONEXIÓN (Código {ret_code})")
            print(f"    Mensaje: {msg}")
            
            if ret_code == 10003:
                print("\n💡 SUGERENCIA: La llave API es inválida para este entorno.")
                print("   Si estás en MODO DEMO, asegúrate de haber creado las llaves")
                print("   DENTRO de la interfaz de 'Trading de Prueba' de Bybit.")
            elif ret_code == 10005:
                print("\n💡 SUGERENCIA: IP no permitida o error de firma.")
                
    except Exception as e:
        if "401" in str(e):
             print("[❌] ERROR 401: No autorizado.")
             print("    Esto sucede cuando la llave no corresponde al servidor (Demo vs Real).")
        else:
             print(f"[❌] EXCEPCIÓN: {e}")

    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(check_bybit_credentials())
