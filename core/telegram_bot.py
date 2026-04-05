import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

class TelegramBot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    async def send_message(self, message):
        if not self.token or not self.chat_id:
            print(f"Telegram no configurado. Mensaje: {message}")
            return
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if response.status != 200:
                        print(f"Error enviando mensaje a Telegram: {await response.text()}")
        except Exception as e:
            print(f"Excepción al enviar mensaje a Telegram: {e}")
