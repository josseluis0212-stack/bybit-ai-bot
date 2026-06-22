import config

class RegimeStrategy:
    def __init__(self):
        self.long_setup_armed = False
        self.long_setup_candles = 0
        
        self.short_setup_armed = False
        self.short_setup_candles = 0

    def evaluate(self, df_15m, df_1h, current_position):
        """
        Evaluates the strategy on the latest candle.
        Returns a dictionary with 'signal' (None, 'long', 'short', 'close_long', 'close_short')
        and 'reason'.
        df_15m and df_1h are the calculated indicator dataframes.
        """
        if df_15m.empty or df_1h.empty:
            return {'signal': None, 'reason': 'Not enough data'}
            
        latest_15m = df_15m.iloc[-1]
        latest_1h = df_1h.iloc[-1]
        
        # --- Update Setup State ---
        
        # 1. Check Previous Regime for Long (Bearish Regime)
        is_bearish_regime = (
            latest_15m['supertrend_dir'] == -1 and 
            latest_15m['close'] < latest_15m['ema_200'] and 
            latest_15m['ema_9'] < latest_15m['ema_21']
        )
        
        if is_bearish_regime:
            self.long_setup_armed = True
            self.long_setup_candles = 0
        elif self.long_setup_armed:
            self.long_setup_candles += 1
            if self.long_setup_candles > config.MAX_SETUP_WINDOW_CANDLES:
                self.long_setup_armed = False
                
        # 2. Check Previous Regime for Short (Bullish Regime)
        is_bullish_regime = (
            latest_15m['supertrend_dir'] == 1 and 
            latest_15m['close'] > latest_15m['ema_200'] and 
            latest_15m['ema_9'] > latest_15m['ema_21']
        )
        
        if is_bullish_regime:
            self.short_setup_armed = True
            self.short_setup_candles = 0
        elif self.short_setup_armed:
            self.short_setup_candles += 1
            if self.short_setup_candles > config.MAX_SETUP_WINDOW_CANDLES:
                self.short_setup_armed = False


        # --- Exit Logic ---
        
        if current_position == 'long':
            # Check opposite bearish conditions
            exit_bearish = (
                self.short_setup_armed and 
                latest_15m['supertrend_dir'] == -1 and 
                latest_15m['close'] < latest_15m['ema_200'] and 
                latest_15m['supertrend'] < latest_15m['ema_200'] and 
                latest_15m['ema_9'] < latest_15m['ema_200'] and 
                latest_15m['ema_21'] < latest_15m['ema_200'] and 
                latest_15m['ema_9'] < latest_15m['ema_21']
            )
            if exit_bearish:
                return {'signal': 'close_long', 'reason': 'Opposite bearish setup complete'}
                
        elif current_position == 'short':
            # Check opposite bullish conditions
            exit_bullish = (
                self.long_setup_armed and 
                latest_15m['supertrend_dir'] == 1 and 
                latest_15m['close'] > latest_15m['ema_200'] and 
                latest_15m['supertrend'] > latest_15m['ema_200'] and 
                latest_15m['ema_9'] > latest_15m['ema_200'] and 
                latest_15m['ema_21'] > latest_15m['ema_200'] and 
                latest_15m['ema_9'] > latest_15m['ema_21']
            )
            if exit_bullish:
                return {'signal': 'close_short', 'reason': 'Opposite bullish setup complete'}

        # --- Entry Logic ---
        
        if current_position is None:
            # Check Long Entry
            long_cond = (
                self.long_setup_armed and
                latest_15m['supertrend_dir'] == 1 and
                latest_15m['close'] > latest_15m['ema_200'] and
                latest_15m['supertrend'] > latest_15m['ema_200'] and
                latest_15m['ema_9'] > latest_15m['ema_200'] and
                latest_15m['ema_21'] > latest_15m['ema_200'] and
                latest_15m['ema_9'] > latest_15m['ema_21'] and
                latest_15m['adx'] >= config.ADX_MIN and
                latest_15m['ema_200_slope'] > 0 and
                latest_15m['distance_to_ema200'] >= (config.MIN_DISTANCE_TO_EMA200_ATR_MULTIPLIER * latest_15m['atr']) and
                latest_1h['close'] > latest_1h['ema_200_1h'] and
                latest_1h['ema_9_1h'] > latest_1h['ema_21_1h']
            )
            
            if long_cond:
                return {'signal': 'long', 'reason': 'Long entry conditions met'}

            # Check Short Entry
            short_cond = (
                self.short_setup_armed and
                latest_15m['supertrend_dir'] == -1 and
                latest_15m['close'] < latest_15m['ema_200'] and
                latest_15m['supertrend'] < latest_15m['ema_200'] and
                latest_15m['ema_9'] < latest_15m['ema_200'] and
                latest_15m['ema_21'] < latest_15m['ema_200'] and
                latest_15m['ema_9'] < latest_15m['ema_21'] and
                latest_15m['adx'] >= config.ADX_MIN and
                latest_15m['ema_200_slope'] < 0 and
                latest_15m['distance_to_ema200'] >= (config.MIN_DISTANCE_TO_EMA200_ATR_MULTIPLIER * latest_15m['atr']) and
                latest_1h['close'] < latest_1h['ema_200_1h'] and
                latest_1h['ema_9_1h'] < latest_1h['ema_21_1h']
            )
            
            if short_cond:
                return {'signal': 'short', 'reason': 'Short entry conditions met'}

        return {'signal': None, 'reason': ''}
