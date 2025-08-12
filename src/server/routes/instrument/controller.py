from datetime import datetime
from typing import Literal
from sqlalchemy import text, insert
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Instruments, Trades
from enums import TimeFrame
from .models import InstrumentCreate, OHLC


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
    Fetches OHLC data for a given instrument and timeframe using a raw SQL query
    for performance and flexibility with date functions.
    """

    query = text(
        f"""
        SELECT
            time_bucket(CAST(:timeframe AS INTERVAL), executed_at) AS bucket,
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

    result = await db_sess.execute(
        query, {"instrument_id": instrument_id, "timeframe": timeframe.value}
    )

    ohlc_data = [
        OHLC(
            time=row.bucket,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
        )
        for row in result.all()
    ]
    return ohlc_data
