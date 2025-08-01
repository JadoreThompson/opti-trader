from asyncio import create_task, wait_for, TimeoutError as AsyncioTimeoutError
from datetime import UTC, datetime, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocket, WebSocketState
from json import loads
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import literal, select, func, join
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from config import FUTURES_BOOKS_KEY, REDIS_CLIENT, SPOT_BOOKS_KEY
from db_models import Instruments, MarketData, OrderEvents, Orders
from enums import EventType, InstrumentEventType, MarketType
from models import SubscriptionRequest
from server.utils.db import depends_db_session
from utils.utils import get_datetime, get_timestamp
from .client_manager import ClientManager
from .models import Candle, InstrumentSummary, InstrumentSummaryFull, TimeFrame


route = APIRouter(prefix="/instrument", tags=["instrument"])
client_manager = ClientManager()


@route.websocket("/{instrument}/ws")
async def instrument_ws(instrument: str, ws: WebSocket):
    async def handle_message() -> None:
        message = await ws.receive_text()
        if message == "ping":
            return

        try:
            req = SubscriptionRequest(**loads(message))
        except ValidationError:
            return

        if req.subscribe is not None:
            client_manager.subscribe(instrument, req.subscribe, ws)
        if req.unsubscribe is not None:
            client_manager.unsubscribe(instrument, req.unsubscribe, ws)

    await ws.accept()
    timeout = 5

    if not client_manager.is_running:
        create_task(client_manager.run())

    try:
        client_manager.subscribe(instrument, InstrumentEventType.PRICE_UPDATE, ws)
        await ws.send_text("connected")

        while True:
            await wait_for(handle_message(), timeout)
    except (RuntimeError, WebSocketDisconnect, AsyncioTimeoutError) as e:
        pass
    finally:
        client_manager.unsubscribe(instrument, InstrumentEventType.PRICE_UPDATE, ws)
        client_manager.unsubscribe(instrument, InstrumentEventType.ORDERBOOK_UPDATE, ws)
        client_manager.unsubscribe(instrument, InstrumentEventType.RECENT_TRADE, ws)

        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()


@route.get("/{instrument}/candles", response_model=List[Candle])
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


@route.get("/{instrument}/summary")
async def get_instrument_summary(
    instrument: str, db_sess: AsyncSession = Depends(depends_db_session)
):
    res = await db_sess.execute(
        select(Instruments.instrument_id).where(Instruments.instrument == instrument)
    )
    instrument_id = res.scalar_one_or_none()

    if instrument_id is None:
        return JSONResponse(
            status_code=404, content={"error": "Instrument doesn't exist."}
        )

    cur_timestamp = get_datetime().timestamp()
    prior_24h = int((get_datetime() - timedelta(hours=24)).timestamp())

    res = await db_sess.execute(
        select(MarketData)
        .where(MarketData.time >= prior_24h)
        .order_by(MarketData.time.asc())
        .limit(1)
    )
    start = res.scalar_one_or_none()
    start_time = start.time if start is not None else 0

    res = await db_sess.execute(
        select(MarketData)
        .where(MarketData.time <= cur_timestamp)
        .order_by(MarketData.time.desc())
        .limit(1)
    )
    end = res.scalar_one_or_none()
    end_time = end.time if end is not None else int(cur_timestamp) * 1000

    res = await db_sess.execute(
        select(OrderEvents.price)
        .where(
            OrderEvents.event_type.in_(
                [
                    EventType.ORDER_PARTIALLY_FILLED,
                    EventType.ORDER_FILLED,
                    EventType.ORDER_PARTIALLY_CLOSED,
                    EventType.ORDER_CLOSED,
                ]
            )
        )
        .order_by(OrderEvents.created_at.desc())
        .limit(1)
    )
    cur_price = res.scalar_one_or_none()

    if start is None and end is None:
        return InstrumentSummaryFull(
            price=cur_price,
            high_24h=None,
            low_24h=None,
            volume_24h=None,
            change_24h=None,
        )

    res = await db_sess.execute(
        select(func.min(MarketData.price), func.max(MarketData.price)).where(
            MarketData.time >= start_time, MarketData.time <= end_time
        )
    )
    min_price, max_price = res.first()

    stmt = select(func.sum(Orders.quantity), func.sum(Orders.standing_quantity)).where(
        Orders.created_at >= datetime.fromtimestamp(start_time, UTC),
        Orders.created_at <= datetime.fromtimestamp(end_time, UTC),
    )
    res = await db_sess.execute(stmt)
    quantity, standing_quantity = res.first()
    volume = (quantity - standing_quantity) // 2

    start_price = start.price if start is not None else 0
    change24h_nominal = end.price - start_price
    change_24h = change24h_nominal / start_price

    return InstrumentSummaryFull(
        price=cur_price,
        high_24h=max_price,
        low_24h=min_price,
        volume_24h=volume,
        change_24h=change_24h * 100,
    )


@route.get("/summary")
async def get_instruments_summary(db_sess: AsyncSession = Depends(depends_db_session)):
    limit = 10
    cur_time = get_datetime()
    start_time, end_time = (cur_time - timedelta(hours=24)), cur_time

    instruments_subq = (
        select(Orders.instrument)
        .where(Orders.created_at >= start_time)
        .limit(limit)
        .scalar_subquery()
    )

    inst_mtype_subq = (
        select(
            Orders.instrument,
            Orders.market_type,
        )
        .where(
            Orders.created_at >= start_time,
            Orders.created_at <= end_time,
            Orders.instrument.in_(instruments_subq),
        )
        .group_by(Orders.instrument, Orders.market_type)
        .subquery()
    )

    start_price_sq = (
        select(MarketData.price.label("starting_price"), MarketData.instrument)
        .where(MarketData.time >= start_time.timestamp())
        .order_by(MarketData.time.asc())
        .limit(1)
        .subquery()
    )

    end_price_sq = (
        select(MarketData.price.label("ending_price"), MarketData.instrument)
        .where(MarketData.time <= end_time.timestamp())
        .order_by(MarketData.time.desc())
        .limit(1)
        .subquery()
    )

    # Final query
    price_join = join(
        start_price_sq,
        end_price_sq,
        start_price_sq.c.instrument == end_price_sq.c.instrument,
        full=True,  # full outer join
    )

    final_join = join(
        price_join,
        inst_mtype_subq,
        (start_price_sq.c.instrument == inst_mtype_subq.c.instrument)
        | (end_price_sq.c.instrument == inst_mtype_subq.c.instrument),
        isouter=True,  # left outer join
    )

    final_stmt = select(
        inst_mtype_subq.c.instrument,
        inst_mtype_subq.c.market_type,
        100
        * (end_price_sq.c.ending_price - start_price_sq.c.starting_price)
        / start_price_sq.c.starting_price,
    ).select_from(final_join)

    res = await db_sess.execute(final_stmt)

    summaries = []
    for inst, market_type, change_24h in res.all():
        cur_price = await REDIS_CLIENT.hget(
            FUTURES_BOOKS_KEY if market_type == MarketType.FUTURES else SPOT_BOOKS_KEY,
            inst,
        )
        summaries.append(
            InstrumentSummary(instrument=inst, price=cur_price, change_24h=change_24h)
        )
    return summaries
