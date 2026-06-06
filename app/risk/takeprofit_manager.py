from app.logger import logger

class TakeProfitManager:
    @staticmethod
    def calculate_tps(entry_price: float, sl_price: float, total_size: float, side: str) -> list:
        """
        Calculates a single TP level at 2:1 Risk:Reward ratio.
        Size: TP1=100% of total_size.
        """
        risk = abs(entry_price - sl_price)

        if side == "LONG":
            tp_price = entry_price + (risk * 2.0)
        else:  # SHORT
            tp_price = entry_price - (risk * 2.0)

        tps = [
            {"price": tp_price, "qty": total_size, "level": 1, "pct": 100}
        ]

        logger.info(f"[TP CALC] TP1 (2:1 R:R)={tp_price:.6f}({total_size})")
        return tps