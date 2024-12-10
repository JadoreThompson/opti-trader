import  traceback
import asyncio
from datetime import datetime, timedelta
from uuid import UUID
from typing import List, Optional, Annotated

# SA
from sqlalchemy import select, insert
from sqlalchemy.exc import IntegrityError

# Local
from utils.arithemtic import get_quantitative_metrics, beta, get_benchmark_returns, get_ghpr
from utils.db import add_to_internal_cache, get_active_orders, get_orders, get_db_session, retrieve_from_internal_cache
from utils.auth import verify_jwt_token_http
from utils.portfolio import get_balance, get_monthly_returns
from enums import OrderStatus, GrowthInterval
from exceptions import DuplicateError, InvalidAction
from db_models import UserWatchlist, Users, Orders
from models.models import CopyTradeRequest, GrowthBody, GrowthModel, Order, OrderStatusBody, PerformanceMetrics, QuantitativeMetricsBody, QuantitativeMetrics, TickerDistribution, Username

# FA
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse


async def get_quant_metrics_handler(
    user_id: str,
    benchmark_ticker: str = "^GSPC",
    months_ago: int = 6,
    total_trades: int = 100,
    all_orders: list[dict] = None,
    balance: float = None,
    all_dates: set = None,
    **kwargs
) -> dict:
    """
    Handles the retrieval of common quantitative metrics

    Args:
        user_id (str).
        benchmark_ticker (str, optional): Risk Free Rate or Benchmark. Defaults to "^GSPC".
        months_ago (int, optional): How far ago to retrieve benchmark_ticker returns. Defaults to 6.
        total_trades (int, optional): The total span of trades to consider for risk of ruin. Defaults to 100.
        all_orders (list[dict], optional): List of all orders. Defaults to None.
        balance (float, optional): Defaults to None.
        all_dates (set, optional): All unique days YYYY-MM-DD for all_orders. Defaults to None.

    Returns:
        dict: Quantitative Metrics.
    """    
    params = {k: v for k, v in locals().items() if v}
    params['order_status'] = OrderStatus.CLOSED
    
    if not balance:
        balance = await get_balance(user_id)
    
    if not all_orders:
        all_orders = await get_orders(user_id=user_id, order_status=OrderStatus.CLOSED)
    
    if not all_dates:
        all_dates = set([order['created_at'].date() for order in all_orders])    
    
    monthly_returns: dict = get_monthly_returns(all_orders, all_dates)
    _, _, winrate = get_average_daily_return_and_total_profit_and_winrate(all_orders, all_dates)
    risk_per_trade = get_avg_risk_per_trade(all_orders, balance)
    
    data: dict = get_quantitative_metrics(
        risk_per_trade=risk_per_trade,
        winrate=winrate,
        monthly_returns=monthly_returns,
        balance=balance,
        benchmark_ticker=benchmark_ticker,
        months_ago=months_ago,
        total_num_trades=total_trades
    )
    
    data.update({
        'ahpr': get_ahpr(all_orders, all_dates, balance),
        'ghpr': get_ghpr([v for _, v in monthly_returns.items()]),
    })
    return data



def beta_wrapper(months_ago: int, benchmark_ticker: str, portfolio_returns: list):
    try:
        benchmark_returns = get_benchmark_returns(months_ago, benchmark_ticker)
        return beta(portfolio_returns, benchmark_returns)
    except InvalidAction:
        raise


def get_ahpr(
    orders: list[dict], 
    all_dates: list, 
    balance: float
) -> float:
    """
    Returns the average monthly return

    Args:
        orders (list[dict]): _description_
        all_dates (list): _description_

    Returns:
        dict[str, float]: The monthly return as a year-month for the key and the total
                        return for the month as the value  {2024-01: 100} 
    """    
    all_dates = set(f"{date_item:%Y-%m}" for date_item in all_dates)
    
    date_return = {key: 0 for key in all_dates}
    
    for order in orders:        
        start_price = (order.get('filled_price', None) or order.get('price', None))
        initial_value = order['quantity'] * start_price
        price_change = ((order['close_price'] - start_price) / start_price) + 1
        date_return[f"{order['created_at']:%Y-%m}"] += (initial_value * price_change) - initial_value
    
    try:
        return (((balance + sum(v for _, v in date_return.items()) / len(date_return)) - balance) / balance) * 100
    except ZeroDivisionError:
        return 0.0


