import eventlet
eventlet.monkey_patch()

import time
import yaml
import os
from core.bybit_client import BybitClient
from core.telegram_bot import TelegramBot
from core.risk_manager import RiskManager
from core.memory_manager import MemoryManager
from strategy.execution_engine import ExecutionEngine
from strategy.grid_analyzer import GridAnalyzer
from dashboard.app import start_dashboard, update_ui, send_log, bot_data

def send_combined_stats(memory_manager, telegram):
    daily = memory_manager.get_periodic_statistics(1)
    weekly = memory_manager.get_periodic_statistics(7)
    monthly = memory_manager.get_periodic_statistics(30)
    
    msg = "📊 *REPORTES DE RENDIMIENTO*\n━━━━━━━━━━━━━━━━━━\n"
    
    if daily:
        msg += f"📅 *HOY:* {daily['win_rate']:.1f}% WR | {daily['pnl']:.2f} USDT\n"
    if weekly:
        msg += f"📅 *SEMANA:* {weekly['win_rate']:.1f}% WR | {weekly['pnl']:.2f} USDT\n"
    if monthly:
        msg += f"📅 *MES:* {monthly['win_rate']:.1f}% WR | {monthly['pnl']:.2f} USDT\n"
    
    msg += "━━━━━━━━━━━━━━━━━━"
    telegram.send_message(msg)

def load_config():
    if not os.path.exists("config/config.yaml"):
        print("❌ ERROR CRÍTICO: No se encuentra config/config.yaml")
        print("Asegúrate de que el archivo exista y no esté ignorado por git.")
        # Retornar una config vacía o por defecto para evitar crash inmediato, 
        # o dejar que falle pero con mensaje claro.
        return {} 
        
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

