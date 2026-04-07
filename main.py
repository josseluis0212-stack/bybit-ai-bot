import eventlet
eventlet.monkey_patch()

import asyncio
import time
import logging
import os
import threading
from strategy.market_scanner import MarketScanner
from strategy.base_strategy import strategy
from execution_engine.executor import executor
from api.bybit_client import bybit_client

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- INTEGRACIÓN DASHBOARD DIRECTA ---
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from utils.ui_utils import set_socketio, send_log, refresh_ui

# Rutas absolutas para Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "dashboard", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "dashboard", "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
socketio = SocketIO(app, cors_allowed_origins="*")
set_socketio(socketio)

# Estado compartido
bot_control = {
    "is_running": True,
    "last_bias": "---",
    "current_balance": "0.00"
}

@app.route('/')
@app.route('/app/index.html')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return "OK", 200

@socketio.on('connect')
def handle_connect():
    logger.info("[UI] Cliente conectado. Enviando datos iniciales...")
    refresh_ui(bot_control)

@socketio.on('control_bot')
def handle_control(data):
    from database.db_manager import db_manager
    action = data.get('action')
    if action == 'start': 
        bot_control["is_running"] = True
        send_log("▶️ Bot INICIADO desde el Dashboard.", "log-success")
    elif action == 'stop': 
        bot_control["is_running"] = False
        send_log("⏹️ Bot DETENIDO desde el Dashboard.", "log-error")
    elif action == 'reset':
        # Reset manual desde el botón
        bybit_client.close_all_positions()
        db_manager.reset_all_stats()
        send_log("♻️ RESET TOTAL: Posiciones cerradas y estadísticas a cero.", "log-warning")
    
    socketio.emit('new_log', {"message": f"Comando {action} recibido.", "type": "warning"})
    refresh_ui(bot_control)

async def bot_loop():
    logger.info("🚀 INICIANDO BOT LOOP V7.9 (SYNCHRONIZED)...")
    scanner = MarketScanner()
    
    while True:
        if not bot_control["is_running"]:
            await asyncio.sleep(5)
            continue

        try:
            # Sincronizar Balance
            balance_info = bybit_client.get_wallet_balance()
            if balance_info and balance_info.get('retCode') == 0:
                coins = balance_info['result']['list'][0]['coin']
                usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
                if usdt: bot_control["current_balance"] = f"{float(usdt['walletBalance']):.2f}"
            
            await executor.check_open_positions()
            signals = await scanner.scan_market()
            
            for signal_data in signals:
                bot_control["last_bias"] = signal_data['signal']
                await executor.try_execute_signal(signal_data)
                
            # Emitir actualización a la UI
            refresh_ui(bot_control)

        except Exception as e:
            logger.error(f"Error Loop: {e}")
        
        await asyncio.sleep(30) # Aumentar frecuencia a 30s

def run_bot_loop():
    """Wrapper para correr el loop asíncrono en el background task de SocketIO."""
    asyncio.run(bot_loop())

if __name__ == "__main__":
    from database.db_manager import db_manager
    
    # --- BULLETPROOF HARD RESET (Startup) ---
    logger.info("🧹 [STARTUP] Ejecutando Hard Reset total...")
    bybit_client.close_all_positions()
    db_manager.reset_all_stats()
    logger.info("🧹 [STARTUP] Reseteo completado. Iniciando servidor...")
    
    # Iniciar el bot como una tarea de fondo de SocketIO
    socketio.start_background_task(run_bot_loop)
    
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🔥 UNIFIED SERVER V7.9 LIVE ON PORT {port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)
