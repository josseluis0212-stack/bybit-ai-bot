import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from notifications.telegram_bot import telegram_notifier
import asyncio

async def test_ui():
    print("Enviando muestra de la nueva interfaz Premium a Telegram...")
    
    # 1. Test Señal
    await telegram_notifier.notify_signal_detected("BTCUSDT", "LONG", "65000.00", "64500.00", "66500.00")
    
    # 2. Test Apertura
    await telegram_notifier.notify_order_opened("ETHUSDT", "SHORT", "3500.00", "3550.00", "3400.00", "0.5", "10", 1, 10, "15.00")
    
    # 3. Test Breakeven
    await telegram_notifier.notify_breakeven("SOLUSDT", "145.00")
    
    # 4. Test Cierre (WIN)
    await telegram_notifier.notify_order_closed("BTCUSDT", "LONG", "65000.00", "66500.00", 150.00, 2.31, "45 min", "TAKE PROFIT", 50150.00)
    
    # 5. Test Cierre (LOSS)
    await telegram_notifier.notify_order_closed("ETHUSDT", "SHORT", "3500.00", "3550.00", -75.00, -1.5, "12 min", "STOP LOSS", 50075.00)

    # 6. Test Dashboard
    daily = {"total_pnl": 75.0, "pnl_pct": 0.15, "win_rate": 50.0, "count": 2}
    weekly = {"total_pnl": 450.0, "pnl_pct": 0.9, "win_rate": 65.0, "count": 14}
    monthly = {"total_pnl": 1200.0, "pnl_pct": 2.4, "win_rate": 58.0, "count": 60}
    await telegram_notifier.notify_stats_summary(daily, weekly, monthly, 60)

    print("✅ Muestras enviadas con éxito. Revisa tu Telegram.")

if __name__ == "__main__":
    asyncio.run(test_ui())
