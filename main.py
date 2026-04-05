<<<<<<< HEAD
import asyncio
import logging
import os
from aiohttp import web
from config.settings import settings
from strategy.market_scanner import market_scanner
from execution_engine.executor import executor

# Configurar logging básico
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

import aiohttp

async def render_heartbeat():
    """
    Servicio de Supervivencia: Evita que Render apague la instancia por inactividad.
    Realiza un self-ping cada 10 minutos.
    """
    port = os.environ.get("PORT", "10000")
    url = f"http://localhost:{port}/health"
    await asyncio.sleep(60) # Esperar a que el servidor inicie
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.info("💓 Heartbeat: Sistema activo y saludable.")
                    else:
                        logger.warning(f"💓 Heartbeat: Respuesta inesperada {response.status}")
            except Exception as e:
                logger.error(f"💓 Heartbeat Error: {e}")
            
            await asyncio.sleep(600) # 10 minutos

async def bot_loop():
    logger.info("🚀 INICIANDO HYPER-QUANT V3 (MODO AUTÓNOMO)...")
    logger.info(f"Estrategia: Vectorized Mean Reversion (1m) | Apalancamiento: 10x | Margen: $50")
    
    while True:
        start_time = time.time()
        try:
            logger.info("--- [Ciclo de Escaneo de Alta Frecuencia] ---")
            
            # 0. Sincronizar y aplicar Time-Exits
            await executor.check_open_positions()
            
            # 1. Escanear el mercado completo
            signals = await market_scanner.scan_market()
            
            # 2. Procesar señales
            if signals:
                logger.info(f"Procesando {len(signals)} señales encontradas...")
                for sig in signals:
                    await executor.try_execute_signal(sig)
            
            # Cálculo de tiempo para mantener el ciclo cerca de 60s
            elapsed = time.time() - start_time
            sleep_time = max(1, 60 - elapsed)
            
            logger.info(f"Ciclo completado en {elapsed:.1f}s. Durmiendo {sleep_time:.1f}s...")
            await asyncio.sleep(sleep_time) 
            
        except Exception as e:
            logger.error(f"Error crítico en Hyper-Quant Loop: {e}")
            await asyncio.sleep(60)

async def handle_health_check(request):
    return web.Response(text="Hyper-Quant V3 is alive! 🚀")

async def init_web_server():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", "10000"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Servidor de supervivencia iniciado en el puerto {port}")

async def main():
    # Iniciamos el servidor, el bot y el heartbeat concurrentemente
    await asyncio.gather(
        init_web_server(),
        render_heartbeat(),
        bot_loop()
    )

if __name__ == '__main__':
    import time # Requerido para start_time
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
=======
import time
import asyncio
import threading
import yaml
from core.bybit_client import BybitClient
from core.telegram_bot import TelegramBot
from core.risk_manager import RiskManager
from core.memory_manager import MemoryManager
from strategy.execution_engine import ExecutionEngine
from dashboard.app import start_dashboard, update_ui, send_log, bot_data

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

