import asyncio
from api.bybit_client import bybit_client
from notifications.telegram_bot import telegram_notifier

async def main():
    print("--- INICIANDO PRUEBAS CORE ---")
    
    # Prueba Bybit
    print("\n1. Probando conexión a Bybit Testnet...")
    balance = bybit_client.get_wallet_balance()
    if balance and balance.get('retCode') == 0:
        print("[OK] CONEXION EXITOSA A BYBIT")
        list_balances = balance['result']['list'][0]['coin']
        usdt_balance = next((item for item in list_balances if item['coin'] == 'USDT'), None)
        if usdt_balance:
            print(f"[$$] Balance USDT Demo: {usdt_balance['walletBalance']}")
        else:
            print("[$$] Balance USDT Demo: 0.00")
    else:
        print(f"[ERROR] CONECTANDO A BYBIT: {balance}")

    # Prueba Tickers
    print("\n2. Probando obtención de mercados...")
    tickers = bybit_client.get_tickers()
    if tickers:
        print(f"[OK] Se obtuvieron {len(tickers)} pares USDT (Demo)")
    else:
        print("[ERROR] obteniendo tickers")
        
    # Prueba Telegram
    print("\n3. Probando envío de mensaje a Telegram...")
    success = await telegram_notifier.send_message("🚀 <b>¡Hola!</b> El servidor del bot de trading está en línea y configurado correctamente.")
    if success:
        print("[OK] MENSAJE ENVIADO A TELEGRAM")
    else:
        print("[ERROR] ENVIANDO A TELEGRAM")
        
    print("\n--- PRUEBAS FINALIZADAS ---")

if __name__ == '__main__':
    asyncio.run(main())
