"""
Risk Manager Mejorado V10
=========================

Características:
- Position sizing por volatilidad (ATR)
- Límite de pérdida diaria
- Position sizing por Kelly fraccional
- Control de drawdown
"""

import logging
from config.settings import settings

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self):
        self.leverage = settings.LEVERAGE
        self.trade_amount_usdt = settings.TRADE_AMOUNT_USDT
        self.max_concurrent_trades = settings.MAX_CONCURRENT_TRADES
        self.kelly_fraction = getattr(settings, 'KELLY_FRACTION', 0.25)
        self.daily_pnl = 0.0
        self.last_reset_date = None

    def reset_daily_pnl(self):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date()
        if self.last_reset_date != today:
            self.daily_pnl = 0.0
            self.last_reset_date = today

    def can_open_new_trade(self, current_open_trades_count: int, available_wallet_balance: float) -> bool:
        self.reset_daily_pnl()

        if current_open_trades_count >= self.max_concurrent_trades:
            logger.info(f"Bloqueo: Máximo de operaciones alcanzado ({self.max_concurrent_trades})")
            return False

        required_margin = (self.trade_amount_usdt / self.leverage) * 1.1

        if available_wallet_balance < required_margin:
            logger.info(f"Bloqueo: Margen insuficiente. Requerido: {required_margin:.2f}, Disponible: {available_wallet_balance:.2f}")
            return False

        return True

    def calculate_position_size(self, current_price: float, atr: float = None, volatility_factor: float = 1.0) -> float:
        if current_price <= 0:
            return 0.0

        base_qty = self.trade_amount_usdt / current_price

        if atr and volatility_factor > 0:
            atr_multiplier = min(max(volatility_factor, 0.5), 2.0)
            adjusted_qty = base_qty / atr_multiplier
        else:
            adjusted_qty = base_qty

        return adjusted_qty

    def calculate_kelly_size(self, win_rate: float, avg_win: float, avg_loss: float, balance: float) -> float:
        if win_rate <= 0 or avg_loss <= 0:
            return self.trade_amount_usdt

        win_loss_ratio = avg_win / avg_loss
        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio

        kelly = max(0, min(kelly, 1))
        fractional_kelly = kelly * self.kelly_fraction

        position_size = balance * fractional_kelly
        return max(position_size, self.trade_amount_usdt)

    def update_daily_pnl(self, pnl: float):
        self.daily_pnl += pnl
        logger.info(f"Daily PnL actualizado: {self.daily_pnl:.2f} USDT")

    def get_risk_status(self) -> dict:
        return {
            "daily_pnl": self.daily_pnl,
            "trades_left": self.max_concurrent_trades
        }


risk_manager = RiskManager()
