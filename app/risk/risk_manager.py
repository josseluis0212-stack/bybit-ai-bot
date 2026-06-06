from app.exchange.bingx_client import AsyncBingXClient
from app.config import Config
from app.logger import logger

class RiskManager:
    def __init__(self):
        self.client = AsyncBingXClient()
        self.risk_per_trade = Config.RISK_PER_TRADE
        self.max_open_trades = Config.MAX_OPEN_TRADES
        self.leverage = Config.LEVERAGE

    async def can_open_trade(self, current_open_trades: int) -> bool:
        if current_open_trades >= self.max_open_trades:
            logger.info(f"[RISK] Max open trades reached ({self.max_open_trades}). Skipping.")
            return False
        return True

    def calculate_position_size(self, entry_price: float, sl_price: float, balance: float) -> float:
        """
        True Fixed Risk: If Stop Loss is hit, exactly $20 is lost.
        
        Formula: size = Risk_Amount / SL_Distance
        """
        if entry_price <= 0:
            return 0.0

        # Fixed parameters requested by user
        fixed_risk = self.risk_per_trade
        sl_distance = abs(entry_price - sl_price)
        if sl_distance == 0:
            return 0.0

        # Size in base currency (BTC, ETH, etc.)
        size = fixed_risk / sl_distance
        size = round(size, 6)

        logger.info(
            f"[RISK] True Fixed Risk | Target Risk={fixed_risk} USDT | "
            f"SL Distance={sl_distance:.6f} | Size={size:.6f} | Entry={entry_price} | SL={sl_price}"
        )
        return size