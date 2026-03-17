import logging
from telegram import Bot
from telegram.constants import ParseMode
from config.settings import settings
import asyncio

logger = logging.getLogger(__name__)

class TelegramNotifier:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramNotifier, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        if settings.TELEGRAM_BOT_TOKEN:
            self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            self.chat_id = settings.TELEGRAM_CHAT_ID
        else:
            self.bot = None
            self.chat_id = None
            logger.warning("Telegram token no configurado. Las notificaciones estarán desactivadas.")

    async def send_message(self, text, parse_mode=ParseMode.HTML):
        if not self.bot or not self.chat_id or self.chat_id == "AQUI_VA_TU_CHAT_ID":
            logger.warning(f"No se pudo enviar mensaje a Telegram (Chat ID no configurado). Mensaje: {text}")
            return False
            
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
            logger.info("Mensaje enviado a Telegram.")
            return True
        except Exception as e:
            logger.error(f"Error enviando mensaje a Telegram: {e}")
            return False

    async def notify_order_opened(self, symbol, side, entry_price, sl, tp, qty, leverage, current_trades, max_trades, risk_usdt):
        emoji = "🟢" if side.upper() == "LONG" else "🔴"
        message = f"""
{emoji} <b>NUEVA OPERACIÓN ABIERTA</b>
        
<b>Par:</b> {symbol}
<b>Tipo:</b> {side.upper()}
<b>Entrada:</b> {entry_price}
<b>Stop Loss:</b> {sl}
<b>Take Profit:</b> {tp}
<b>Tamaño:</b> {qty}
<b>Apalancamiento:</b> {leverage}x
<b>Riesgo:</b> ~{risk_usdt} USDT
<b>Operaciones activas:</b> {current_trades}/{max_trades}
"""
        return await self.send_message(message)

    async def notify_order_closed(self, symbol, side, entry_price, exit_price, pnl_usdt, pnl_pct, duration, reason, balance):
        is_win = pnl_usdt > 0
        status_label = "GANADORA 💰" if is_win else "PERDEDORA 🔻"
        emoji = "✅" if is_win else "❌"
        
        message = f"""
{emoji} <b>OPERACIÓN {status_label}</b>

<b>Par:</b> {symbol}
<b>Tipo:</b> {side.upper()}
<b>Resultado:</b> {pnl_usdt:.2f} USDT ({pnl_pct:.2f}%)

<b>Entrada:</b> {entry_price}
<b>Salida:</b> {exit_price}
<b>Motivo:</b> {reason}
<b>Balance Actual:</b> {balance:.2f} USDT
"""
        return await self.send_message(message)

telegram_notifier = TelegramNotifier()
