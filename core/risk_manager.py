class RiskManager:
    def __init__(self, config):
        self.config = config
        self.daily_pnl = 0.0

    def calculate_position_size(self, balance):
        return min(self.config['trading']['monto_por_operacion'], balance * 0.2)

    def calculate_sl_tp(self, side, entry_price, atr):
        sl_dist = atr * self.config['riesgo']['stop_loss_atr_multiplicador']
        
        if side == "Buy":
            sl = entry_price - sl_dist
            tp = entry_price + (sl_dist * self.config['riesgo']['take_profit_ratio'])
        else:
            sl = entry_price + sl_dist
            tp = entry_price - (sl_dist * self.config['riesgo']['take_profit_ratio'])
            
        return round(sl, 4), round(tp, 4)

    def check_daily_drawdown(self, current_balance, initial_balance):
        drawdown = ((initial_balance - current_balance) / initial_balance) * 100
        if drawdown >= self.config['riesgo']['max_drawdown_diario']:
            return False # Riesgo excedido
        return True

    def get_trailing_stop_price(self, side, entry_price, current_price, current_sl):
        activation_pct = self.config['riesgo']['trailing_stop_activacion'] / 100
        
        if side == "Buy":
            profit = (current_price - entry_price) / entry_price
            if profit >= activation_pct:
                new_sl = current_price * (1 - 0.01) # 1% de distancia
                return max(current_sl, new_sl)
        else:
            profit = (entry_price - current_price) / entry_price
            if profit >= activation_pct:
                new_sl = current_price * (1 + 0.01)
                return min(current_sl, new_sl)
        return current_sl
