from asyncio import create_task
from fastapi import APIRouter, Depends, Query
from fastapi.websockets import WebSocket, WebSocketState
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import MarketData
from server.utils.db import depends_db_session
from utils.utils import get_timestamp
from .client_manager import ClientManager
from .models import Candle, TimeFrame


route = APIRouter(prefix="/instrument", tags=["instrument"])
client_manager = ClientManager()


@route.get("/{instrument}/candles")
async def get_instrument(
    instrument: str,
    time_frame: TimeFrame = Query(),
    db_sess: AsyncSession = Depends(depends_db_session),
):
    data = await db_sess.execute(
        select(MarketData).where(MarketData.instrument == instrument)
    )
    market_data = data.scalars().all()

    if not market_data:
        return []

    timeframe_to_seconds = {
        TimeFrame.S5: 5,
        TimeFrame.M1: 60,
        TimeFrame.M5: 5 * 60,
        TimeFrame.H1: 60 * 60,
        TimeFrame.H4: 4 * 60 * 60,
        TimeFrame.D1: 24 * 60 * 60,
    }

    seconds = timeframe_to_seconds[time_frame]
    first = market_data[0]
    candles: list[Candle] = [
        Candle(
            open=first.price,
            high=first.price,
            low=first.price,
            close=first.price,
            time=first.time - (first.time % seconds),
        )
    ]

    for mdata in market_data[1:]:
        prev_candle = candles[-1]
        elapsed_time = mdata.time - prev_candle.time
        gaps = int(elapsed_time // seconds)

        if gaps < 1:
            prev_candle.high = max(prev_candle.high, mdata.price)
            prev_candle.low = min(prev_candle.low, mdata.price)
            prev_candle.close = mdata.price
        elif gaps == 1:
            candles.append(
                Candle(
                    open=mdata.price,
                    high=mdata.price,
                    low=mdata.price,
                    close=mdata.price,
                    time=mdata.time - (mdata.time % seconds),
                )
            )
        else:
            for i in range(1, 1 + gaps):
                candles.append(
                    Candle(
                        open=prev_candle.close,
                        high=prev_candle.close,
                        low=prev_candle.close,
                        close=prev_candle.close,
                        time=prev_candle.time + (i * seconds),
                    )
                )

            prev_candle.high = max(prev_candle.high, mdata.price)
            prev_candle.low = min(prev_candle.low, mdata.price)
            prev_candle.close = mdata.price

    prev_candle = candles[-1]
    cur_ts = get_timestamp()

    for i in range(1, 1 + int((cur_ts - prev_candle.time) // seconds)):
        candles.append(
            Candle(
                open=prev_candle.close,
                high=prev_candle.close,
                low=prev_candle.close,
                close=prev_candle.close,
                time=prev_candle.time + (i * seconds),
            )
        )

    return candles


@route.websocket("/{instrument}/ws")
async def instrument_ws(instrument: str, ws: WebSocket):
    await ws.accept()

    if not client_manager.is_running:
        create_task(client_manager.run())

    client_manager.append(instrument, ws)

    try:
        while True:
            await ws.receive()
    except (RuntimeError, WebSocketDisconnect):
        pass
    finally:
        client_manager.remove(instrument, ws)
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
