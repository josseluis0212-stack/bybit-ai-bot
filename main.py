import asyncio
import logging
import os
from aiohttp import web
from config.settings import settings
from api.bybit_client import bybit_client
from database.db_manager import db_manager
from strategy.market_scanner import market_scanner
from execution_engine.executor import executor

# Configurar logging básico
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def bot_loop():
    logger.info("Iniciando Trading Bot Profesional Demo (Loop Principal)...")
    logger.info(f"Parámetros: {settings.LEVERAGE}x | Capital/Trade: {settings.TRADE_AMOUNT_USDT} USDT | Max Trades: {settings.MAX_CONCURRENT_TRADES}")
    
    # Sincronización forzada al inicio: cerrar trades "fantasma" de runs anteriores
    logger.info("Ejecutando sincronización institucional inicial con Bybit...")
    await executor.force_sync_at_startup()
    
    logger.info(f"✅ Bot Configurado: Killzones={settings.KILLZONE_FILTER}, HTF_Confluence={settings.HTF_CONFLUENCE}")
    if settings.PROXY_URL:
        logger.info(f"🌐 Conectividad vía Proxy: {settings.PROXY_URL[:15]}...")
    
    while True:
        try:
            logger.info("--- Iniciando ciclo de escaneo ---")
            
            # 0. Sincronizar y cerrar posiciones abiertas que hayan tocado SL/TP
            await executor.check_open_positions()
            
            # 1. Escanear el mercado (GLOBAL - Todas las monedas)
            signals = await market_scanner.scan_market()
            
            # 2. Procesar señales encontradas de inmediato
            if signals:
                logger.info(f"Procesando {len(signals)} señales detectadas...")
                for sig in signals:
                    # Intentar ejecutar cada señal. El ejecutor filtrará por límites y balance.
                    await executor.try_execute_signal(sig)
                    # Pequeño respiro para no saturar la API de Bybit en ráfagas
                    await asyncio.sleep(0.5)
            else:
                logger.info("Sin señales institucionales válidas en este ciclo.")
            
            logger.info("Ciclo de escaneo global completado. Pausando por 5 minutos...")
            await asyncio.sleep(300) 
            
        except Exception as e:
            logger.error(f"Error crítico en el bucle principal: {e}")
            await asyncio.sleep(60)

async def handle_status(request):
    """Devuelve el estado general del bot y balance"""
    balance_info = bybit_client.get_wallet_balance()
    active_positions = bybit_client.get_active_positions()
    
    data = {
        "status": "Running",
        "balance": balance_info['result']['list'][0]['coin'] if balance_info.get('retCode') == 0 else [],
        "active_trades_count": len(active_positions),
        "leverage": settings.LEVERAGE,
        "strategy": "Institutional SMC (OB + FVG)"
    }
    return web.json_response(data)
 
async def handle_performance(request):
    """Devuelve estadísticas de rendimiento detalladas (Diario, Semanal, Mensual, Total)"""
    from analytics.analytics_manager import analytics_manager
    stats = analytics_manager.get_dashboard_stats()
    return web.json_response(stats)

async def handle_trades(request):
    """Devuelve el historial y trades abiertos desde la DB"""
    session = db_manager.Session()
    from database.models import Trade
    all_trades = session.query(Trade).order_by(Trade.id.desc()).limit(50).all()
    
    trades_list = []
    for t in all_trades:
        trades_list.append({
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "status": t.status,
            "entry": t.entry_price,
            "exit": t.exit_price,
            "pnl_usdt": t.pnl_usdt,
            "pnl_pct": t.pnl_pct,
            "reason": t.close_reason,
            "time": t.close_time.isoformat() if t.close_time else None
        })
    session.close()
    return web.json_response(trades_list)

async def handle_health_check(request):
    return web.Response(text="Bot is running! 🚀")

