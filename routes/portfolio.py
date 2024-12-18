import  traceback
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID
from typing import List, Optional
from fastapi.responses import JSONResponse
from sqlalchemy import select

# Local
from utils.arithemtic import get_quantitative_metrics, beta, get_benchmark_returns, get_ghpr
from utils.db import add_to_internal_cache, get_active_orders, get_orders, get_db_session, retrieve_from_internal_cache
from utils.auth import verify_jwt_token_http
from utils.portfolio import get_balance, get_monthly_returns
from enums import OrderStatus, GrowthInterval
from exceptions import InvalidAction
from db_models import Users, Orders
from models.models import GrowthModel, Order, OrderRequest, PerformanceMetrics, QuantitativeMetrics, TickerDistribution

# FA
from fastapi import APIRouter, Depends


async def get_quant_metrics_handler(
    user_id: str,
    benchmark_ticker: str = "^GSPC",
    months_ago: int = 6,
    total_trades: int = 100,
    all_orders: list[dict] = None,
    balance: float = None,
    all_dates: set = None
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
    
    monthly_returns: dict = await get_monthly_returns(all_orders, all_dates)
    _, _, winrate = await get_average_daily_return_and_total_profit_and_winrate(all_orders, all_dates)
    risk_per_trade = await get_avg_risk_per_trade(all_orders, balance)
    
    data: dict = await get_quantitative_metrics(
        risk_per_trade=risk_per_trade,
        winrate=winrate,
        monthly_returns=monthly_returns,
        balance=balance,
        benchmark_ticker=benchmark_ticker,
        months_ago=months_ago,
        total_num_trades=total_trades
    )
    
    more_metrics: dict = {
        'ahpr': get_ahpr(all_orders, all_dates, balance),
        'ghpr': get_ghpr([v for _, v in monthly_returns.items()]),
    }
    
    data.update(dict(
        zip([k for k in more_metrics], await asyncio.gather(*[v for _, v in more_metrics.items()]))
    ))
    
    return data



async def get_beta(months_ago: int, benchmark_ticker: str, portfolio_returns: list):
    try:
        benchmark_returns = await get_benchmark_returns(months_ago, benchmark_ticker)
        return await beta(portfolio_returns, benchmark_returns)
    except InvalidAction:
        raise


async def get_ahpr(
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


async def get_average_daily_return_and_total_profit_and_winrate(
    orders: list[dict], 
    all_dates: list
) -> tuple[float, float]:
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
            start_price = (order.get('filled_price', None) or order.get('price', None))
            initial_value = order['quantity'] * start_price
            price_change = ((order['close_price'] - start_price) / start_price) + 1
            
            order_return = round((initial_value * price_change) - initial_value, 2)
            date_return[order['created_at'].date()] += order_return
            total_return += order_return
            
            if order_return > 0:
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
    
    

async def get_avg_risk_per_trade(
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
portfolio = APIRouter(prefix='/portfolio', tags=['portfolio'])


@portfolio.get('/orders', response_model=List[Order])
async def orders(
    user_id: str = Depends(verify_jwt_token_http),
    order_status: Optional[OrderStatus] = None
) -> list[dict]:
    """
    Returns all trades based on the constraints
    Args:
        user_id (UUID)
        order_status (OrderStatus)

    Returns:
        list[dict]: all orders based on the constraints
    """
    return [Order(**order) for order in await get_orders(**locals())]


@portfolio.get("/performance", response_model=PerformanceMetrics)
async def performance(user_id: str = Depends(verify_jwt_token_http)) -> PerformanceMetrics:
    """
    Returns performance metrics for the account

    Args:
        user_id (str, optional): JWT Token in header

    Returns:
        PerformanceMetrics()
    """
    main_dictionary = {}
    try:
        main_dictionary['balance'], all_orders = await asyncio.gather(*[
            get_balance(user_id),
            get_orders(**{'user_id': user_id, 'order_status': OrderStatus.CLOSED})
        ])
        
        all_dates = set(order['created_at'].date() for order in all_orders)

        tasks = [
            (asyncio.create_task(get_average_daily_return_and_total_profit_and_winrate(all_orders, all_dates)), ['daily', 'total_profit', 'winrate']),
            (asyncio.create_task(get_quant_metrics_handler(
                user_id=user_id, 
                all_orders=all_orders, 
                all_dates=all_dates,
                balance=main_dictionary['balance']
            )),)  
        ]
        
        results = await asyncio.gather(*[pair[0] for pair in tasks])
        
        for i in range(len(results)):
            current_result = results[i]
            
            if isinstance(current_result, dict):
                main_dictionary.update(current_result)
            elif isinstance(current_result, tuple):
                main_dictionary.update(dict(zip([item for item in tasks[i][1]], [item for item in current_result])))
            elif isinstance(current_result, float):
                main_dictionary.update({key: current_result for key in tasks[i][1]})
            
    except Exception:
        traceback.print_exc()
    finally:
        return PerformanceMetrics(**main_dictionary)


@portfolio.get("/quantitative", response_model=QuantitativeMetrics)
async def quantitative_metrics(
    user_id: str = Depends(verify_jwt_token_http),
    benchmark_ticker: Optional[str] = "^GSPC",
    months_ago: Optional[int] = 6,
    total_trades: Optional[int] = 100
) -> QuantitativeMetrics:
    """
    Args:
        user_id (str, optional): Depends(verify_jwt_token) Header JWT Verification.
        risk_free (Optional[float], optional): The risk free rate or benchmark rate to be comapred to.

    Returns:
        QuantitativeMetrics()
    """    
    data: dict = await get_quant_metrics_handler(**locals())
    return QuantitativeMetrics(**data)


@portfolio.get("/growth")
async def growth(
    interval: GrowthInterval,
    user_id: str = Depends(verify_jwt_token_http),
):    
    """
    Returns growth list for the tradingview chart frontend
    Args:
        interval (GrowthInterval): 
        user_id (str, optional): Defaults to Depends(verify_jwt_token_http).

    Returns:
        list
    """    
    
    existing_data = await retrieve_from_internal_cache(user_id, 'growth')
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
        
    # Getting the starting balance for the peiod
    for order in all_orders:
        quantity = order.quantity
        monetary_gain = -1 * ((order.filled_price * quantity) - (order.close_price * quantity))
        starting_period_balance += monetary_gain
        all_orders_with_gain.append({'date': order.created_at, 'gain': monetary_gain})

    for order in all_orders_with_gain:
        return_list.append(GrowthModel(**{
            'time': int(order['date'].timestamp()),
            'value': round((order['gain'] / starting_period_balance) * 100, 2)
        }))    
    
    asyncio.create_task(add_to_internal_cache(user_id, 'growth', {interval: return_list}))
    return_list.sort(key= lambda item: item.time)
    return return_list
    

@portfolio.get("/distribution", response_model=List[TickerDistribution])
async def distribution(user_id: str = Depends(verify_jwt_token_http)) -> List[TickerDistribution]:
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
    
    
@portfolio.get('/weekday-results')
async def wins_losses_weekday(user_id: str = Depends(verify_jwt_token_http)):
    constraints = locals()
    constraints.update({'order_status': OrderStatus.CLOSED})
    
    all_orders = await get_orders(**constraints)
    
    num_range = range(7)
    wins = [0 for _ in num_range]    
    losses = [0 for _ in num_range]
    
    for order in all_orders:
        close_price = order['close_price']
        price = order['price']
        
        if close_price > price:
            wins[order['created_at'].weekday()] += 1
        elif close_price < price:
            losses[order['created_at'].weekday()] += 1
    
    return JSONResponse(status_code=200, content={'wins': wins, 'losses': losses})
