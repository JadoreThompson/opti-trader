from datetime import timedelta

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Instruments, Trades
from enums import TimeFrame
from utils.utils import get_datetime
from .models import InstrumentCreate, OHLC, Stats24h


async def create_instrument(
    db_sess: AsyncSession, details: InstrumentCreate
) -> Instruments:
    """Creates a new instrument in the database."""
    instrument = Instruments(**details.model_dump())
    db_sess.add(instrument)
    await db_sess.commit()
    await db_sess.refresh(instrument)
    # Here you might signal the engine manager to add a new context
    # to the running engine, but that's a more advanced feature.
    return instrument


async def get_ohlc_data(
    db_sess: AsyncSession,
    instrument_id: str,
    timeframe: TimeFrame,
) -> list[OHLC]:
    """
    Fetches OHLC data for a given instrument and timeframe. Requires the
    timescaledb (now tigerdata) extension.

    If you don't have it, connect to the DB and run
    ```
    CREATE EXTENSION IF NOT EXISTS timescaledb;
    ```
    """

    query = text(
        f"""
        SELECT
            time_bucket(CAST('{timeframe.to_interval()}' AS INTERVAL), executed_at) AS bucket,
            first(price, executed_at) AS open,
            max(price) AS high,
            min(price) AS low,
            last(price, executed_at) AS close
        FROM trades
        WHERE instrument_id = :instrument_id
        GROUP BY bucket
        ORDER BY bucket;
    """
    )

    result = await db_sess.execute(query, {"instrument_id": instrument_id})

    ohlc_data = [
        OHLC(
            time=row.bucket.timestamp(),
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
        )
        for row in result.all()
    ]
    return ohlc_data


async def calculate_24h_stats(db_sess: AsyncSession, instrument_id: str):
    """
    Calculate 24h trading stats for a given instrument.

    Returns: Stats24h
    """
    now = get_datetime()
    since = now - timedelta(hours=24)

    stmt_stats = select(
        (func.sum(Trades.quantity) / 2).label("volume"),
        func.max(Trades.price).label("high"),
        func.min(Trades.price).label("low"),
    ).where(
        Trades.instrument_id == instrument_id,
        Trades.executed_at >= since,
    )

    result = await db_sess.execute(stmt_stats)
    stats = result.one()

    stmt_first = (
        select(Trades.price)
        .where(
            Trades.instrument_id == instrument_id,
            Trades.executed_at >= since,
        )
        .order_by(Trades.executed_at.asc())
        .limit(1)
    )
    first_trade = (await db_sess.execute(stmt_first)).scalar()

    stmt_last = (
        select(Trades.price)
        .where(
            Trades.instrument_id == instrument_id,
            Trades.executed_at >= since,
        )
        .order_by(Trades.executed_at.desc())
        .limit(1)
    )
    last_trade = (await db_sess.execute(stmt_last)).scalar()

    if first_trade and last_trade:
        h24_change = ((last_trade - first_trade) / first_trade) * 100
    else:
        h24_change = 0.0

    return Stats24h(
        h24_volume=stats.volume or 0.0,
        h24_change=h24_change,
        h24_high=stats.high or 0.0,
        h24_low=stats.low or 0.0,
        price=last_trade,
    )


async def get_24h_stats_all(
    db_sess: AsyncSession, instrument_id: str | None = None
) -> None:
    now = get_datetime()
    since = now - timedelta(hours=24)

    first_trade = (
        select(Trades.instrument_id, Trades.price.label("first_price"))
        .where(Trades.executed_at >= since)
        .order_by(Trades.instrument_id, Trades.executed_at.asc())
        .distinct(Trades.instrument_id)
        .subquery()
    )

    last_trade = (
        select(Trades.instrument_id, Trades.price.label("last_price"))
        .where(Trades.executed_at >= since)
        .order_by(Trades.instrument_id, Trades.executed_at.desc())
        .distinct(Trades.instrument_id)
        .subquery()
    )

    # Main aggregation
    stmt = (
        select(
            Trades.instrument_id,
            (func.sum(Trades.quantity) / 2).label("volume"),
            last_trade.c.last_price.label("price"),
            (
                (
                    (last_trade.c.last_price - first_trade.c.first_price)
                    / first_trade.c.first_price
                )
                * 100
            ).label("h24_change"),
        )
        .join(first_trade, first_trade.c.instrument_id == Trades.instrument_id)
        .join(last_trade, last_trade.c.instrument_id == Trades.instrument_id)
        .group_by(
            Trades.instrument_id,
            last_trade.c.last_price,
            first_trade.c.first_price,
        )
        .order_by(desc("volume"))
        .limit(20)
    )

    stmt = stmt.where(Trades.executed_at >= since)
    if instrument_id is not None:
        stmt = stmt.where(Trades.instrument_id.like(f"%{instrument_id}%"))

    result = await db_sess.execute(stmt)
    return result.all()
