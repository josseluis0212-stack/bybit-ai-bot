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
HORAS_STATUS = 4   
HORAS_REPORTE = 24 
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
    
    telegram.send_message("🤖 *Bot Live*\nReportes Detallados Activados 📝")
    
    try:
        while True:
            if not bot_data["is_running"]:
                time.sleep(5)
                continue
            now = time.time()
            # --- 1. REPORTE DIARIO ---
            if now - last_daily_report_time > (HORAS_REPORTE * 3600):
                dia = memory_manager.get_estadisticas(1)
                semana = memory_manager.get_estadisticas(7)
                msg = (
                    f"📅 *RESUMEN DIARIO*\n"
                    f"Hoy: {dia['pnl']} USDT ({dia['wins']} Wins)\n"
                    f"Semana: {semana['pnl']} USDT\n"
                    f"Balance: {client.get_balance():.2f} USDT"
                )
                telegram.send_message(msg)
                last_daily_report_time = now
            # --- 2. STATUS CHECK ---
            elif now - last_status_time > (HORAS_STATUS * 3600):
                dia = memory_manager.get_estadisticas(1)
                telegram.send_message(f"👋 *Status*: Activo | Hoy: {dia['pnl']} USDT")
                last_status_time = now
            # Reload Config & Data
            with open("config/config.yaml", "r") as f: config = yaml.safe_load(f)
            engine.config = config
            
            balance = client.get_balance()
            posiciones = client.get_active_positions()
            
            # --- DETECCIÓN DE CIERRE DE OPERACIONES ---
            current_symbols = {p['symbol'] for p in posiciones}
            for symbol, prev_p in list(prev_positions.items()):
                if symbol not in current_symbols:
                    # ¡Se cerró! Buscamos los detalles EXACTOS en Bybit
                    time.sleep(2) # Esperar a que Bybit procese el cierre
                    closed_trades = client.get_closed_pnl(symbol=symbol, limit=1)
                    
                    if closed_trades:
                        trade = closed_trades[0]
                        real_pnl = float(trade['closedPnl'])
                        entry_price = float(trade['avgEntryPrice'])
                        exit_price = float(trade['avgExitPrice'])
                        side = trade['side'] # Buy/Sell
                        qty = trade['qty']
                        
                        # Icono
                        icon = "🟢 GANADA" if real_pnl > 0 else "🔴 PERDIDA"
                        
                        # Enviar REPORTE DETALLADO
                        msg_cierre = (
                            f"{icon} *Operación Cerrada*\n\n"
                            f"🪙 *Moneda:* {symbol}\n"
                            f"🔭 *Dirección:* {side}\n"
                            f"📉 *Entrada:* {entry_price}\n"
                            f"📈 *Salida:* {exit_price}\n"
                            f"💵 *Tamaño:* {qty}\n"
                            f"💰 *Resultado:* {real_pnl:.2f} USDT\n"
                            f"------------------"
                        )
                        telegram.send_message(msg_cierre)
                        
                        # Guardar memoria
                        memory_manager.update_coin_stats(symbol, real_pnl > 0, real_pnl)
                        memory_manager.registrar_trade(symbol, side, real_pnl)
                        send_log(f"Cierre {symbol}: {real_pnl} USDT", "log-success")
                    
                    del prev_positions[symbol]
            
            for p in posiciones:
                prev_positions[p['symbol']] = p
            
            update_ui({"balance": f"{balance:.2f}","positions": posiciones})
            
            # Escaneo
            pares = client.get_all_symbols()
            if pares:
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
