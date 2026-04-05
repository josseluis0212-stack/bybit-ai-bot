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
