from datetime import datetime, timedelta
from fastapi import APIRouter, WebSocket
from typing import Optional
from sqlalchemy import select

from db_models import MarketData
from utils.db import get_db_session
from .controllers import generate_ohlc
from .manager import ClientManager
from .models import OHLC, Timeframe

instrument = APIRouter(prefix="/instrument", tags=["instrument"])
manager = ClientManager()


@instrument.websocket("/ws/")
async def instrument_ws(ws: WebSocket, instrument: str) -> None:
    try:
        await manager.connect(ws, instrument)

        while True:
            await ws.receive()
    except Exception as e:
        if not isinstance(e, RuntimeError):
            print(type(e), str(e))
    finally:
        manager.disconnect(ws, instrument)


@instrument.get("/")
async def get_instrument(
    instrument: str, timeframe: Timeframe, ago: int = 432000
) -> list[Optional[OHLC]]:
    """ago in seconds"""
    async with get_db_session() as sess:
        res = await sess.execute(
            select(MarketData).where(
                (MarketData.instrument == instrument)
                & (
                    MarketData.time
                    > (datetime.now() - timedelta(minutes=ago)).timestamp()
                )
            )
        )
        data = res.scalars().all()

    if not data:
        return []
    return generate_ohlc(data, timeframe)
