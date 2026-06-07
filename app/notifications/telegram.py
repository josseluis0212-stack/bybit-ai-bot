import asyncio
import httpx
from app.config import Config
from app.core.logger import get_logger

logger = get_logger(__name__)

class TelegramNotifier:
    BASE_URL = "https://api.telegram.org"

    def __init__(self):
        self.token = Config.TELEGRAM_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.enabled = Config.USE_TELEGRAM and bool(self.token) and bool(self.chat_id)

    async def send_message(self, text: str):
        if not self.enabled:
            return
            
        url = f"{self.BASE_URL}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except Exception as e:
            logger.error(f"[Telegram] Error enviando mensaje: {e}")

    async def notify_open(self, symbol: str, side: str, entry_price: float, qty: float, strategy: str = ""):
        icon = "🟢" if side.lower() == "long" else "🔴"
        strat_str = f"🤖 Estrategia: <code>{strategy}</code>\n" if strategy else ""
        text = (
            f"{icon} <b>NUEVA OPERACIÓN {side.upper()}</b>\n"
            f"📌 <b>{symbol}</b> (BingX)\n"
            f"💰 Entrada: <code>{entry_price:.4f}</code>\n"
            f"📦 Tamaño: <code>{qty}</code>\n"
            f"{strat_str}"
        )
        await self.send_message(text)

    async def notify_close(self, symbol: str, side: str, pnl: float = 0.0, reason: str = "Cierre"):
        icon = "✅" if pnl >= 0 else "❌"
        sign = "+" if pnl > 0 else ""
        text = (
            f"{icon} <b>CIERRE {side.upper()}</b>\n"
            f"📌 <b>{symbol}</b> (BingX)\n"
            f"📋 Razón: {reason}\n"
            f"💵 PnL: <b>{sign}{pnl:.2f} USDT</b>"
        )
        await self.send_message(text)

notifier = TelegramNotifier()
