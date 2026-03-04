"""
Script de Prueba Rapida de Conexion
- Verifica la conexion a Bybit Demo
- Verifica la conexion a Telegram
- Verifica que la base de datos se crea correctamente
"""
import asyncio
import logging
import sys

# Forzar UTF-8 en stdout para manejar emojis en Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def test_bybit_connection():
    print("\n" + "="*50)
    print("PRUEBA 1: CONEXION A BYBIT (DEMO)")
    print("="*50)
    try:
        from api.bybit_client import bybit_client
        balance = bybit_client.get_wallet_balance()
        if balance and balance.get('retCode') == 0:
            coins = balance['result']['list'][0]['coin']
            usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
            if usdt:
                print(f"[OK] Conexion a Bybit EXITOSA!")
                print(f"   Balance Disponible: {float(usdt['walletBalance']):.2f} USDT")
                print(f"   Balance Equity:     {float(usdt.get('equity', 0)):.2f} USDT")
            else:
                print("[OK] Conexion a Bybit ok, pero no se encontro saldo USDT.")
        else:
            print(f"[ERROR] Error en Bybit: {balance}")
    except Exception as e:
        print(f"[ERROR] Excepcion al conectar a Bybit: {e}")

async def test_telegram_connection():
    print("\n" + "="*50)
    print("PRUEBA 2: CONEXION A TELEGRAM")
    print("="*50)
    try:
        from notifications.telegram_bot import telegram_notifier
        msg = "<b>Bot de Trading PRO</b> - Prueba de conexion exitosa [OK]\n\nEl bot esta configurado y listo para operar en modo Demo."
        success = await telegram_notifier.send_message(msg)
        if success:
            print("[OK] Mensaje enviado a Telegram correctamente.")
        else:
            print("[ERROR] No se pudo enviar el mensaje (revisa token y chat_id en .env)")
    except Exception as e:
        print(f"[ERROR] Excepcion al conectar a Telegram: {e}")

def test_database():
    print("\n" + "="*50)
    print("PRUEBA 3: BASE DE DATOS LOCAL (SQLite)")
    print("="*50)
    try:
        from database.db_manager import db_manager
        count = db_manager.get_open_trades_count()
        print(f"[OK] Base de datos inicializada correctamente.")
        print(f"   Operaciones abiertas actualmente: {count}")
    except Exception as e:
        print(f"[ERROR] Error en base de datos: {e}")

def test_config():
    print("\n" + "="*50)
    print("PRUEBA 4: CONFIGURACION SETTINGS")
    print("="*50)
    try:
        from config.settings import settings
        print(f"[OK] Settings cargado correctamente.")
        print(f"   BYBIT_API_KEY:  {settings.BYBIT_API_KEY[:6]}...{settings.BYBIT_API_KEY[-4:] if settings.BYBIT_API_KEY else 'NO CONFIGURADA'}")
        print(f"   BYBIT_DEMO:     {settings.BYBIT_DEMO}")
        print(f"   LEVERAGE:       {settings.LEVERAGE}x")
        print(f"   TRADE_AMOUNT:   {settings.TRADE_AMOUNT_USDT} USDT")
        print(f"   MAX_TRADES:     {settings.MAX_CONCURRENT_TRADES}")
        tg = settings.TELEGRAM_BOT_TOKEN
        print(f"   TELEGRAM_TOKEN: {tg[:8]}...{tg[-4:] if tg else 'NO CONFIGURADO'}")
    except Exception as e:
        print(f"[ERROR] Error cargando settings: {e}")

async def main():
    print("\n" + "="*50)
    print("INICIANDO PRUEBAS DE CONFIGURACION DEL BOT...")
    print("="*50)
    test_config()
    await test_bybit_connection()
    await test_telegram_connection()
    test_database()
    print("\n" + "="*50)
    print("[LISTO] TODAS LAS PRUEBAS COMPLETADAS")
    print("="*50 + "\n")

if __name__ == '__main__':
    asyncio.run(main())
