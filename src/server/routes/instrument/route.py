from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db_models import Instruments
from enums import TimeFrame
from server.utils.db import depends_db_session
from .controller import get_ohlc_data, create_instrument as create_instrument_controller
from .models import InstrumentCreate, OHLC

route = APIRouter(prefix="/instruments", tags=["instrument"])


@route.post("/", status_code=201)
async def create_instrument(
    details: InstrumentCreate,
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """Creates a new tradeable instrument."""
    try:
        instrument = await create_instrument_controller(db_sess, details)
        return instrument
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Instrument already exists.")


@route.get("/{instrument_id}/ohlc", response_model=list[OHLC])
async def get_instrument_ohlc(
    instrument_id: str,
    timeframe: TimeFrame,
    db_sess: AsyncSession = Depends(depends_db_session),
):
    """
    Retrieves Open-High-Low-Close (OHLC) data for a given instrument.
    Requires TimescaleDB with the timescale_toolkit extension for `time_bucket`,
    `first`, and `last` functions.
    """
    try:
        data = await get_ohlc_data(db_sess, instrument_id, timeframe)
        return data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
