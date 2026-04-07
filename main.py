import asyncio
import time
import logging
import os
from strategy.market_scanner import MarketScanner
from strategy.base_strategy import strategy
from execution_engine.executor import executor
from api.bybit_client import bybit_client
from dashboard.app import start_dashboard, bot_control, send_log, refresh_ui

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def bot_loop():
    logger.info("🚀 INICIANDO HYPER-QUANT ULTRA V7.0 (PREMIUM DASHBOARD)...")
    
    # Notificación inicial a la UI
    send_log("🤖 Sistema V7.0 Iniciado. Estableciendo conexión con Bybit...", "log-info")
    
    scanner = MarketScanner()
    
    while True:
        # 1. Verificar si el bot está encendido desde el Dashboard
        if not bot_control["is_running"]:
            await asyncio.sleep(5)
            continue

        start_time = time.time()
        
        try:
            # 2. Actualizar balance general para la UI
            balance_info = bybit_client.get_wallet_balance()
            if balance_info and balance_info.get('retCode') == 0:
                coins = balance_info['result']['list'][0]['coin']
                usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
                if usdt:
                    bot_control["current_balance"] = f"{float(usdt['walletBalance']):.2f}"
            
            # 3. Monitorear posiciones abiertas (TP/SL/Breakeven)
            await executor.check_open_positions()
            
            # 4. Escanear Mercado
            send_log(f"🔍 Escaneando mercado ({scanner.timeframe_bias}m bias)...", "log-info")
            signals = await scanner.scan_market()
            
            for signal_data in signals:
                symbol = signal_data['symbol']
                # Actualizar último Bias detectado para la UI
                bot_control["last_bias"] = signal_data['signal']
                
                # Intentar ejecución
                success = await executor.try_execute_signal(signal_data)
                if success:
                    logger.info(f"✅ Orden ejecutada con éxito: {symbol}")
            
            # Refrescar UI al final de cada ciclo
            refresh_ui()
            
        except Exception as e:
            logger.error(f"❌ Error crítico en el loop: {e}")
            send_log(f"⚠️ Error en el ciclo: {str(e)}", "log-warning")
            await asyncio.sleep(10)

        # Control de frecuencia: Esperar 1 minuto entre escaneos completos
        elapsed = time.time() - start_time
        wait_time = max(1, 60 - elapsed)
        await asyncio.sleep(wait_time)

def start_bot_in_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_loop())

if __name__ == "__main__":
    import threading
    from dashboard.app import app, socketio
    
    # 1. Iniciar el motor de trading en un hilo separado
    bot_thread = threading.Thread(target=start_bot_in_thread)
    bot_thread.daemon = True
    bot_thread.start()
    
    # 2. Iniciar el Dashboard en el hilo principal (Patrón recomendado para Render)
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🟢 SISTEMA V7.3 INICIANDO | PUERTO {port} | DASHBOARD EN HILO PRINCIPAL")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)
