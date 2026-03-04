import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Trade
import logging

logger = logging.getLogger(__name__)

DB_PATH = 'sqlite:///database/trading_bot.db'

class DBManager:
    def __init__(self):
        # Asegurar de que la carpeta database exista
        os.makedirs('database', exist_ok=True)
        self.engine = create_engine(DB_PATH)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        logger.info("Base de datos local inicializada.")

    def add_trade(self, symbol, side, entry_price, sl, tp, qty, leverage, risk_usdt):
        session = self.Session()
        try:
            new_trade = Trade(
                symbol=symbol,
                side=side,
                status="OPEN",
                entry_price=entry_price,
                stop_loss=sl,
                take_profit=tp,
                qty=qty,
                leverage=leverage,
                risk_usdt=risk_usdt
            )
            session.add(new_trade)
            session.commit()
            logger.info(f"Operación guardada en DB: {symbol} {side}")
            return new_trade.id
        except Exception as e:
            logger.error(f"Error guardando trade en DB: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def get_open_trades_count(self) -> int:
        session = self.Session()
        try:
            count = session.query(Trade).filter(Trade.status == "OPEN").count()
            return count
        except Exception as e:
            logger.error(f"Error obteniendo conteo de trades abiertos: {e}")
            return settings.MAX_CONCURRENT_TRADES # Bloquear precaución
        finally:
            session.close()

    def get_open_trades(self):
        session = self.Session()
        try:
            return session.query(Trade).filter(Trade.status == "OPEN").all()
        finally:
            session.close()

    def close_trade(self, trade_id, exit_price, pnl_usdt, pnl_pct, reason):
        from datetime import datetime
        session = self.Session()
        try:
            trade = session.query(Trade).filter(Trade.id == trade_id).first()
            if trade:
                trade.status = "CLOSED"
                trade.exit_price = exit_price
                trade.pnl_usdt = pnl_usdt
                trade.pnl_pct = pnl_pct
                trade.close_reason = reason
                trade.close_time = datetime.utcnow()
                session.commit()
                logger.info(f"Operación cerrada en DB: {trade.symbol} (ID: {trade_id})")
                return trade
        except Exception as e:
            logger.error(f"Error cerrando trade en DB: {e}")
            session.rollback()
        finally:
            session.close()

db_manager = DBManager()
