import logging
import os
from flask_socketio import SocketIO

# Instancia global que será configurada en main.py
socketio_instance = None

def set_socketio(si):
    global socketio_instance
    socketio_instance = si

def send_log(message, type="log-info"):
    if socketio_instance:
        socketio_instance.emit('new_log', {"message": message, "type": type})

def refresh_ui(bot_control=None):
    """Vuelve a cargar y enviar los últimos datos al Dashboard."""
    if not socketio_instance:
        return

    from database.db_manager import db_manager
    from api.bybit_client import bybit_client
    
    stats = {
        "daily": db_manager.get_stats("daily"),
        "weekly": db_manager.get_stats("weekly"),
        "monthly": db_manager.get_stats("monthly"),
        "all_time": db_manager.get_stats("all_time"),
        "performance": db_manager.get_advanced_stats()
    }
    
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
            "pnl_usdt": t.pnl_usdt or 0.0,
            "reason": t.close_reason or "N/A"
        })

    # Obtener posiciones reales directamente
    positions_response = bybit_client.get_positions()
    real_positions = []
    if positions_response and positions_response.get('retCode') == 0:
        for pos in positions_response['result']['list']:
            if float(pos['size']) > 0:
                real_positions.append(pos)

    data = {
        "balance": bot_control["current_balance"] if bot_control else "0.00",
        "bias": bot_control["last_bias"] if bot_control else "---",
        "current_price": bot_control["current_price"] if bot_control else "0.00",
        "ema_value": bot_control["ema_value"] if bot_control else "0.00",
        "stats": stats,
        "history": recent_trades,
        "positions": real_positions
    }
    socketio_instance.emit('update_data', data)