async def init_web_server():
    """Inicia un servidor web con API y health check"""
    app = web.Application()
    
    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard')
    
    async def serve_index(request):
        if os.path.exists(os.path.join(dashboard_path, 'index.html')):
            return web.FileResponse(os.path.join(dashboard_path, 'index.html'))
        return web.Response(text="Dashboard index.html no encontrado.", status=404)

    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    app.router.add_get('/api/status', handle_status)
    app.router.add_get('/api/performance', handle_performance)
    app.router.add_get('/api/trades', handle_trades)
    
    app.router.add_get('/app', serve_index)
    app.router.add_get('/app/', serve_index)
    app.router.add_get('/app/index.html', serve_index)
    
    if os.path.exists(dashboard_path):
        app.router.add_static('/app', dashboard_path)
        logger.info(f"Dashboard servido desde: {dashboard_path}")
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", "10000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"✅ Servidor web activo en el puerto {port}")
    
    # Mantener el servidor funcionando indefinidamente
    while True:
        await asyncio.sleep(3600)

async def report_task():
    """Envía reportes de rendimiento programados (Diario, Semanal, Mensual) a Telegram."""
    from analytics.analytics_manager import analytics_manager
    from notifications.telegram_bot import telegram_notifier
    from datetime import datetime, timezone
    import calendar

    # ── Reporte inicial de arranque ──────────────────────────────────────────
    logger.info("Enviando reporte inicial de arranque...")
    try:
        kz_status  = "ACTIVADAS"  if settings.KILLZONE_FILTER  else "DESACTIVADAS"
        htf_status = "ACTIVADA"   if settings.HTF_CONFLUENCE    else "DESACTIVADA"
        startup_msg = (
            "🚀 <b>INSTITUTIONAL HUNTER ACTIVADO</b>\n\n"
            f"KZ: {kz_status} | HTF: {htf_status}\n"
            "Filtro PD: ACTIVADO\n\n"
            "Sistema operando 24/7.\n"
            "📬 Recibirás reportes diarios, semanales y mensuales automáticamente."
        )
        await telegram_notifier.send_message(startup_msg)
    except Exception as e:
        logger.error(f"Error en reporte inicial: {e}")

    # ── Estado de últimos envíos (para evitar duplicados) ────────────────────
    sent_daily   = None   # datetime.date del último reporte diario enviado
    sent_weekly  = None   # (year, isoweek) del último reporte semanal enviado
    sent_monthly = None   # (year, month) del último reporte mensual enviado

    while True:
        await asyncio.sleep(60)   # Revisar cada minuto (bajo costo)
        now = datetime.now(timezone.utc)

        try:
            # ── REPORTE DIARIO: todos los días a las 23:55 UTC ────────────────
            if now.hour == 23 and now.minute >= 55 and sent_daily != now.date():
                logger.info("Generando reporte DIARIO...")
                msg = analytics_manager.get_periodic_report("diario")
                if msg:
                    await telegram_notifier.send_message(msg)
                sent_daily = now.date()

            # ── REPORTE SEMANAL: domingo a las 23:30 UTC ─────────────────────
            #    isoweekday(): lunes=1 … domingo=7
            is_sunday = now.isoweekday() == 7
            this_week = (now.isocalendar().year, now.isocalendar().week)
            if is_sunday and now.hour == 23 and now.minute >= 30 and sent_weekly != this_week:
                logger.info("Generando reporte SEMANAL...")
                msg = analytics_manager.get_periodic_report("semanal")
                if msg:
                    await telegram_notifier.send_message(msg)
                sent_weekly = this_week

            # ── REPORTE MENSUAL: último día del mes a las 22:00 UTC ──────────
            last_day_of_month = calendar.monthrange(now.year, now.month)[1]
            this_month = (now.year, now.month)
            if now.day == last_day_of_month and now.hour == 22 and now.minute >= 0 and sent_monthly != this_month:
                logger.info("Generando reporte MENSUAL...")
                msg = analytics_manager.get_periodic_report("mensual")
                if msg:
                    await telegram_notifier.send_message(msg)
                sent_monthly = this_month

        except Exception as e:
            logger.error(f"Error en report_task: {e}")

async def main():
    await asyncio.gather(
        init_web_server(),
        bot_loop(),
        report_task()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
