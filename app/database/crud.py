from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.database.models import Base, TradeState, TradeHistory, SymbolCooldown
import datetime
import os

DB_URL = "sqlite+aiosqlite:///app.db"
engine = create_async_engine(DB_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_all_active_trades():
    async with async_session() as session:
        result = await session.execute(select(TradeState))
        return result.scalars().all()

async def get_trade(symbol: str):
    async with async_session() as session:
        result = await session.execute(select(TradeState).where(TradeState.symbol == symbol))
        return result.scalars().first()

async def save_trade(trade: TradeState):
    async with async_session() as session:
        session.add(trade)
        await session.commit()

async def delete_trade(symbol: str):
    async with async_session() as session:
        trade = await session.execute(select(TradeState).where(TradeState.symbol == symbol))
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
        # delete existing if any
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
