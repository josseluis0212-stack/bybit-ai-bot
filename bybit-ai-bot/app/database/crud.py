from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from app.database.models import Base, TradeState, TradeHistory, SymbolCooldown
import datetime
import os

DB_URL = "sqlite+aiosqlite:///app.db"
engine = create_async_engine(DB_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        # Note: in production with schema changes, alembic is better.
        # For this prototype we rely on drop/create if schemas mismatch or a manual clear.
        await conn.run_sync(Base.metadata.create_all)

async def get_all_active_trades():
    async with async_session() as session:
        result = await session.execute(select(TradeState).where(TradeState.position_closed == False))
        return result.scalars().all()

async def get_active_trade(symbol: str):
    async with async_session() as session:
        result = await session.execute(select(TradeState).where(TradeState.symbol == symbol, TradeState.position_closed == False))
        return result.scalars().first()

async def get_trade(trade_id: str):
    async with async_session() as session:
        result = await session.execute(select(TradeState).where(TradeState.trade_id == trade_id))
        return result.scalars().first()

async def save_trade(trade: TradeState):
    async with async_session() as session:
        await session.merge(trade)
        await session.commit()

async def create_trade(symbol: str, signal: str, entry_price: float, stop_loss: float, qty: float, strategy: str, trade_id: str, position_size: float, atr: float, tp1_price: float, tp2_price: float, profit_lock_price: float):
    async with async_session() as session:
        new_trade = TradeState(
            symbol=symbol,
            side=signal,
            strategy=strategy,
            entry_price=entry_price,
            stop_loss=stop_loss,
            trade_id=trade_id,
            position_size=position_size,
            remaining_size=position_size,
            atr=atr,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            profit_lock_price=profit_lock_price,
            position_closed=False
        )
        session.add(new_trade)
        await session.commit()
        return new_trade

async def delete_trade(trade_id: str):
    async with async_session() as session:
        trade = await session.execute(select(TradeState).where(TradeState.trade_id == trade_id))
        trade = trade.scalars().first()
        if trade:
            await session.delete(trade)
            await session.commit()

async def add_history(symbol: str, side: str, entry_price: float, exit_price: float, pnl: float):
    async with async_session() as session:
        history = TradeHistory(symbol=symbol, side=side, entry_price=entry_price, exit_price=exit_price, pnl=pnl)
        session.add(history)
        await session.commit()

async def set_cooldown(symbol: str, minutes: int):
    async with async_session() as session:
        cooldown_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
        existing = await session.execute(select(SymbolCooldown).where(SymbolCooldown.symbol == symbol))
        existing = existing.scalars().first()
        if existing:
            await session.delete(existing)
        new_cooldown = SymbolCooldown(symbol=symbol, cooldown_until=cooldown_until)
        session.add(new_cooldown)
        await session.commit()

async def is_on_cooldown(symbol: str) -> bool:
    async with async_session() as session:
        result = await session.execute(select(SymbolCooldown).where(SymbolCooldown.symbol == symbol))
        cooldown = result.scalars().first()
        if cooldown:
            if datetime.datetime.utcnow() < cooldown.cooldown_until:
                return True
            else:
                await session.delete(cooldown)
                await session.commit()
        return False

async def clear_all_data():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
