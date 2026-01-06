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
# --- CONFIGURACIÓN DE REPORTE ---
HORAS_REPORTE = 4 # Cada cuántas horas envía mensaje
# -------------------------------
def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)
def bot_loop():
    config = load_config()
    print("--- INICIANDO BOT DE TRADING IA (BYBIT) ---")
    
    # Variables de seguimiento
    prev_positions = {} 
    total_pnl = 0.0
    win_count = 0
    loss_count = 0
    closed_trades = []
    
    # Control de tiempo para reportes
    last_report_time = time.time()
    
    # Inicializar componentes
    client = BybitClient(
        testnet=config['trading'].get('testnet', False),
        demo=config['trading'].get('demo', True)
    )
    telegram = TelegramBot()
    risk_manager = RiskManager(config)
    memory_manager = MemoryManager()
    engine = ExecutionEngine(client, risk_manager, memory_manager, config, telegram)
    
    telegram.send_message("🤖 *Bot de Trading Iniciado*\n\n✅ Estrategia Avanzada Activa\n✅ Reporte cada 4 horas")
    
    try:
        while True:
            if not bot_data["is_running"]:
                print("Bot en pausa...")
                time.sleep(5)
                continue
            # 1. Verificar si toca enviar REPORTE "ESTOY VIVO"
            if time.time() - last_report_time > (HORAS_REPORTE * 3600):
                balance_now = client.get_balance()
                pos_activas = len(client.get_active_positions())
                msg = (
                    f"👋 *Reporte de Estado*\n\n"
                    f"🔋 *Bot Activo:* Sí\n"
                    f"💰 *Balance:* {balance_now:.2f} USDT\n"
                    f"📊 *Posiciones Abiertas:* {pos_activas}\n"
                    f"📈 *PnL Sesión:* {total_pnl:.2f} USDT\n"
                    f"⏳ *Próximo reporte en {HORAS_REPORTE}h*"
                )
                telegram.send_message(msg)
                last_report_time = time.time()
                send_log("Reporte periódico enviado a Telegram", "log-info")
            # Recargar configuración
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
                    raw_pnl = prev_p.get('unrealisedPnl', 0)
                    try:
                        pnl = float(raw_pnl)
                    except:
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
            
            for p in posiciones:
                prev_positions[p['symbol']] = p
            # Actualizar Dashboard UI
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
            
            # Escaneo de Mercado
            pares = client.get_all_symbols()
            if not pares:
                time.sleep(10)
                continue
                
            send_log(f"🚀 Escaneando {len(pares)} pares...", "log-info")
            print(f"🚀 Escaneando {len(pares)} pares...")
            
            for par in pares:
                if not bot_data["is_running"]: break
                engine.execute_trade(par)
                time.sleep(0.5) 
                
            time.sleep(60) 
            
    except KeyboardInterrupt:
        telegram.send_message("⚠️ *Bot Detenido Manualmente*")
if __name__ == "__main__":
    eventlet.spawn(bot_loop)
    from dashboard.app import run_server
    run_server()
