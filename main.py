import eventlet
eventlet.monkey_patch()
import time
import yaml
from core.bybit_client import BybitClient
from core.telegram_bot import TelegramBot
from core.risk_manager import RiskManager
from core.memory_manager import MemoryManager
from strategy.execution_engine import ExecutionEngine
from dashboard.app import start_dashboard, update_ui, send_log, bot_data
# CONFIGURACIÓN
HORAS_STATUS = 4   # Mensaje "Estoy Vivo"
HORAS_REPORTE = 24 # Resumen Financiero Completo
def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)
def bot_loop():
    config = load_config()
    print("--- INICIANDO BOT DE TRADING IA (BYBIT) ---")
    
    prev_positions = {} 
    
    # Timers
    last_status_time = time.time()
    last_daily_report_time = time.time()
    
    # Componentes
    client = BybitClient(
        testnet=config['trading'].get('testnet', False),
        demo=config['trading'].get('demo', True)
    )
    telegram = TelegramBot()
    risk_manager = RiskManager(config)
    memory_manager = MemoryManager()
    engine = ExecutionEngine(client, risk_manager, memory_manager, config, telegram)
    
    telegram.send_message("🤖 *Bot Reiniciado*\nSistema de Estadísticas Pro Activo 📊")
    
    try:
        while True:
            if not bot_data["is_running"]:
                time.sleep(5)
                continue
            now = time.time()
            # --- 1. REPORTE DIARIO DE ESTADÍSTICAS (Cada 24h) ---
            if now - last_daily_report_time > (HORAS_REPORTE * 3600):
                dia = memory_manager.get_estadisticas(1)
                semana = memory_manager.get_estadisticas(7)
                mes = memory_manager.get_estadisticas(30)
                
                msg = (
                    f"📅 *RESUMEN DE RENDIMIENTO*\n\n"
                    f"🟢 *Hoy (24h):* {dia['pnl']} USDT ({dia['wins']}/{dia['total']} Ops)\n"
                    f"🗓️ *Semana:* {semana['pnl']} USDT\n"
                    f"📆 *Mes:* {mes['pnl']} USDT\n\n"
                    f"🤖 *WinRate Global:* {mes['winrate']}%\n"
                    f"💰 *Balance Total:* {client.get_balance():.2f} USDT"
                )
                telegram.send_message(msg)
                last_daily_report_time = now
            # --- 2. STATUS "ESTOY VIVO" (Cada 4h) ---
            elif now - last_status_time > (HORAS_STATUS * 3600):
                dia = memory_manager.get_estadisticas(1)
                msg_status = (
                    f"👋 *Status Check*\n"
                    f"Bot Activo | PnL Hoy: {dia['pnl']} USDT\n"
                    f"Analizando mercado..."
                )
                telegram.send_message(msg_status)
                last_status_time = now
            # Recargar config
            with open("config/config.yaml", "r") as f:
                config = yaml.safe_load(f)
            engine.config = config
            
            # Lógica de Trading y Detección de Cierres
            balance = client.get_balance()
            posiciones = client.get_active_positions()
            
            # Detectar cierres para guardar en memoria
            current_symbols = {p['symbol'] for p in posiciones}
            for symbol, prev_p in list(prev_positions.items()):
                if symbol not in current_symbols:
                    # Posición cerrada
                    raw_pnl = prev_p.get('unrealisedPnl', 0)
                    try: pnl = float(raw_pnl)
                    except: pnl = 0.0
                    
                    # 💾 GUARDAR EN MEMORIA PERMANENTE
                    win = pnl > 0
                    memory_manager.update_coin_stats(symbol, win, pnl)
                    memory_manager.registrar_trade(symbol, prev_p['side'], pnl)
                    
                    send_log(f"Cierre detectado {symbol}: {pnl:.2f} USDT", "log-info")
                    del prev_positions[symbol]
            
            for p in posiciones:
                prev_positions[p['symbol']] = p
            
            update_ui({
                "balance": f"{balance:.2f}",
                "positions": posiciones,
            })
            
            # Escaneo
            pares = client.get_all_symbols()
            if pares:
                print(f"Escaneando {len(pares)} pares...")
                for par in pares:
                    if not bot_data["is_running"]: break
                    engine.execute_trade(par)
                    time.sleep(0.5)
            
            time.sleep(60)
    except KeyboardInterrupt:
        pass
if __name__ == "__main__":
    eventlet.spawn(bot_loop)
    from dashboard.app import run_server
    run_server()