def get_average_daily_return_and_total_profit_and_winrate(
    orders: list[dict], 
    all_dates: list
) -> tuple[float, float, float]:
    """
    Returns the return for all orders grouped by date
    
    Args:
        orders (list[dict])
        all_dates: List[datetime.date()] -> All must be unique

    Returns:
        dict
    """    
    date_return = {key: 0 for key in all_dates}
    total_return = 0
    wins = 0
    
    for order in orders:        
        try:
            realised_pnl = order['realised_pnl']
            date_return[order['created_at'].date()] += realised_pnl
            total_return += realised_pnl
            
            if realised_pnl > 0:
                wins += 1
        except TypeError:
            pass
    try:
        average_daily_return = sum(v for _, v in date_return.items()) / len(date_return)
    except ZeroDivisionError:
        average_daily_return = 0.0
    
    try:
        win_rate = (wins / len(orders)) * 100
    except ZeroDivisionError:
        win_rate = 0.0
    
    return average_daily_return, total_return, win_rate
    
    

def get_avg_risk_per_trade(
    all_orders: list[dict],
    balance: float
) -> float:
    """
    Returns the average percentage risk of a portfolio
    across all orders
    
    Args:
        all_orders (list[dict]): 
        balance (float): 

    Returns:
        float: Average percentage risk across all orders
    """    
    total_risk: float = 0.0
    
    for order in all_orders:
        q = order['quantity']
        risk = q * (
            order.get('filled_price', None) or order.get('price', None)
            or order.get('limit_price', None)
        )
        
        if order.get('stop_loss', None):
            risk = risk - (q * order['stop_loss'])
        
        total_risk += (risk / balance) * 100
    
    try:
        return round(total_risk / len(all_orders), 2)
    except ZeroDivisionError:
        return 0.0


# Initialisation
# ^^^^^^^^^^^^^^
portfolio = APIRouter(prefix='/portfolio', tags=['portfolio'])


@portfolio.post('/orders', response_model=List[Order])
async def orders(
    body: OrderStatusBody,
    user_id: str = Depends(verify_jwt_token_http),
):    
    
    if body.username:
        async with get_db_session() as session:
            try:
                user_id = await session.execute(
                    select(Users.user_id)
                    .where(
                        (Users.username == body.username) &
                        (Users.visible == True)
                    )
                )
                user_id = user_id.first()[0]
            except TypeError:
                raise InvalidAction("Account is private")
        
    existing_data: dict | None = retrieve_from_internal_cache(user_id, 'orders')
    tupled_order_status = tuple(body.order_status)
    
    if existing_data:
        if tupled_order_status in existing_data:
            return existing_data[tupled_order_status]
                
    try:    
        async with get_db_session() as session:                
            r = await session.execute(
                select(Orders)
                .where(
                    (Orders.order_status.in_(tupled_order_status)) &
                    (Orders.user_id == user_id))
            )
            
            all_orders = [Order(**vars(item)) for item in r.scalars().all()]
        add_to_internal_cache(user_id=user_id, channel='orders', value={tupled_order_status: all_orders})
        return all_orders
    except InvalidAction:
        raise
    except Exception as e:
        print('orders: ', type(e), str(e))


@portfolio.post("/performance", response_model=PerformanceMetrics)
async def performance(
    user_id: str = Depends(verify_jwt_token_http),
    body: Optional[Username] = None,
) -> PerformanceMetrics:
    """
    Returns performance metrics for the account

    Args:
        user_id (str, optional): JWT Token in header

    Returns:
        PerformanceMetrics()
    """
    
    if body:
        try:
            async with get_db_session() as session:
                r = await session.execute(
                    select(Users.user_id)
                    .where(
                        (Users.username == body.username) &
                        (Users.visible == True)
                    )
                )
                user_id = r.first()[0]
        except TypeError:
            raise InvalidAction("Account is private")
    
    main_dictionary = {}
    try:
        main_dictionary['balance'], all_orders = await asyncio.gather(*[
            get_balance(user_id),
            get_orders(**{'user_id': user_id, 'order_status': OrderStatus.CLOSED})
        ])
        
        all_dates = set(order['created_at'].date() for order in all_orders)

        quant_data: dict = await get_quant_metrics_handler(
            user_id=user_id, 
            all_orders=all_orders, 
            all_dates=all_dates,
            balance=main_dictionary['balance']
        )
        
        main_dictionary.update(
            dict(zip(
                ['daily', 'total_profit', 'winrate'], 
                get_average_daily_return_and_total_profit_and_winrate(all_orders, all_dates)
            ))
        )
        
        main_dictionary.update(quant_data)
        return PerformanceMetrics(**main_dictionary)
            
    except Exception as e:
        print('portfolio/performance/: ', type(e), str(e))


