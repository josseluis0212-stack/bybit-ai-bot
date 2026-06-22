import ccxt
import time
import logging

class ExecutionManager:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        exchange_class = getattr(ccxt, self.config.EXCHANGE_ID)
        self.exchange = exchange_class({
            'apiKey': self.config.API_KEY,
            'secret': self.config.API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future', # Use futures
            }
        })
        
        if self.config.TESTNET:
            self.exchange.set_sandbox_mode(True)
            
        # Load markets
        try:
            self.exchange.load_markets()
            self.logger.info("Markets loaded successfully.")
        except Exception as e:
            self.logger.error(f"Failed to load markets: {e}")

    def fetch_ohlcv(self, timeframe, limit=300):
        try:
            return self.exchange.fetch_ohlcv(self.config.SYMBOL, timeframe, limit=limit)
        except Exception as e:
            self.logger.error(f"Error fetching OHLCV for {timeframe}: {e}")
            return []

    def get_position(self):
        """
        Retrieves current position for the symbol.
        Returns a dict with 'side' ('long', 'short', None), 'size', 'entry_price'.
        """
        try:
            # Different exchanges handle positions differently. CCXT standardize it mostly.
            positions = self.exchange.fetch_positions([self.config.SYMBOL])
            for pos in positions:
                if pos['symbol'] == self.config.SYMBOL:
                    size = float(pos.get('contracts', pos.get('info', {}).get('size', 0)))
                    side = pos['side']
                    
                    if size > 0:
                        return {
                            'side': side, # 'long' or 'short'
                            'size': size,
                            'entry_price': float(pos['entryPrice'])
                        }
            return {'side': None, 'size': 0, 'entry_price': 0}
        except Exception as e:
            self.logger.error(f"Error fetching position: {e}")
            # If we can't confirm position, assume None to avoid errors, or raise
            return None

    def cancel_all_orders(self):
        """Cancels all open orders for the symbol (useful before opening new pos or updating SL)"""
        try:
            self.exchange.cancel_all_orders(self.config.SYMBOL)
            self.logger.info("All open orders cancelled.")
        except Exception as e:
            self.logger.error(f"Error cancelling orders: {e}")

    def open_position(self, side, price):
        """
        Opens a position using TRADE_CAPITAL.
        """
        try:
            self.cancel_all_orders()
            
            # Calculate quantity based on capital and current price
            # Assuming no leverage defined in script, or leverage is 1x. If leverage is used, adjust quantity.
            # Usually USDT-M futures capital is margin. Qty = Capital * Leverage / Price
            # Here we just use Capital / Price as a basic assumption (1x leverage).
            # To use 15 USDT margin at 10x leverage, qty would be (15 * 10) / price.
            # Defaulting to 1x leverage for safety if not specified.
            quantity = self.config.TRADE_CAPITAL / price
            
            # Adjust to lot size
            market = self.exchange.market(self.config.SYMBOL)
            quantity = float(self.exchange.amount_to_precision(self.config.SYMBOL, quantity))
            
            if quantity <= 0:
                self.logger.error("Calculated quantity is <= 0")
                return False

            order_side = 'buy' if side == 'long' else 'sell'
            
            order = self.exchange.create_order(
                symbol=self.config.SYMBOL,
                type='market',
                side=order_side,
                amount=quantity
            )
            self.logger.info(f"Opened {side} position: {order}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error opening position: {e}")
            return False

    def close_position(self, side, size):
        """
        Closes the current position.
        """
        try:
            self.cancel_all_orders()
            
            order_side = 'sell' if side == 'long' else 'buy'
            
            # Note: Many exchanges support 'reduceOnly'
            params = {'reduceOnly': True}
            
            order = self.exchange.create_order(
                symbol=self.config.SYMBOL,
                type='market',
                side=order_side,
                amount=size,
                params=params
            )
            self.logger.info(f"Closed {side} position: {order}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error closing position: {e}")
            return False

    def place_stop_loss(self, side, size, stop_price):
        """
        Places a stop loss order.
        """
        try:
            self.cancel_all_orders()
            
            order_side = 'sell' if side == 'long' else 'buy'
            
            # This is specific to how the exchange handles stop market orders.
            # Using basic CCXT unified parameters.
            params = {
                'stopPrice': stop_price,
                'reduceOnly': True
            }
            
            # Some exchanges require 'stop_market' or 'stop' type, ccxt tries to unify but it can be tricky.
            # Assuming Binance/Bybit standard here.
            order = self.exchange.create_order(
                symbol=self.config.SYMBOL,
                type='market', # Some need 'stop_market'
                side=order_side,
                amount=size,
                params=params
            )
            self.logger.info(f"Placed Stop Loss at {stop_price}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error placing stop loss: {e}")
            return False
