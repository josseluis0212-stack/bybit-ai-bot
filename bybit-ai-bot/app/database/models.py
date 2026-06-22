from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class TradeState(Base):
    __tablename__ = 'trade_state'
    trade_id = Column(String, primary_key=True)
    symbol = Column(String, index=True)
    side = Column(String)
    strategy = Column(String, nullable=True, default="Unknown")
    entry_price = Column(Float)
    position_size = Column(Float)
    atr = Column(Float)
    stop_loss = Column(Float)
    tp1_price = Column(Float)
    tp2_price = Column(Float)
    profit_lock_price = Column(Float)
    highest_price = Column(Float, nullable=True)
    lowest_price = Column(Float, nullable=True)
    remaining_size = Column(Float)
    tp1_filled = Column(Boolean, default=False)
    tp2_filled = Column(Boolean, default=False)
    profit_lock_active = Column(Boolean, default=False)
    trailing_active = Column(Boolean, default=False)
    position_closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
class TradeHistory(Base):
    __tablename__ = 'trade_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String)
    side = Column(String)
    entry_price = Column(Float)
    exit_price = Column(Float)
    pnl = Column(Float)
    closed_at = Column(DateTime, default=datetime.datetime.utcnow)

class SymbolCooldown(Base):
    __tablename__ = 'symbol_cooldown'
    symbol = Column(String, primary_key=True)
    cooldown_until = Column(DateTime)
