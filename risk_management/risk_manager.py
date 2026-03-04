import logging
from config.settings import settings

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self):
        self.leverage = settings.LEVERAGE
        self.trade_amount_usdt = settings.TRADE_AMOUNT_USDT
        self.max_concurrent_trades = settings.MAX_CONCURRENT_TRADES

    def can_open_new_trade(self, current_open_trades_count: int, available_wallet_balance: float) -> bool:
        """
        Verifica si se cumplen las reglas para abrir una nueva operación.
        """
        if current_open_trades_count >= self.max_concurrent_trades:
            logger.info(f"Bloqueo: Máximo de operaciones alcanzado ({self.max_concurrent_trades})")
            return False
            
        # El margen requerido es trade_amount / leverage. Añadimos un pequeño buffer (1.1)
        required_margin = (self.trade_amount_usdt / self.leverage) * 1.1 
        
        if available_wallet_balance < required_margin:
            logger.info(f"Bloqueo: Margen insuficiente. Requerido: {required_margin:.2f}, Disponible: {available_wallet_balance:.2f}")
            return False
            
        return True

    def calculate_position_size(self, current_price: float) -> float:
        """
        Calcula el tamaño de la posición en monedas base (ej: BTC) 
        dado un tamaño fijo en USDT apalancado.
        
        Si quiero abrir 50 USDT en la posición total con 5x, 
        el valor nocional de la posición será 50 USDT.
        """
        if current_price <= 0:
            return 0.0
            
        qty = self.trade_amount_usdt / current_price
        return qty

risk_manager = RiskManager()
