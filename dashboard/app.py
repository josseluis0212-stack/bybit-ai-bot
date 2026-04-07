from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import os
import logging
from database.db_manager import db_manager

# Desactivar logs basura de Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Estado global compartido para control del Bot
bot_control = {
    "is_running": True,
    "last_bias": "---",
    "current_balance": "0.00"
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/app/index.html')
def index_legacy():
    return render_template('index.html')

@app.route('/health')
def health_check():
    return "OK", 200

# SocketIO Events
@socketio.on('connect')
def handle_connect():
    print("[UI] Cliente conectado. Enviando datos iniciales...")
    refresh_ui()

@socketio.on('control_bot')
def handle_control(data):
    action = data.get('action')
    if action == 'start':
        bot_control["is_running"] = True
        send_log("▶️ Bot INICIADO desde el Dashboard.", "log-success")
    elif action == 'stop':
        bot_control["is_running"] = False
        send_log("⏹️ Bot DETENIDO desde el Dashboard.", "log-error")
    elif action == 'reset':
        send_log("♻️ Estadísticas de sesión reseteadas (Visualmente).", "log-warning")
    
    refresh_ui()

def refresh_ui():
    """Genera un paquete completo de datos para la UI."""
    stats_daily = db_manager.get_stats("daily")
    stats_weekly = db_manager.get_stats("weekly")
    stats_monthly = db_manager.get_stats("monthly")
    
    recent_trades = []
    trades_raw = db_manager.get_recent_closed_trades(20)
    for t in trades_raw:
        recent_trades.append({
            "close_time": t.close_time.strftime("%H:%M:%S") if t.close_time else "---",
            "symbol": t.symbol,
            "side": t.side,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "pnl_pct": t.pnl_pct or 0.0,
            "reason": t.close_reason or "N/A"
        })

    data = {
        "balance": bot_control["current_balance"],
        "bias": bot_control["last_bias"],
        "is_running": bot_control["is_running"],
        "stats": {
            "daily": stats_daily,
            "weekly": stats_weekly,
            "monthly": stats_monthly
        },
        "history": recent_trades,
        "positions": [] # Esto se llena desde main.py periódicamente
    }
    socketio.emit('update_data', data)

def send_log(message, type="log-info"):
    socketio.emit('new_log', {"message": message, "type": type})

def run_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"[UI] Dashboard V7.0 iniciando en puerto {port}...")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_dashboard():
    thread = threading.Thread(target=run_server)
    thread.daemon = True
    thread.start()
    return thread
