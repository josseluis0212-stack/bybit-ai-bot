import asyncio
import logging
import sys
import os

# Añadir el directorio actual al path para importar módulos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from analytics.analytics_manager import analytics_manager
from notifications.telegram_bot import telegram_notifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_all_reports():
    print("\n" + "="*55)
    print("  PRUEBA DE REPORTES - Bot Bybit")
    print("="*55)

    tests = [
        ("Reporte Acumulado",   analytics_manager.get_full_report,            ()),
        ("Reporte DIARIO",      analytics_manager.get_periodic_report,        ("diario",)),
        ("Reporte SEMANAL",     analytics_manager.get_periodic_report,        ("semanal",)),
        ("Reporte MENSUAL",     analytics_manager.get_periodic_report,        ("mensual",)),
        ("Ultimas 10 ops",      analytics_manager.get_summary_n_trades,       (10,)),
    ]

    for i, (name, fn, args) in enumerate(tests, 1):
        print(f"\n[{i}/{len(tests)}] {name}...")
        try:
            report = fn(*args)
            if report:
                print(f"   Mensaje generado ({len(report)} chars)")
                success = await telegram_notifier.send_message(report)
                print(f"   Enviado a Telegram: {'OK' if success else 'FALLO'}")
            else:
                print("   Sin datos para este periodo.")
        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n" + "="*55)
    print("  PRUEBAS FINALIZADAS")
    print("="*55 + "\n")

if __name__ == "__main__":
    asyncio.run(test_all_reports())
