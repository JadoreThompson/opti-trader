import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from typing import List, Optional
from sqlalchemy import insert, select
import sqlalchemy
import sqlalchemy.exc

from config import DB_LOCK, REDIS_CLIENT
from db_models import Instruments
from utils.db import get_db_session
from .controllers import generate_ohlc
from .client_manager import ClientManager
from .models import (
    OHLC,
    InstrumentObject,
    PaginatedInstruments,
    Timeframe,
)
from ...middleware import JWT, encrypt_jwt, verify_jwt_http


instrument = APIRouter(prefix="/instrument", tags=["instrument"])
manager = ClientManager()


@instrument.get("/")
async def get_instrument(
    instrument: str,
    timeframe: Timeframe,
) -> List[Optional[OHLC]]:
    """ago in seconds"""
    return await generate_ohlc(instrument, timeframe)


@instrument.get("/list")
async def get_instruments(
    page: int = 0,
    quantity: int = 10,
    jwt: JWT = Depends(verify_jwt_http),    
) -> PaginatedInstruments:
    async with DB_LOCK:
        async with get_db_session() as sess:
            res = await sess.execute(
                select(Instruments.instrument).offset(page * quantity).limit(quantity + 1)
            )
            instruments = res.all()

    data = [item[0] for item in instruments[:quantity]]
    rtn_value: list[InstrumentObject] = []

    for instrument in data:
        prev: Optional[dict] = await REDIS_CLIENT.get(f"{instrument}.price")
        if prev:
            rtn_value.append(InstrumentObject(name=instrument, price=json.loads(prev)))

    return PaginatedInstruments(
        instruments=rtn_value, has_next_page=len(instruments) > quantity
    )


@instrument.post("/create")
async def create_instrument(
    body: InstrumentObject, jwt: JWT = Depends(verify_jwt_http)
) -> None:
    try:
        async with get_db_session() as sess:
            await sess.execute(
                insert(Instruments).values(
                    instrument=body.name, starting_price=body.price
                )
            )
            await sess.commit()
    except sqlalchemy.exc.IntegrityError:
        raise HTTPException(status_code=409, detail="Instrument exists")

    await REDIS_CLIENT.set(f"{body.name}.price", f"{body.price}")
    await REDIS_CLIENT.publish("instrument.new", body.name)


@instrument.websocket("/ws/")
async def instrument_ws(ws: WebSocket, instrument: str) -> None:
    try:
        await manager.connect(ws, instrument)
        
        while True:
            await ws.receive()
    except RuntimeError:
        pass
    finally:
        manager.disconnect(ws, instrument)
