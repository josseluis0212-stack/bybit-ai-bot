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
    async def notify_signal_detected(self, symbol, side, entry_price, sl, tp):
        emoji = "📈" if side.upper() == "LONG" else "📉"
        color = "🔵" if side.upper() == "LONG" else "🟠"
        message = f"""
{color} <b>SMC SIGNAL: {symbol}</b> {emoji}
────────────────────
<b>TIPO:</b> <code>{side.upper()}</code>
<b>ENTRADA:</b> <code>{entry_price}</code>

🎯 <b>TAKE PROFIT:</b> <code>{tp}</code>
🛡️ <b>STOP LOSS:</b> <code>{sl}</code>
────────────────────
<i>⚡ Buscando entrada institucional...</i>
"""
        return await self.send_message(message)

    async def notify_order_opened(self, symbol, side, entry_price, sl, tp, qty, leverage, current_trades, max_trades, risk_usdt):
        emoji = "🚀" if side.upper() == "LONG" else "⚡"
        color = "🔵" if side.upper() == "LONG" else "🟠"
        message = f"""
{color} <b>ORDEN EJECUTADA: {symbol}</b> {emoji}
────────────────────
<b>Dirección:</b> <code>{side.upper()}</code>
<b>Precio:</b> <code>{entry_price}</code>
<b>Tamaño:</b> <code>{qty} ({leverage}x)</code>

<b>Objetivos:</b>
└ 💰 TP: <code>{tp}</code>
└ 🛑 SL: <code>{sl}</code>

<b>Riesgo:</b> <code>{risk_usdt} USDT</code>
<b>Slots:</b> <code>{current_trades}/{max_trades}</code>
────────────────────
"""
        return await self.send_message(message)

    async def notify_order_closed(self, symbol, side, entry_price, exit_price, pnl_usdt, pnl_pct, duration, reason, balance):
        is_win = pnl_usdt > 0
        emoji = "💰" if is_win else "💸"
        color = "🟢" if is_win else "🔴"
        result_text = "PROFIT" if is_win else "LOSS"
        
        # Barra visual de resultado
        bar = "🟩🟩🟩" if is_win else "🟥🟥🟥"
        
        message = f"""
{color} <b>{result_text}: {symbol}</b> {emoji}
────────────────────
<b>{side.upper()}</b> | {reason}
<b>Entrada:</b> <code>{entry_price}</code>
<b>Salida:</b> <code>{exit_price}</code>
<b>Reloj:</b> <code>{duration}</code>

<b>RESULTADO:</b>
└ <b>PnL:</b> <code>{pnl_usdt:+.2f} USDT</code>
└ <b>ROI:</b> <code>{pnl_pct:+.2f}%</code> {bar}

<b>BALANCE:</b> <code>{balance:.2f} USDT</code>
────────────────────
"""
        return await self.send_message(message)

    async def notify_stats_summary(self, daily, weekly, monthly, last_n_count):
        # Generar mini barras para el resumen
        def get_trend(val): return "📈" if val > 0 else "📉"
        
        message = f"""
🏛️ <b>DASHBOARD: {last_n_count} TRADES</b>
────────────────────
📅 <b>DIARIO</b> {get_trend(daily['total_pnl'])}
  ├ PnL: <code>{daily['total_pnl']:+.2f} USDT</code>
  └ WR:  <code>{daily['win_rate']:.1f}%</code>

🗓️ <b>SEMANAL</b> {get_trend(weekly['total_pnl'])}
  ├ PnL: <code>{weekly['total_pnl']:+.2f} USDT</code>
  └ WR:  <code>{weekly['win_rate']:.1f}%</code>

🏛️ <b>MENSUAL</b> {get_trend(monthly['total_pnl'])}
  ├ PnL: <code>{monthly['total_pnl']:+.2f} USDT</code>
  └ WR:  <code>{monthly['win_rate']:.1f}%</code>

<b>ESTADO:</b> 🤖 <b>AUTÓNOMO</b> | 🚀 <b>V5.0</b>
────────────────────
"""
        return await self.send_message(message)

    async def notify_breakeven(self, symbol, new_sl):
        message = f"""
🛡️ <b>BREAKEVEN ACTIVADO: {symbol}</b>
────────────────────
<b>Estado:</b> <code>RIESGO CERO</code> ✅
<b>Nuevo SL:</b> <code>{new_sl}</code>

<i>El Stop Loss ha sido movido al precio de entrada para proteger tus ganancias.</i>
────────────────────
"""
        return await self.send_message(message)

    async def notify_api_error(self, error_msg, suggestion):
        message = f"""
⚠️ <b>SYSTEM CRITICAL: API ERROR</b>
────────────────────
❌ <b>ERROR:</b> <code>{error_msg}</code>
💡 <b>FIX:</b> <i>{suggestion}</i>

<b>Estatus:</b> ⛔ OPERACIONES PAUSADAS
────────────────────
"""
        return await self.send_message(message)

telegram_notifier = TelegramNotifier()
