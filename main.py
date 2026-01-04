import time
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

def main():
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
        testnet=config['trading'].get('testnet', False),
        demo=config['trading'].get('demo', True)
    )
    telegram = TelegramBot()
    risk_manager = RiskManager(config)
    memory_manager = MemoryManager()
    engine = ExecutionEngine(client, risk_manager, memory_manager, config)
    
    # Iniciar Dashboard
    start_dashboard()
    
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
            
            send_log(f"Sincronización completa. Balance: {balance} USDT | PnL Total: {total_pnl:.2f}")
            
            # Obtener todos los símbolos del mercado
            pares = client.get_all_symbols()
            if not pares:
                send_log("No se encontraron pares USDT para escanear. Reintentando...", "log-error")
                time.sleep(10)
                continue
                
            send_log(f"🚀 ESCANEO INICIADO: {len(pares)} monedas encontradas", "log-success")
            print(f"🚀 ESCANEO INICIADO: {len(pares)} monedas encontradas")
            
            for par in pares:
                if not bot_data["is_running"]: break
                print(f"Analizando {par}...")
                engine.execute_trade(par)
                # No dormimos mucho aquí para escanear rápido, pero respetamos rate limit
                time.sleep(0.5) 
                
            send_log("Escaneo completo. Esperando siguiente ciclo...", "log-warning")
            time.sleep(60) # Escaneo cada minuto
            
    except KeyboardInterrupt:
        print("\nBot detenido por el usuario.")
        telegram.send_message("⚠️ *Bot Detenido Manualmente*")
    except Exception as e:
        print(f"Error crítico en el bucle principal: {e}")
        telegram.send_message(f"❌ *Error Crítico:* {e}")

if __name__ == "__main__":
    main()