async def bot_loop():
    config = load_config()
    print("--- INICIANDO BOT DE TRADING IA (BYBIT) ---")
    
    # Variables de seguimiento de operaciones
    prev_positions = {} # symbol -> position_data
    total_pnl = 0.0
    win_count = 0
    loss_count = 0
    closed_trades = []
    trades_cerrados_ciclo = 0
    
    # Inicializar componentes
    client = BybitClient(
        testnet=config.get('bybit', {}).get('testnet', False),
        demo=config.get('bot', {}).get('modo_demo', True)
    )
    telegram = TelegramBot()
    risk_manager = RiskManager(config)
    memory_manager = MemoryManager()
    engine = ExecutionEngine(client, risk_manager, memory_manager, config, telegram)
    
    await telegram.send_message(
        "🚀 *SISTEMA IA INICIADO* 🚀\n\n"
        "✅ *BOT IA:* Optimización 24/7 Activa\n"
        "📡 *Escaneo:* Paralelo Asíncrono\n"
        "🐺 *Cazando en Hugging Face...*"
    )
    
    # *** BORRAR HISTORIAL AL ARRANCAR (pizarra limpia) ***
    total_pnl = 0.0
    win_count = 0
    loss_count = 0
    closed_trades = []
    trades_cerrados_ciclo = 0
    bot_data["total_pnl"] = 0.0
    bot_data["win_count"] = 0
    bot_data["loss_count"] = 0
    bot_data["closed_trades"] = []
    print("✅ Historial PnL reseteado - Pizarra limpia.")
    
    semaphore = asyncio.Semaphore(15)

    async def analyze_and_execute(symbol):
        async with semaphore:
            if not bot_data["is_running"]: return
            await engine.execute_trade(symbol)
    
    try:
        while True:
            if not bot_data["is_running"]:
                print("Bot en pausa (esperando inicio desde Dashboard)...")
                await asyncio.sleep(5)
                continue

            # Recargar configuración para aplicar cambios desde la UI
            with open("config/config.yaml", "r") as f:
                config = yaml.safe_load(f)
            engine.config = config
            engine.risk_manager.config = config
            engine.trend_analyzer.config = config

            balance = client.get_balance()
            btc_trend = engine.trend_analyzer.analyze_btc_filter()
            posiciones = client.get_active_positions()
            
            # Detectar operaciones cerradas
            current_symbols = {p['symbol'] for p in posiciones}
            for symbol, prev_p in list(prev_positions.items()):
                if symbol not in current_symbols:
                    # La posición se cerró. Intentamos obtener el PnL realizado.
                    # Por ahora usamos el último PnL no realizado conocido o una estimación.
                    # En una versión más avanzada, consultaríamos el historial de trades de Bybit.
                    raw_pnl = prev_p.get('unrealisedPnl', 0)
                    try:
                        pnl = float(raw_pnl) if raw_pnl is not None and str(raw_pnl).strip() != "" else 0.0
                    except (ValueError, TypeError):
                        pnl = 0.0
                    
                    total_pnl += pnl
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    
                    trade_info = {
                        "symbol": symbol,
                        "side": prev_p['side'],
                        "pnl": f"{pnl:.2f}",
                        "time": time.strftime("%H:%M:%S")
                    }
                    closed_trades.insert(0, trade_info)
                    if len(closed_trades) > 10: closed_trades.pop()
                    
                    send_log(f"Operación CERRADA en {symbol}: PnL {pnl:.2f} USDT", "log-success" if pnl > 0 else "log-error")
                    
                    # Alertar cierre individual a Telegram
                    estado_trade = "✅ OPERACIÓN GANADORA 💰" if pnl > 0 else "❌ OPERACIÓN PERDEDORA 🩸"
                    await telegram.send_message(
                        f"{estado_trade}\n\n"
                        f"Par: {symbol}\n"
                        f"Lado: {prev_p['side']}\n"
                        f"PnL Final: {pnl:.2f} USDT\n\n"
                        f"PnL Acumulado Sesión: {total_pnl:.2f} USDT"
                    )
                    
                    trades_cerrados_ciclo += 1
                    report_limit = int(config.get('telegram', {}).get('reporte_estadisticas_cada_n_trades', 10))
                    
                    # Reporte de ciclo cada N operaciones
                    if trades_cerrados_ciclo >= report_limit:
                        total = win_count + loss_count
                        winrate = (win_count / total) * 100 if total > 0 else 0
                        await telegram.send_message(
                            f"📊 *REPORTE DE CICLO SCALPER* 📊\n\n"
                            f"Ciclo completado: {report_limit} trades.\n\n"
                            f"🏆 Ganados: {win_count}\n"
                            f"💀 Perdidos: {loss_count}\n"
                            f"🎯 Win Rate: {winrate:.1f}%\n"
                            f"💸 PnL Total Sesión: {total_pnl:.2f} USDT"
                        )
                        trades_cerrados_ciclo = 0
                        
                    del prev_positions[symbol]
            
            # Actualizar posiciones previas
            for p in posiciones:
                prev_positions[p['symbol']] = p

            # Actualizar UI
            update_ui({
                "balance": f"{balance:.2f}",
                "points": memory_manager.data["puntos_aprendizaje"],
                "btc_trend": btc_trend,
                "positions": posiciones,
                "total_pnl": f"{total_pnl:.2f}",
                "win_count": win_count,
                "loss_count": loss_count,
                "closed_trades": closed_trades
            })
            
            send_log(f"Sincronización completa. Balance: {balance} USDT")
            
            # Obtener todos los símbolos del mercado
            pares = client.get_all_symbols()
            if not pares:
                send_log("No se encontraron pares USDT. Reintentando...", "log-error")
                await asyncio.sleep(10)
                continue
                
            send_log(f"🚀 ESCANEO GLOBAL: {len(pares)} monedas en paralelo", "log-success")
            
            # Ejecutar escaneo paralelo
            tasks = [analyze_and_execute(par) for par in pares]
            await asyncio.gather(*tasks)
            
            send_log("Ciclo de escaneo completado. Esperando 1 minuto...", "log-warning")
            await asyncio.sleep(60)
            
    except KeyboardInterrupt:
        print("\nBot detenido por el usuario.")
        telegram.send_message("⚠️ *Bot Detenido Manualmente*")
    except Exception as e:
        print(f"Error crítico en bot_loop: {e}")
        await telegram.send_message(f"⚠️ *ERROR CRÍTICO:* {e}")
        await asyncio.sleep(10)

def start_bot_thread():
    asyncio.run(bot_loop())

if __name__ == "__main__":
    # Iniciar bot en hilo separado
    threading.Thread(target=start_bot_thread, daemon=True).start()
    
    # Iniciar el Dashboard en el hilo principal
    from dashboard.app import run_server
    print("Servidor iniciando en el hilo principal...")
    run_server()
>>>>>>> 877fcfbfb4560be4c8c22641f46a99a14f54d375
