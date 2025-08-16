from datetime import timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Orders, Transactions, Trades
from enums import Side
from utils.utils import get_datetime
from .models import HistoryInterval


async def get_portfolio_history(
    interval: HistoryInterval,
    user_id: str | UUID,
    points: int,
    db: AsyncSession,
) -> list[dict[str, float]]:
    """
    Calculates the total portfolio value for a user at different points in time
    over a specified historical interval.

    The portfolio value is the sum of the user's cash balance and the market
    value of all their asset holdings at each point in time.

    Args:
        db: The SQLAlchemy database session.
        user_id: The UUID of the user whose portfolio history is being queried.
        interval: The time interval to look back ('1d', '1w', '1m', '3m', '6m', '1y').
        points: The number of data points to generate within the interval.

    Returns:
        A list of dictionaries, where each dictionary contains a 'time' (datetime)
        and 'value' (total portfolio value) for that point in time. Ordered from
        oldest to most recent.
    """
    interval_map: dict[HistoryInterval, timedelta] = {
        "1d": timedelta(days=1),
        "1w": timedelta(weeks=1),
        "1m": timedelta(days=30),
        "3m": timedelta(days=90),
        "6m": timedelta(days=180),
        "1y": timedelta(days=365),
    }

    if interval not in interval_map:
        raise ValueError(
            f"Invalid interval: {interval}. Must be one of {list(interval_map.keys())}"
        )

    end_time = get_datetime()
    total_delta = interval_map[interval]

    if points < 1:
        raise ValueError("Points must be at least 1.")
    elif points == 1:
        timestamps = [end_time]
    else:
        time_step = total_delta / (points - 1)
        timestamps = [end_time - i * time_step for i in range(points)]

    user_instruments_stmt = (
        select(Trades.instrument_id).where(Trades.user_id == user_id).distinct()
    )
    instrument_ids = (await db.execute(user_instruments_stmt)).scalars().all()

    results: list[dict] = []

    for t in timestamps:
        cash_stmt = (
            select(Transactions.balance)
            .where(Transactions.user_id == user_id, Transactions.created_at <= t)
            .order_by(Transactions.created_at.desc())
            .limit(1)
        )
        cash_at_t = (await db.execute(cash_stmt)).scalar_one_or_none() or 0.0

        total_asset_value = 0.0

        for instrument_id in instrument_ids:
            buy_sum = func.sum(
                case((Orders.side == Side.BID.value, Trades.quantity), else_=0.0)
            )
            sell_sum = func.sum(
                case((Orders.side == Side.ASK.value, Trades.quantity), else_=0.0)
            )

            quantity_stmt = (
                select(buy_sum - sell_sum)
                .select_from(Trades)
                .join(Orders, Trades.order_id == Orders.order_id)
                .where(
                    Trades.user_id == user_id,
                    Trades.instrument_id == instrument_id,
                    Trades.executed_at <= t,
                )
            )
            quantity_at_t = (await db.execute(quantity_stmt)).scalar_one_or_none() or 0.0

            if quantity_at_t == 0:
                continue

            price_stmt = (
                select(Trades.price)
                .where(
                    Trades.instrument_id == instrument_id,
                    Trades.executed_at <= t,
                )
                .order_by(Trades.executed_at.desc())
                .limit(1)
            )
            price_at_t = (await db.execute(price_stmt)).scalar_one_or_none() or 0.0

            total_asset_value += quantity_at_t * price_at_t

        total_portfolio_value = cash_at_t + total_asset_value
        results.append({"time": t, "value": round(total_portfolio_value, 2)})

    return results[::-1]
