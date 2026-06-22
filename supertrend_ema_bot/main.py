import time
import logging
import pandas as pd
from datetime import datetime

import config
from execution import ExecutionManager
from indicators import calculate_indicators_15m, calculate_indicators_1h
from strategy import RegimeStrategy
from risk_management import RiskManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting SuperTrend EMA Regime MTF Pro Bot...")
    
    execution = ExecutionManager(config)
    strategy = RegimeStrategy()
    risk_manager = RiskManager(config)
    
    current_sl = None

    while True:
        try:
            # 1. Fetch Data
            # We fetch more candles to ensure EMAs and Slope calculate correctly
            data_15m = execution.fetch_ohlcv(config.TIMEFRAME_15M, limit=300)
            data_1h = execution.fetch_ohlcv(config.TIMEFRAME_1H, limit=300)
            
            if not data_15m or not data_1h:
                logger.warning("Could not fetch data. Retrying in 60s...")
                time.sleep(60)
                continue
                
            df_15m = pd.DataFrame(data_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_1h = pd.DataFrame(data_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Convert timestamp to datetime for debugging if needed
            df_15m['datetime'] = pd.to_datetime(df_15m['timestamp'], unit='ms')
            df_1h['datetime'] = pd.to_datetime(df_1h['timestamp'], unit='ms')

            # 2. Calculate Indicators
            df_15m_calc = calculate_indicators_15m(df_15m, config)
            df_1h_calc = calculate_indicators_1h(df_1h, config)
            
            # 3. Get Current Position
            pos = execution.get_position()
            if pos is None:
                logger.warning("Could not verify position. Retrying in 60s...")
                time.sleep(60)
                continue
                
            current_position = pos['side']
            entry_price = pos['entry_price']
            position_size = pos['size']
            
            latest_15m = df_15m_calc.iloc[-1]
            current_price = latest_15m['close']
            current_atr = latest_15m['atr']
            ema_21 = latest_15m['ema_21']

            # 4. Risk Management (if open position)
            if current_position is not None:
                # If we don't have an SL locally tracked but we have a position, we should set it
                if current_sl is None:
                    current_sl = risk_manager.calculate_initial_sl(current_position, entry_price, current_atr)
                    execution.place_stop_loss(current_position, position_size, current_sl)
                else:
                    new_sl = risk_manager.update_sl(
                        side=current_position, 
                        entry_price=entry_price, 
                        current_price=current_price, 
                        current_sl=current_sl, 
                        current_atr=current_atr, 
                        ema_21=ema_21
                    )
                    
                    if new_sl is not None and new_sl != current_sl:
                        logger.info(f"Updating SL to {new_sl} due to Trailing/Breakeven")
                        current_sl = new_sl
                        execution.place_stop_loss(current_position, position_size, current_sl)

                # Check manual local SL hit just in case API missed it
                if current_position == 'long' and current_price <= current_sl:
                    logger.info(f"Local SL Hit for LONG at {current_price}")
                    execution.close_position('long', position_size)
                    current_position = None
                    current_sl = None
                elif current_position == 'short' and current_price >= current_sl:
                    logger.info(f"Local SL Hit for SHORT at {current_price}")
                    execution.close_position('short', position_size)
                    current_position = None
                    current_sl = None
            else:
                current_sl = None # Reset SL if no position

            # 5. Evaluate Strategy
            signal_data = strategy.evaluate(df_15m_calc, df_1h_calc, current_position)
            signal = signal_data['signal']
            reason = signal_data['reason']

            if signal:
                logger.info(f"Signal Generated: {signal} - Reason: {reason}")
                
                if signal == 'close_long' and current_position == 'long':
                    execution.close_position('long', position_size)
                    
                elif signal == 'close_short' and current_position == 'short':
                    execution.close_position('short', position_size)
                    
                elif signal == 'long' and current_position is None:
                    success = execution.open_position('long', current_price)
                    if success:
                        current_sl = risk_manager.calculate_initial_sl('long', current_price, current_atr)
                        pos = execution.get_position() # get exact size
                        if pos and pos['size'] > 0:
                            execution.place_stop_loss('long', pos['size'], current_sl)
                            
                elif signal == 'short' and current_position is None:
                    success = execution.open_position('short', current_price)
                    if success:
                        current_sl = risk_manager.calculate_initial_sl('short', current_price, current_atr)
                        pos = execution.get_position()
                        if pos and pos['size'] > 0:
                            execution.place_stop_loss('short', pos['size'], current_sl)

            # 6. Sleep until next roughly 1-minute check
            # Real implementation could align sleep with candle close, 
            # but for trailing SL, checking more frequently (e.g., every 60s) is better
            time.sleep(60)

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(60)

if __name__ == "__main__":
    main()