@portfolio.post("/quantitative", response_model=QuantitativeMetrics)
async def quantitative_metrics(
    body: Optional[QuantitativeMetricsBody] = None,
    user_id: str = Depends(verify_jwt_token_http),
) -> QuantitativeMetrics:
    """
    Args:
        user_id (str, optional): Depends(verify_jwt_token) Header JWT Verification.
        risk_free (Optional[float], optional): The risk free rate or benchmark rate to be comapred to.

    Returns:
        QuantitativeMetrics()
    """ 
    data = {}
    
    if body:
        try:
            async with get_db_session() as session:
                r = await session.execute(
                    select(Users.user_id)
                    .where(
                        (Users.username == body.username) &
                        (Users.visible == True)
                    )
                )
                data['user_id'] = r.first()[0]
                data.update(body.model_dump())
        except TypeError:
            raise InvalidAction("Account is private")
    else:
        data.update(QuantitativeMetricsBody().model_dump())
    
    data.update(await get_quant_metrics_handler(**locals()))
    return QuantitativeMetrics(**data)


@portfolio.post("/growth", response_model=List[GrowthModel])
async def growth(
    user_id: str = Depends(verify_jwt_token_http),
    body: Optional[GrowthBody] = None
) -> List[GrowthModel]:    
    """
    Returns growth list for the tradingview chart frontend
    Args:
        interval (GrowthInterval): 
        user_id (str, optional): Defaults to Depends(verify_jwt_token_http).

    Returns:
        list
    """ 
    if body.username:
        try:
            async with get_db_session() as session:
                r = await session.execute(
                    select(Users.user_id)
                    .where(
                        (Users.username == body.username) &
                        (Users.visible == True)
                    )
                )
                user_id = r.first()[0]
        except TypeError:
            raise InvalidAction("Account is private")
    
    existing_data: dict | None = retrieve_from_internal_cache(user_id, 'growth')
    interval = body.interval
    
    try:
        if interval in existing_data:
            return existing_data[interval]
    except TypeError:
        pass
    
    query = select(Orders).where((Orders.user_id == user_id) & (Orders.order_status == OrderStatus.CLOSED))
    today = datetime.now()
    today = datetime(day=today.day, month=today.month, year=today.year)
    
    if interval == GrowthInterval.DAY:
        query = query.where(Orders.created_at >= today)

    elif interval == GrowthInterval.WEEK:
        start_of_week = today - timedelta(days=today.weekday())
        query = query.where(Orders.created_at >= start_of_week)

    elif interval == GrowthInterval.MONTH:
        start_of_month = today.replace(day=1)
        query = query.where(Orders.created_at >= start_of_month)
    
    elif interval == GrowthInterval.YEAR:
        start_of_year = datetime(year=today.year, month=1, day=1)
        query = query.where(Orders.created_at >= start_of_year)
    
    async def retrieve_orders(query) -> list:
        async with get_db_session() as session:
            r = await session.execute(query)
            return r.scalars().all()
    
    try:
        all_orders, current_balance = await asyncio.gather(*[retrieve_orders(query), get_balance(user_id)])
    except Exception as e:
        print("Growth Error: ", type(e), str(e))
        print('-' * 10)
            
    starting_period_balance: float = current_balance
    
    all_orders_with_gain = []
    return_list = []
        
    for order in all_orders:
        starting_period_balance += -1 * order.realised_pnl
        all_orders_with_gain.append({'date': order.created_at, 'gain': order.realised_pnl})

    for order in all_orders_with_gain:
        return_list.append({
            'time': int(order['date'].timestamp()),
            'value': round((order['gain'] / starting_period_balance) * 100, 2)
        })
    
    return_list.sort(key= lambda item: item['time'])
    return_list = [GrowthModel(**item) for item in return_list if return_list.count(item) == 1]
    add_to_internal_cache(user_id, 'growth', {interval: return_list})
    return return_list
    