def bot_loop():
    config = load_config()
    VERSION = "v2.6 Premium"
    print(f"--- INICIANDO BOT DE TRADING IA {VERSION} (BYBIT) ---")
    
    # Variables de seguimiento de operaciones
    prev_positions = {} # symbol -> position_data
    total_pnl = 0.0
    win_count = 0
    loss_count = 0
    closed_trades = []
    
    # Inicializar componentes
    client = BybitClient(
        testnet=config['trading'].get('testnet', False),
        demo=config['trading'].get('demo', True)
    )
    telegram = TelegramBot()
    risk_manager = RiskManager(config)
    memory_manager = MemoryManager()
    engine = ExecutionEngine(client, risk_manager, memory_manager, config, telegram)
    grid_engine = GridAnalyzer(client, config, telegram)
    
    balance = client.get_balance()
    mode = "Demo Trading" if config['trading'].get('demo', True) else "Cuenta REAL"
    
    telegram.send_message(f"🚀 *BOT IA {VERSION} OPERATIVO*\n💰 Balance: {balance:.2f} USDT\n⚙️ Modo: {mode}")
    telegram.send_message(f"✅ *BOT GRID {VERSION} OPERATIVO*")
    telegram.send_message("🤖 *Sincronización completa.* Iniciando análisis de mercado...")
    
    try:
        while True:
            if not bot_data["is_running"]:
                print("Bot en pausa (esperando inicio desde Dashboard)...")
                time.sleep(5)
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
                    # Obtener PnL real desde Bybit (Module 9/11)
                    closed_info = client.get_last_closed_pnl(symbol)
                    pnl = float(closed_info['closedPnl']) if closed_info else 0.0
                    win = pnl > 0
                    
                    total_pnl += pnl
                    if win: win_count += 1
                    else: loss_count += 1
                    
                    # Actualizar Memoria (Módulo 9)
                    memory_manager.update_coin_stats(symbol, win, pnl, prev_p['side'])
                    
                    trade_info = {
                        "symbol": symbol,
                        "side": prev_p['side'],
                        "pnl": f"{pnl:.2f}",
                        "time": time.strftime("%H:%M:%S")
                    }
                    closed_trades.insert(0, trade_info)
                    if len(closed_trades) > 10: closed_trades.pop()
                    
                    send_log(f"Operación CERRADA en {symbol}: PnL {pnl:.2f} USDT", "log-success" if pnl > 0 else "log-error")
                    
                    # Notificar a Telegram (Módulo 10)
                    emoji = "🟢" if win else "🔴"
                    res_txt = "GANANCIA" if win else "PÉRDIDA"
                    telegram.send_message(
                        f"{emoji} *BOT IA: OPERACIÓN CERRADA*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 *Moneda:* {symbol}\n"
                        f"🏁 *Resultado:* {res_txt}\n"
                        f"💰 *PnL Real:* {pnl:.2f} USDT\n"
                        f"━━━━━━━━━━━━━━━━━━"
                    )
                    send_combined_stats(memory_manager, telegram)
                    
                    del prev_positions[symbol]
            
            # Actualizar posiciones previas
            for p in posiciones:
                prev_positions[p['symbol']] = p

            # Actualizar UI
            update_ui({
                "balance": f"{balance:.2f}",
                "points": memory_manager.data["puntos_aprendizaje"],
                "btc_trend": f"{btc_trend} ({btc_daily_trend})",
                "positions": posiciones,
                "total_pnl": f"{total_pnl:.2f}",
                "win_count": win_count,
                "loss_count": loss_count,
                "closed_trades": closed_trades,
                "coins_count": len(pares_rankeados) if 'pares_rankeados' in locals() else 0
            })
            
            send_log(f"Sincronización completa. Balance: {balance} USDT | PnL Total: {total_pnl:.2f}")
            
            # 1. MÓDULO BITCOIN (Módulo 4: Jefe del Mercado)
            btc_trend, es_brusco_btc = engine.trend_analyzer.analyze_btc_filter()
            
            # 2. Análisis de Tendencia Diaria de BTC (Módulo 3)
            btc_daily_trend = engine.trend_analyzer.get_market_trend("BTCUSDT")
            
            # Sincronización de UI preliminar
            update_ui({
                "balance": f"{balance:.2f}",
                "points": memory_manager.data["puntos_aprendizaje"],
                "btc_trend": f"{btc_trend} ({btc_daily_trend})",
                "positions": posiciones,
                "total_pnl": f"{total_pnl:.2f}",
                "win_count": win_count,
                "loss_count": loss_count,
                "closed_trades": closed_trades
            })

            # Obtener todos los símbolos del mercado
            pares_disponibles = client.get_all_symbols()
            if not pares_disponibles:
                send_log("No se encontraron pares USDT. Reintentando...", "log-error")
                time.sleep(10)
                continue

            # MÓDULO DE PRIORIZACIÓN (Módulo 8: Aprendizaje)
            # Rankear pares según memoria institucional
            pares_rankeados = memory_manager.get_ranked_pairs(pares_disponibles)
            
            send_log(f"🚀 ESCANEO INICIADO: {len(pares_rankeados)} monedas priorizadas", "log-success")
            
            for par in pares_rankeados:
                if not bot_data["is_running"]: break
                
                # MÓDULO DE CORRELACIÓN (Módulo 5: Inteligencia)
                # Omitimos actualización aquí para no saturar, se actualiza en cierres o por kline
                # Solo analizamos si el bot IA no está en límite de operaciones
                if len(posiciones) < config['trading']['max_operaciones_simultaneas']:
                    print(f"Analizando IA para {par}...")
                    engine.execute_trade(par)
                
                # MÓDULO GRID DE TENDENCIA (Manual)
                print(f"Analizando Grid para {par}...")
                grid_engine.analyze_grid(par)
                
                # Respetar Rate Limits
                time.sleep(0.5) 
                
            send_log("Ciclo de escaneo completado. Esperando...", "log-warning")
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\nBot detenido por el usuario.")
        telegram.send_message("⚠️ *Bot Detenido Manualmente*")
if __name__ == "__main__":
    # Iniciar el bucle del bot usando eventlet (mejor para SocketIO)
    eventlet.spawn(bot_loop)
    
    # Iniciar el Dashboard en el hilo principal
    from dashboard.app import run_server
    print("Servidor iniciando en el hilo principal...")
    run_server()
