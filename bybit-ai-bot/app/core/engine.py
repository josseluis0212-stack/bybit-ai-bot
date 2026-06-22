import asyncio
import time
import os
import json
from app.logger import logger
from app.config import Config
from app.exchange.websocket_client import BybitWebSocket
from app.exchange.bybit_client import AsyncBybitClient
from app.exchange.order_executor import OrderExecutor
from app.core.guardian import ExchangeSynchronizer
from app.core.recovery_engine import RecoveryEngine
from app.risk.trailing_manager import TrailingManager
from app.database import crud
from app.strategy.antigravity_v13_pro import evaluate_antigravity_v13
from app.strategy.supertrend_regime import evaluate_supertrend_regime
import pandas as pd
import pandas_ta as ta
class Engine:
    def __init__(self):
        self.client = AsyncBybitClient()
        self.executor = OrderExecutor()
        self.synchronizer = ExchangeSynchronizer(self)
        self.recovery = RecoveryEngine(self)
        self.ws = BybitWebSocket(
            message_callback=self._noop_ws,
            fill_callback=self.on_fill_event,
            mark_price_callback=self._handle_ws_mark_price
        )
        self.trade_state = {}
        self.cooldowns = {}
        self.tracked_symbols = []
        self.running = False

    async def start(self):
        self.running = True
        logger.info("🚀 [ENGINE] Iniciando Antigravity Bot (Demo/Testnet)...")
        await crud.init_db()
        await self.recovery.execute_recovery()

        self._polling_task = asyncio.create_task(self._kline_polling_loop())
        self._sync_task = asyncio.create_task(self.synchronizer.start())
        
        await self.ws.connect()
        for sym in self.trade_state.keys():
            await self.ws.subscribe_mark_price(sym)

    async def stop(self):
        self.running = False
        await self.synchronizer.stop()
        await self.ws.stop()
        if hasattr(self, '_polling_task'):
            self._polling_task.cancel()
        if hasattr(self, '_sync_task'):
            self._sync_task.cancel()
        logger.info("[ENGINE] Apagado completado.")

    async def force_scan(self):
        logger.info("🚀 [ENGINE] Escaneo inmediato forzado...")
        self.running = True

    async def reset_state(self):
        logger.info("♻️ [ENGINE] Reseteando estado local y cerrando operaciones activas...")
        try:
            positions = await self.client.get_positions()
            for pos in positions:
                symbol = pos.get("symbol")
                amt = float(pos.get("positionAmt", 0))
                side = "LONG" if pos.get("positionSide") == "LONG" else "SHORT"
                if abs(amt) > 0:
                    await self.executor.close_position_market(symbol, side, "MANUAL_RESET")
        except Exception as e:
            logger.error(f"[ENGINE] Error cerrando posiciones en reset: {e}")
        
        self.trade_state.clear()
        logger.info("✅ [ENGINE] Estado reseteado.")

    async def _noop_ws(self, data):
        pass

    async def on_fill_event(self, data: dict):
        try:
            order_id = str(data.get("i", data.get("orderId", "")))
            status = data.get("X", data.get("status", ""))
            symbol = data.get("s", data.get("symbol", ""))

            if status != "FILLED": return
            trade = self.trade_state.get(symbol)
            if not trade: return

            # Entry
            if order_id == trade.get("trade_id") and not trade.get("filled"):
                logger.info(f"✅ [FILL] Entrada ejecutada para {symbol}. Colocando SL y TPs...")
                trade["filled"] = True
                await self._place_protections(symbol, trade)
                
            # TP1
            elif order_id == trade.get("tp1_order_id") and not trade.get("tp1_hit"):
                logger.info(f"🎯 [TP1] 30% asegurado en {symbol}. (No se mueve SL aquí)")
                trade["tp1_hit"] = True
                trade["remaining_size"] -= trade["position_size"] * 0.3
                
            # TP2
            elif order_id == trade.get("tp2_order_id") and not trade.get("tp2_hit"):
                logger.info(f"🎯 [TP2] 30% adicional asegurado en {symbol}. Activando Trailing Stop.")
                trade["tp2_hit"] = True
                trade["remaining_size"] -= trade["position_size"] * 0.3
                trade["trailing_active"] = True

            # Stop Loss
            elif order_id == trade.get("sl_order_id"):
                logger.info(f"🛑 [FILL] Stop Loss ejecutado para {symbol}.")
                # Se cerrará en _close_position_internal (vía websocket o guardián)
                # No hacemos remove directo para que _close_position_internal decida el cooldown.

            # Guardar en DB
            db_trade = await crud.get_trade_by_id(trade["trade_id"])
            if db_trade:
                db_trade.tp1_filled = trade.get("tp1_hit", False)
                db_trade.tp2_filled = trade.get("tp2_hit", False)
                db_trade.profit_lock_active = trade.get("profit_lock_active", False)
                db_trade.trailing_active = trade.get("trailing_active", False)
                db_trade.remaining_size = trade["remaining_size"]
                await crud.save_trade(db_trade)

        except Exception as e:
            logger.error(f"[FILL EVENT] Error: {e}")

    async def _place_protections(self, symbol, trade):
        sl = trade["sl_price"]
        tp1 = trade["tp1_price"]
        tp2 = trade["tp2_price"]
        sz = trade["position_size"]
        order_ids = await self.executor.place_sl_and_tps(symbol, trade["side"], sl, tp1, tp2, sz)
        if order_ids:
            trade["sl_order_id"] = order_ids.get("sl")
            trade["tp1_order_id"] = order_ids.get("tp1")
            trade["tp2_order_id"] = order_ids.get("tp2")

        await self.ws.subscribe_mark_price(symbol)

    async def _activate_profit_lock(self, symbol, trade):
        if "lock" not in trade:
            trade["lock"] = asyncio.Lock()
            
        async with trade["lock"]:
            if trade.get("profit_lock_active"): return
            
            logger.info(f"🔒 [BREAKEVEN] Moviendo SL a punto de entrada (Breakeven) para {symbol}.")
            new_sl = trade["profit_lock_price"]
            new_id = await self.executor.update_sl(
                symbol, trade["side"], trade.get("sl_order_id"), new_sl, trade["remaining_size"]
            )
            if new_id:
                trade["sl_order_id"] = new_id
                trade["sl_price"] = new_sl
                trade["profit_lock_active"] = True

    async def _handle_ws_mark_price(self, data):
        try:
            ws_data = data.get("data", {})
            symbol = ws_data.get("symbol")
            mark_price = ws_data.get("markPrice")
            if not symbol or not mark_price: return
            
            mark_price = float(mark_price)
            trade = self.trade_state.get(symbol)
            
            if trade and trade.get("filled"):
                side = trade["side"]
                entry_price = trade["entry_price"]
                tp2_price = trade["tp2_price"]  # El 100% de la operación es el último TP
                
                # Breakeven: se activa según la estrategia
                if not trade.get("profit_lock_active"):
                    if trade.get("strategy") == "AntigravityV13":
                        # Activa al 33.3% de ROE (3.33% de mov. de precio a 10x)
                        be_threshold = entry_price * (0.333 / Config.LEVERAGE)
                    else:
                        # SuperTrend activa BE a los 2.0 ATR
                        be_threshold = trade["atr"] * 2.0
                        
                    if side == "LONG" and mark_price >= entry_price + be_threshold:
                        await self._activate_profit_lock(symbol, trade)
                    elif side == "SHORT" and mark_price <= entry_price - be_threshold:
                        await self._activate_profit_lock(symbol, trade)
                
                highest = trade.get("highest_price", mark_price)
                if side == "LONG" and mark_price > highest:
                    trade["highest_price"] = mark_price
                elif side == "SHORT" and mark_price < highest:
                    trade["highest_price"] = mark_price
                    
                # Trailing Stop: Activar solo después de 2.5 ATR de ganancia
                trail_threshold = trade["atr"] * 2.5
                trail_ready = trade.get("trailing_active", False)
                
                if not trail_ready:
                    if side == "LONG" and mark_price >= entry_price + trail_threshold:
                        trade["trailing_active"] = True
                        trail_ready = True
                        logger.info(f"🚀 [TRAILING] Activado para {symbol} LONG al cruzar 2.5 ATR de ganancia.")
                    elif side == "SHORT" and mark_price <= entry_price - trail_threshold:
                        trade["trailing_active"] = True
                        trail_ready = True
                        logger.info(f"🚀 [TRAILING] Activado para {symbol} SHORT al cruzar 2.5 ATR de ganancia.")

                if trail_ready:
                    # Usamos el EMA21 calculado asíncronamente en el polling, o caemos al ATR
                    ema_21 = trade.get("ema_21", 0)
                    if ema_21 > 0:
                        new_sl = ema_21 if side == "LONG" else ema_21
                        # Asegurar que NUNCA retroceda el SL
                        if side == "LONG" and new_sl < trade["sl_price"]: new_sl = trade["sl_price"]
                        if side == "SHORT" and new_sl > trade["sl_price"]: new_sl = trade["sl_price"]
                    else:
                        new_sl = TrailingManager.calculate_new_sl(
                            mark_price, trade["highest_price"], trade["sl_price"], trade["atr"], side
                        )
                    
                    # Evitar actualizaciones microscópicas y Race Conditions
                    if abs(new_sl - trade["sl_price"]) > (trade["atr"] * 0.05):
                        if "lock" not in trade:
                            trade["lock"] = asyncio.Lock()
                            
                        # Solo actualizamos si no hay otra actualización en curso
                        if not trade["lock"].locked():
                            async with trade["lock"]:
                                try:
                                    logger.info(f"🚀 [TRAILING] Moviendo SL a {new_sl:.4f} para {symbol}.")
                                    new_id = await self.executor.update_sl(
                                        symbol, side, trade.get("sl_order_id"), new_sl, trade["remaining_size"]
                                    )
                                    if new_id:
                                        trade["sl_order_id"] = new_id
                                        trade["sl_price"] = new_sl
                                except Exception as e:
                                    logger.error(f"[TRAILING] Error actualizando SL: {e}")
        except Exception as e:
            logger.error(f"[WS MARK PRICE] Error: {e}")

    async def _close_position_internal(self, symbol: str, reason: str):
        trade = self.trade_state.pop(symbol, None)
        if trade:
            db_trade = await crud.get_trade_by_id(trade["trade_id"])
            if db_trade:
                db_trade.position_closed = True
                await crud.save_trade(db_trade)
            logger.info(f"🛑 [CLOSE] {symbol} cerrada. Motivo: {reason}")
            
            # Si se cerró y no tocamos ni TP1, ni BE, ni Trailing -> Fue un SL inicial negativo
            if not trade.get("tp1_hit") and not trade.get("profit_lock_active") and not trade.get("trailing_active"):
                logger.info(f"💤 [COOLDOWN] {symbol} cerró en pérdida. Puesta a descansar por 1 hora.")
                self.cooldowns[symbol] = time.time() + 3600 # 1 hour
                
            await self.ws.unsubscribe_mark_price(symbol)

    async def _kline_polling_loop(self):
        await asyncio.sleep(5)
        
        # Semáforo para limitar concurrencia a 5 agentes simultáneos (evita baneos de IP/Rate Limits en Bybit)
        semaphore = asyncio.Semaphore(5)
        
        async def evaluate_and_execute(symbol):
            async with semaphore:
                try:
                    # Actualizar EMA21 de los trades activos para el trailing
                    trade = self.trade_state.get(symbol)
                    if trade and trade.get("trailing_active"):
                        klines = await self.client.get_klines(symbol, interval="15", limit=30)
                        if klines:
                            df = pd.DataFrame(klines)
                            ema21 = ta.ema(df['close'], length=21)
                            if ema21 is not None and not ema21.empty:
                                trade["ema_21"] = ema21.iloc[-1]

                    # Si ya tiene trade, no abrimos otro, salimos
                    if trade: return

                    # Timeout de 15 segundos máximo por moneda para evitar bloqueos
                    ag_task = asyncio.create_task(evaluate_antigravity_v13(self.client, symbol))
                    st_task = asyncio.create_task(evaluate_supertrend_regime(self.client, symbol))
                    
                    done, pending = await asyncio.wait([ag_task, st_task], timeout=15.0)
                    for p in pending: p.cancel()
                    
                    ag_res = ag_task.result() if ag_task in done and not ag_task.exception() else {"signal": "NONE"}
                    st_res = st_task.result() if st_task in done and not st_task.exception() else {"signal": "NONE"}
                    
                    if st_res.get("signal") != "NONE":
                        await self._execute_signal(symbol, st_res, "SuperTrendRegimeMTF")
                    elif ag_res.get("signal") != "NONE":
                        await self._execute_signal(symbol, ag_res, "AntigravityV13")
                        
                except asyncio.TimeoutError:
                    logger.error(f"[POLL] Timeout evaluando {symbol}. Saltando...")
                except Exception as e:
                    logger.error(f"[POLL] Error evaluando {symbol}: {e}")
        
        while self.running:
            logger.info("[POLL] Analizando el mercado en busca de oportunidades (V13 PRO) de forma concurrente...")
            try:
                symbols = await self.client.get_top_volume_symbols(40)
            except Exception as e:
                logger.error(f"[POLL] Error obteniendo símbolos de volumen: {e}")
                symbols = []
                
            if not symbols: 
                await asyncio.sleep(5)
                continue
                
            # Filtramos símbolos que ya tienen una operación activa o están en descanso
            symbols_to_evaluate = []
            
            # Limite Global de Operaciones simultáneas
            active_trades_count = len(self.trade_state)
            if active_trades_count >= Config.MAX_OPEN_TRADES:
                logger.warning(f"[POLL] Límite de posiciones abiertas alcanzado ({active_trades_count}/{Config.MAX_OPEN_TRADES}). Solo actualizando EMA21 para trailing.")
                # Solo evaluamos los que ya están en self.trade_state para actualizar EMA21
                tasks = [asyncio.create_task(evaluate_and_execute(sym)) for sym in self.trade_state.keys()]
                if tasks: await asyncio.gather(*tasks)
                await asyncio.sleep(60)
                continue

            for sym in symbols:
                if sym in self.trade_state: 
                    # Lo incluimos para que se actualice su EMA21 en el polling loop
                    symbols_to_evaluate.append(sym)
                    continue
                if sym in self.cooldowns:
                    if time.time() < self.cooldowns[sym]:
                        continue
                    else:
                        del self.cooldowns[sym] # Tiempo expirado
                symbols_to_evaluate.append(sym)
            
            if symbols_to_evaluate:
                # Lanzamos el análisis de todas las monedas en paralelo
                tasks = [asyncio.create_task(evaluate_and_execute(sym)) for sym in symbols_to_evaluate]
                await asyncio.gather(*tasks)
                
            logger.info(f"[POLL] Escaneo multi-agente completado en {len(symbols_to_evaluate)} monedas. Esperando el siguiente ciclo...")
            await asyncio.sleep(60)

    async def _execute_signal(self, symbol, signal_data, strategy_name="Unknown"):
        side = signal_data["signal"]
        logger.info(f"🚨 [SEÑAL] {symbol} {side} by {strategy_name}")
        
        ticker = await self.client.get_ticker(symbol)
        if not ticker: return
        
        entry_price = float(ticker.get("askPrice") if side == "LONG" else ticker.get("bidPrice"))
        if entry_price <= 0: entry_price = float(ticker.get("lastPrice", 0))

        atr = signal_data.get("atr", entry_price * 0.01)
        if atr <= 0: atr = entry_price * 0.01
        
        sl_price = entry_price - (2.5 * atr) if side == "LONG" else entry_price + (2.5 * atr)
        
        # Strategy 1 uses 30/30/40. Strategy 2 (SuperTrend) disables fixed TPs.
        if strategy_name == "SuperTrendRegimeMTF":
            tp1_price = None
            tp2_price = None
        else:
            tp1_price = entry_price + (1.5 * atr) if side == "LONG" else entry_price - (1.5 * atr)
            tp2_price = entry_price + (3.0 * atr) if side == "LONG" else entry_price - (3.0 * atr)
            
        # Breakeven SL
        if strategy_name == "AntigravityV13":
            # Asegura el 15% de ROE moviendo el SL a +15% de ganancia de la operación
            profit_lock_price = entry_price + (entry_price * (0.15 / Config.LEVERAGE)) if side == "LONG" else entry_price - (entry_price * (0.15 / Config.LEVERAGE))
        else:
            # SuperTrend asegura exactamente el precio de entrada (0.00 ATR)
            profit_lock_price = entry_price
        
        # Tamaño de posición fijo: $15 USDT margen * Apalancamiento
        total_volume_usdt = Config.MARGIN_USDT * Config.LEVERAGE
        if entry_price <= 0:
            logger.error(f"[{symbol}] Error: Entry Price es 0.")
            return
            
        size = total_volume_usdt / entry_price
        if size <= 0: return

        # Aseguramos que solo hayan MAX_OPEN_TRADES activos antes de disparar
        if len(self.trade_state) >= Config.MAX_OPEN_TRADES:
            logger.warning(f"[{symbol}] Omitiendo orden, se alcanzó el MAX_OPEN_TRADES.")
            return

        order_id = await self.executor.place_entry(symbol, side, size, entry_price, attached_sl=sl_price)
        if not order_id: return

        trade = {
            "trade_id": order_id,
            "side": side,
            "entry_price": entry_price,
            "position_size": size,
            "remaining_size": size,
            "atr": atr,
            "sl_price": sl_price,
            "tp1_price": tp1_price,
            "tp2_price": tp2_price,
            "profit_lock_price": profit_lock_price,
            "highest_price": entry_price,
            "filled": False,
            "tp1_hit": False,
            "tp2_hit": False,
            "profit_lock_active": False,
            "trailing_active": False,
            "strategy": strategy_name,
            "ema_21": 0.0,
            "order_time": time.time(),  # Para timeout de 15 min
            "entry_timeout": time.time() + 900,  # 15 minutos
        }
        self.trade_state[symbol] = trade

        db_trade = await crud.create_trade(
            symbol=symbol,
            signal=side,
            entry_price=entry_price,
            stop_loss=sl_price,
            qty=size,
            strategy=strategy_name,
            trade_id=order_id,
            position_size=size,
            atr=atr,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            profit_lock_price=profit_lock_price
        )