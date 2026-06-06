from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import declarative_base
import datetime

Base = declarative_base()

class TradeState(Base):
    __tablename__ = 'trade_state'
    symbol = Column(String, primary_key=True)
    signal = Column(String)
    entry_price = Column(Float)
    sl_price = Column(Float)
    target_distance = Column(Float)
    qty = Column(Float)
    filled = Column(Boolean, default=False)
    entry_order_id = Column(String, nullable=True)
    sl_order_id = Column(String, nullable=True)
    tp1_order_id = Column(String, nullable=True)
    trailing_active = Column(Boolean, default=False)
    highest_price = Column(Float, nullable=True)
    breakeven_hit = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
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
