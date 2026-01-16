from core.telegram_bot import TelegramBot
import os
from dotenv import load_dotenv

load_dotenv(override=True)

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

print("--- DIAGNOSTICO LOCAL ---")
if token:
    print("TOKEN: SI")
else:
    print("TOKEN: NO")

if chat_id:
    print("CHAT_ID: SI")
else:
    print("CHAT_ID: NO")

if not token or not chat_id:
    print("\n[ERROR] Faltan claves en .env local.")
else:
    print("\n[INFO] Intentando enviar mensaje...")
    bot = TelegramBot()
    bot.send_message("ALERTA DE PRUEBA: Sistema funcionando.")
    print("[OK] Mensaje enviado a la API.")
