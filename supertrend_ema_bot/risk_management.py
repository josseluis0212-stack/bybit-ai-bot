class RiskManager:
    def __init__(self, config):
        self.config = config

    def calculate_initial_sl(self, side, entry_price, current_atr):
        """
        Calculates the initial Stop Loss price based on ATR.
        """
        if side == 'long':
            return entry_price - (self.config.STOP_LOSS_ATR_MULTIPLIER * current_atr)
        elif side == 'short':
            return entry_price + (self.config.STOP_LOSS_ATR_MULTIPLIER * current_atr)
        return None

    def update_sl(self, side, entry_price, current_price, current_sl, current_atr, ema_21):
        """
        Calculates the new Stop Loss price based on Breakeven and Trailing logic.
        Returns the new SL price, or None if no update is needed.
        """
        new_sl = current_sl
        
        if side == 'long':
            # Check Breakeven
            profit_distance = current_price - entry_price
            if profit_distance >= (self.config.BREAKEVEN_TRIGGER_ATR_MULTIPLIER * current_atr):
                # Move to entry if current SL is below entry
                if new_sl < entry_price:
                    new_sl = entry_price
            
            # Check Trailing
            if profit_distance >= (self.config.TRAILING_TRIGGER_ATR_MULTIPLIER * current_atr):
                # Trail using EMA21, but never lower the SL
                if ema_21 > new_sl:
                    new_sl = ema_21
                    
        elif side == 'short':
            # Check Breakeven
            profit_distance = entry_price - current_price
            if profit_distance >= (self.config.BREAKEVEN_TRIGGER_ATR_MULTIPLIER * current_atr):
                # Move to entry if current SL is above entry
                if new_sl > entry_price:
                    new_sl = entry_price
            
            # Check Trailing
            if profit_distance >= (self.config.TRAILING_TRIGGER_ATR_MULTIPLIER * current_atr):
                # Trail using EMA21, but never raise the SL
                if ema_21 < new_sl:
                    new_sl = ema_21
                    
        # Return new SL if it changed, else None
        if new_sl != current_sl:
            return new_sl
            
        return None
