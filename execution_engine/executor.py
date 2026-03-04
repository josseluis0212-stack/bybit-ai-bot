import logging
import asyncio
from api.bybit_client import bybit_client
from database.db_manager import db_manager
from risk_management.risk_manager import risk_manager
from config.settings import settings
from notifications.telegram_bot import telegram_notifier

logger = logging.getLogger(__name__)

class ExecutionEngine:
    async def try_execute_signal(self, signal_data):
        """
        Intenta transformar una señal de la estrategia en una orden real,
        pasando primero por los filtros de riesgo.
        """
        symbol = signal_data['symbol']
        signal = signal_data['signal']
        entry_price = signal_data['entry_price']
        sl_price = signal_data['sl']
        tp_price = signal_data['tp']
        
        # 1. Chequeo de límites concurrentes
        open_count = db_manager.get_open_trades_count()
        if open_count >= settings.MAX_CONCURRENT_TRADES:
            logger.info(f"Omitiendo señal {symbol} - Límite de trades abierto alcanzado.")
            return False

        # 2. Chequeo de capital en Bybit
        balance_info = bybit_client.get_wallet_balance()
        available_balance = 0.0
        if balance_info and balance_info.get('retCode') == 0:
             list_balances = balance_info['result']['list'][0]['coin']
             usdt_balance = next((item for item in list_balances if item['coin'] == 'USDT'), None)
             if usdt_balance:
                 available_balance = float(usdt_balance['walletBalance'])
                 
        if not risk_manager.can_open_new_trade(open_count, available_balance):
            return False

        # 3. Calcular cantidad e instruir la orden
        qty = risk_manager.calculate_position_size(entry_price)
        
        # Ajustar lote mínimo sugerido por Bybit (esto es complejo en general pero 
        # para propósitos de Demo y prototipo usamos redondeo a 3 decimales usualmente estándar)
        # Nota: En desarrollo PRO, habría que consultar el 'lotSizeFilter' del instrumento.
        qty_str = f"{qty:.3f}"
        
        side = "Buy" if signal == "LONG" else "Sell"
        
        logger.info(f"🚀 Ejecutando {signal} en {symbol} | Qty: {qty_str} | SL: {sl_price:.4f} | TP: {tp_price:.4f}")
        
        response = bybit_client.place_order(
            symbol=symbol,
            side=side,
            order_type="Market", # Entramos Market porque la vela ya cerró confirmando señal
            qty=qty_str,
            take_profit=tp_price,
            stop_loss=sl_price
        )

        if response and response.get("retCode") == 0:
            # 4. Guardar en Base de Datos
            risk_usdt = abs(entry_price - sl_price) * float(qty_str)
            db_manager.add_trade(
                symbol=symbol,
                side=signal,
                entry_price=entry_price,
                sl=sl_price,
                tp=tp_price,
                qty=float(qty_str),
                leverage=settings.LEVERAGE,
                risk_usdt=risk_usdt
            )
            
            # 5. Notificar a Telegram
            await telegram_notifier.notify_order_opened(
                symbol=symbol,
                side=signal,
                entry_price=f"{entry_price:.4f}",
                sl=f"{sl_price:.4f}",
                tp=f"{tp_price:.4f}",
                qty=qty_str,
                leverage=settings.LEVERAGE,
                current_trades=open_count + 1,
                max_trades=settings.MAX_CONCURRENT_TRADES,
                risk_usdt=f"{risk_usdt:.2f}"
            )
            return True
        else:
            logger.error(f"Fallo al ejecutar orden en Bybit: {response}")
            return False

    async def check_open_positions(self):
        """
        Revisa las posiciones abiertas en la BD y las sincroniza con Bybit para ver si tocaron SL o TP.
        En una versión PRO real esto se hace vía WebSockets, pero por API REST verificamos el estado.
        """
        open_trades = db_manager.get_open_trades()
        if not open_trades:
            return
            
        logger.info(f"Monitorizando {len(open_trades)} operaciones abiertas...")
        
        # Obtenemos las posiciones reales de Bybit
        positions_response = bybit_client.get_positions()
        
        real_positions = {}
        if positions_response and positions_response.get('retCode') == 0:
            for pos in positions_response['result']['list']:
                # pos['size'] > 0 indica que la posición sigue abierta
                if float(pos['size']) > 0:
                    real_positions[pos['symbol']] = pos

        # Comparar nuestra BD con Bybit
        for trade in open_trades:
            symbol = trade.symbol
            
            # Si el trade está en nuestra DB pero NO en Bybit con size > 0, significa que se cerró (SL o TP tocado)
            if symbol not in real_positions:
                logger.info(f"El trade {symbol} ya no está activo en Bybit. Procesando cierre...")
                
                # Obtenemos historia de órdenes cerradas para ver por qué se cerró
                # Para simplificar, obtenemos el precio actual de ticker como exit price aproximado
                # En PRO: Se busca el PnL exacto en el endpoint de 'closed-pnl'
                tickers = bybit_client.get_tickers()
                if not tickers: continue
                    
                ticker_info = next((t for t in tickers if t['symbol'] == symbol), None)
                if not ticker_info: continue
                
                exit_price = float(ticker_info['lastPrice'])
                
                # Aproximación de pnl (LONG vs SHORT)
                if trade.side == "LONG":
                    pnl_usdt = (exit_price - trade.entry_price) * trade.qty
                    reason = "TAKE PROFIT" if exit_price >= trade.take_profit else ("STOP LOSS" if exit_price <= trade.stop_loss else "CERRADA")
                else:
                    pnl_usdt = (trade.entry_price - exit_price) * trade.qty
                    reason = "TAKE PROFIT" if exit_price <= trade.take_profit else ("STOP LOSS" if exit_price >= trade.stop_loss else "CERRADA")
                
                pnl_pct = (pnl_usdt / (trade.entry_price * trade.qty)) * 100 * trade.leverage
                
                # Actualizar DB
                db_manager.close_trade(trade.id, exit_price, pnl_usdt, pnl_pct, reason)
                
                # Consultar balance para Telegram
                balance_info = bybit_client.get_wallet_balance()
                current_balance = 0.0
                if balance_info and balance_info.get('retCode') == 0:
                     current_balance = float(balance_info['result']['list'][0]['coin'][0]['walletBalance'])
                
                # Notificar a Telegram
                await telegram_notifier.notify_order_closed(
                    symbol=symbol,
                    side=trade.side,
                    entry_price=f"{trade.entry_price:.4f}",
                    exit_price=f"{exit_price:.4f}",
                    pnl_usdt=pnl_usdt,
                    pnl_pct=pnl_pct,
                    duration="N/A", # Simplificación
                    reason=reason,
                    balance=current_balance
                )

executor = ExecutionEngine()
