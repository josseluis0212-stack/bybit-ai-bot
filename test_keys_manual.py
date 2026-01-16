from pybit.unified_trading import HTTP
import time

api_key = "CERBQyqyqgFq8SzKEi"
api_secret = "ZPu2qLCzoLPp9ncJmZs9ETaQ82YKN8LXriaf"

print("--- PROBANDO CLAVES EN MODO DEMO ---")
try:
    session = HTTP(
        testnet=False, 
        demo=True,
        api_key=api_key,
        api_secret=api_secret
    )
    
    # 1. Probar conexión básica (Hora del servidor)
    print("1. Conectando a Bybit...")
    t = session.get_server_time()
    print("   [OK] Conexión establecida.")

    # 2. Probar Permisos (Balance)
    print("2. Verificando Balance...")
    balance_data = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    
    if balance_data['retCode'] == 0:
        balance = balance_data['result']['list'][0]['coin'][0]['walletBalance']
        print(f"   [OK] Balance encontrado: {balance} USDT")
        print("   ✅ LAS CLAVES FUNCIONAN CORRECTAMENTE.")
    else:
        print(f"   [ERROR] Fallo al leer balance: {balance_data['retMsg']}")
        print("   ❌ POSIBLE FALLO: Permisos incorrectos o claves equivocadas.")

except Exception as e:
    print(f"   [ERROR CRÍTICO] Excepción: {e}")
