from app.logger import logger

class TakeProfitManager:
    @staticmethod
    def calculate_tps(entry_price: float, sl_price: float, total_size: float, side: str) -> list:
        """
        Calculates Tiered Take Profits.
        TP1 = 50% size at 1.5x Risk
        TP2 = 50% size at 5.0x Risk
        """
        risk = abs(entry_price - sl_price)

        if side == "LONG":
            tp1_price = entry_price + (risk * 1.5)
            tp2_price = entry_price + (risk * 5.0)
        else:  # SHORT
            tp1_price = entry_price - (risk * 1.5)
            tp2_price = entry_price - (risk * 5.0)

        qty1 = round(total_size * 0.5, 4)
        qty2 = total_size - qty1  # Ensure exact total

        tps = [
            {"price": tp1_price, "qty": qty1, "level": 1, "pct": 50},
            {"price": tp2_price, "qty": qty2, "level": 2, "pct": 50}
        ]

        logger.info(f"[TP CALC] TP1={tp1_price:.6f}({qty1}) | TP2={tp2_price:.6f}({qty2})")
        return tps