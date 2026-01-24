from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
import yaml
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    emit('update_data', bot_data)

# Estado global compartido
bot_data = {
    "balance": "0.00",
    "points": 0,
    "btc_trend": "---",
    "is_running": True,
    "positions": [],
    "total_pnl": 0.0,
    "win_count": 0,
    "loss_count": 0,
    "closed_trades": []
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start')
def start_bot():
    bot_data["is_running"] = True
    return jsonify(status="started")

@app.route('/stop')
def stop_bot():
    bot_data["is_running"] = False
    return jsonify(status="stopped")

@app.route('/config', methods=['GET', 'POST'])
def handle_config():
    config_path = "config/config.yaml"
    if request.method == 'POST':
        new_config = request.json
        with open(config_path, "w") as f:
            yaml.dump(new_config, f)
        return jsonify(status="success")
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return jsonify(config)

@app.route('/toggle_mode')
def toggle_mode():
    config_path = "config/config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    config['trading']['testnet'] = not config['trading']['testnet']
    
    with open(config_path, "w") as f:
        yaml.dump(config, f)
        
    return jsonify(testnet=config['trading']['testnet'])

def run_server():
    # Render proporciona el puerto en la variable de entorno PORT
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_dashboard():
    thread = threading.Thread(target=run_server)
    thread.daemon = True
    thread.start()
    print("Dashboard iniciado en http://localhost:5000")

def update_ui(data):
    socketio.emit('update_data', data)

def send_log(message, type="log-info"):
    socketio.emit('new_log', {"message": message, "type": type})
