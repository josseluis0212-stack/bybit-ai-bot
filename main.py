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
# TIEMPOS PARA REPORTES
HORAS_STATUS = 4
HORAS_REPORTE = 24
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
    
    # Timers de Reportes
    last_status_time = time.time()
    last_daily_report_time = time.time()
    
    # Inicializar componentes
    client = BybitClient(
        testnet=config['trading'].get('testnet', False),
        demo=config['trading'].get('demo', True)
    )
    telegram = TelegramBot()
    risk_manager = RiskManager(config)
    memory_manager = MemoryManager()
    engine = ExecutionEngine(client, risk_manager, memory_manager, config, telegram)
    
    # MENSAJE DE DIAGNÓSTICO
    telegram.send_message(
        "🚀 *SISTEMA DUAL INICIADO* 🚀\n\n"
        "✅ *BOT 1 (Auto):* Triple Pantalla (1D/1H/5m)\n"
        "✅ *BOT 2 (Grid):* Alertas Pro (Bollinger Reversión)\n"
        "📡 *Conexión Telegram:* ESTABLE\n"
        "🐺 *El lobo está cazando...*"
    )
    
    try:
        while True:
            if not bot_data["is_running"]:
                print("Bot en pausa (esperando inicio desde Dashboard)...")
                time.sleep(5)
                continue
            # Recargar configuración
            with open("config/config.yaml", "r") as f:
                config = yaml.safe_load(f)
            engine.config = config
            engine.risk_manager.config = config
            engine.trend_analyzer.config = config
            balance = client.get_balance()
            btc_trend = engine.trend_analyzer.analyze_btc_filter()
            posiciones = client.get_active_positions()
            
            # --- DETECTAR CIERRES DE OPERACIONES ---
            current_symbols = {p['symbol'] for p in posiciones}
            for symbol, prev_p in list(prev_positions.items()):
                if symbol not in current_symbols:
                    # La posición se cerró
                    raw_pnl = prev_p.get('unrealisedPnl', 0)
                    try:
                        pnl = float(raw_pnl) if raw_pnl is not None and str(raw_pnl).strip() != "" else 0.0
                    except: pnl = 0.0
                    
                    total_pnl += pnl
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    
                    # Registrar en Memoria
                    memory_manager.registrar_cierre(symbol, pnl)
                    
                    # Notificar Cierre
                    emoji = "💰" if pnl >= 0 else "🛑"
                    telegram.send_message(f"{emoji} *TRADE CERRADO*: {symbol}\nPNL: {pnl:.2f} USDT")
                    
                    trade_info = {
                        "symbol": symbol, "side": prev_p['side'], "pnl": f"{pnl:.2f}",
                        "time": time.strftime("%H:%M:%S")
                    }
                    closed_trades.insert(0, trade_info)
                    if len(closed_trades) > 10: closed_trades.pop()
                    del prev_positions[symbol]
            
            for p in posiciones: prev_positions[p['symbol']] = p
            # --- REPORTES PERIÓDICOS ---
            # 1. Reporte de Estado (Cada 4 horas)
            if time.time() - last_status_time > (HORAS_STATUS * 3600):
                msg = f"⏱️ *Emebargo 4H*\nBalance: {balance:.2f}\nPnL Sesión: {total_pnl:.2f}"
                telegram.send_message(msg)
                last_status_time = time.time()
                
            # 2. Reporte Diario y Semanal (Cada 24 horas)
            if time.time() - last_daily_report_time > (HORAS_REPORTE * 3600):
                stats_dia = memory_manager.get_estadisticas(dias=1)
                stats_sem = memory_manager.get_estadisticas(dias=7)
                msg_reporte = (
                    f"📅 *REPORTE DIARIO*\n"
                    f"Ganancia Día: {stats_dia['pnl_total']:.2f} USDT\n"
                    f"Trades Día: {stats_dia['total_trades']}\n\n"
                    f"🗓️ *REPORTE SEMANAL*\n"
                    f"Ganancia Semana: {stats_sem['pnl_total']:.2f} USDT"
                )
                telegram.send_message(msg_reporte)
                last_daily_report_time = time.time()
            # --- ACTUALIZAR DASHBOARD ---
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
            
            # --- ESCANEO DE MERCADO ---
            pares = client.get_all_symbols()
            if not pares:
                time.sleep(10)
                continue
                
            print(f"🚀 ESCANEO INICIADO: {len(pares)} monedas")
            
            for par in pares:
                if not bot_data["is_running"]: break
                engine.execute_trade(par)
                time.sleep(0.5) 
                
            send_log("Escaneo completo. Esperando siguiente ciclo...", "log-warning")
            time.sleep(60)
            
    except KeyboardInterrupt:
        telegram.send_message("⚠️ *Bot Detenido Manualmente*")
if __name__ == "__main__":
    eventlet.spawn(bot_loop)
    from dashboard.app import run_server
    print("Servidor iniciando en el hilo principal...")
    run_server()