@portfolio.post("/distribution", response_model=List[TickerDistribution])
async def distribution(
    user_id: str = Depends(verify_jwt_token_http),
    body: Optional[Username] = None
) -> List[TickerDistribution]:
    
    if body:
        try:
            async with get_db_session() as session:
                r = await session.execute(
                    select(Users.user_id)
                    .where(
                        (Users.username == body.username) &
                        (Users.visible == True)
                    )
                )
                user_id = r.first()[0]
        except TypeError:
            raise InvalidAction("Account is private")
    
    all_orders = await get_active_orders(user_id)
    ticker_map = {
        ticker: 0
        for ticker in 
        set(order['ticker'] for order in all_orders)
    }
    
    for order in all_orders:
        price = order['price'] or order['filled_price']
        ticker_map[order['ticker']] += price * order['quantity']
    total = sum(ticker_map.values())
    ticker_map = {
        k: (v / total)
        for k, v in ticker_map.items()
    }
    
    return [TickerDistribution(name=key, value=value) for key, value in ticker_map.items()]
    
    
@portfolio.post('/weekday-results')
async def wins_losses_weekday(
    user_id: str = Depends(verify_jwt_token_http),
    body: Optional[Username] = None
):
    constraints = {'user_id': user_id, 'order_status': OrderStatus.CLOSED}

    
    if body:
        try:
            async with get_db_session() as session:
                r = await session.execute(
                    select(Users.user_id)
                    .where(
                        (Users.username == body.username) &
                        (Users.visible == True)
                    )
                )
                constraints.update({'user_id': r.first()[0]})
        except TypeError:
            raise InvalidAction("Account is private")
            
    all_orders = await get_orders(**constraints)
    num_range = range(7)
    wins = [0 for _ in num_range]    
    losses = [0 for _ in num_range]
    
    for order in all_orders:
        realised_pnl = order['realised_pnl']
        if realised_pnl < 0:
            losses[order['created_at'].weekday()] += 1
        elif realised_pnl > 0:
            wins[order['created_at'].weekday()] += 1
    
    return JSONResponse(status_code=200, content={'wins': wins, 'losses': losses})


@portfolio.post("/copy")
async def copy_trades(body: CopyTradeRequest, user_id: str = Depends(verify_jwt_token_http)):
    """
    Enters a record into DB
    
    Args:
        body (CopyTradeRequest):
        user_id (str, optional): Defaults to Depends(verify_jwt_token_http).

    Raises:
        InvalidAction: _description_
        DuplicateError: _description_
    
    Returns:
        None: body.username is invalid. This may be due to the user not existing or more than likely
        the target user has visible set to False
    """    
    try:
        async with get_db_session() as session:
            r = await session.execute(
                select(Users.user_id)
                .where(
                    (Users.username == body.username)
                    & (Users.visible == True)
                )
            )
            
            m_user = r.first()
            if m_user is None:
                raise InvalidAction("User doesn't exist")
            
            existing_entry = await session.execute(
                select(UserWatchlist)
                .where(
                    (UserWatchlist.master == m_user[0])
                    & (UserWatchlist.watcher == user_id)
                )
            )
            
            existing_entry = existing_entry.first()
            if existing_entry is not None:
                existing_entry = existing_entry[0]
                existing_entry.limit_orders = body.limit_orders
                existing_entry.market_orders = body.market_orders
            else:
                await session.execute(
                    insert(UserWatchlist)
                    .values(
                        master=m_user[0], 
                        watcher=UUID(f'{{{user_id}}}'),
                        limit_orders=body.limit_orders,
                        market_orders=body.market_orders 
                    )
                )
                
            await session.commit()
    except InvalidAction:
        raise
    except IntegrityError:
        raise DuplicateError(f"Already subcribed to {body.username}")
    except Exception as e:
        print('copy trades: ', type(e), str(e))
        