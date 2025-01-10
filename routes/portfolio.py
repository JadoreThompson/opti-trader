import asyncio
from datetime import (
    datetime, 
    timedelta
)
import json
import logging
from typing import (
    Dict,
    List, 
    Optional, 
    Annotated
)
from uuid import UUID

# SA
import redis
import redis.connection
from sqlalchemy import (
    select,
    insert
)

# Local
from config import (
    REDIS_HOST,
    SYNC_REDIS_CONN_POOL,
)
from enums import (
    MarketType,
    OrderStatus,
    GrowthInterval
)
from exceptions import InvalidAction
from db_models import (
    UserWatchlist,
    Users,
    DBOrder
)
from models.models import (
    CopyTradeRequest,
    FuturesContractRead,
    GrowthModel,
    PerformanceMetrics,
    QuantitativeMetricsBody,
    QuantitativeMetrics,
    SpotOrderRead,
    AssetAllocation,
    Username,
    WinsLosses,
)
from utils.arithemtic import (
    get_quantitative_metrics,
    beta,
    get_benchmark_returns,
    get_ghpr,
    risk_of_ruin,
    sharpe,
    std,
    treynor
)

from utils.auth import verify_jwt_token_http
from utils.db import (
    check_visible_user,
    get_active_orders,
    get_orders,
    get_db_session,    
)
from utils.portfolio import (
    get_balance,
    get_monthly_returns
)

# FA
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse


def calculate_cumulative_return(starting_balance: float, orders: List[float]) -> List[float]:
    balance = starting_balance
    return [
        {
            f'{order['created_at']:%Y-%m}': round(
                order['realised_pnl'] / (balance := balance - order['realised_pnl']) * 100
            , 2)
        }
        for order in orders
    ]
    

def calcualte_risk_per_trade(starting_balane: float, orders: List[dict]) -> List[float]:
    """
    Returns the percentage risk per trade as a float list
    Args:
        starting_balane (float): _description_
        orders (List[dict]): _description_

    Returns:
        List: _description_
    """    
    balance = starting_balane
    return [
        (margin := order['quantity'] * order['filled_price']) / (balance := balance - margin)
        for order in orders
    ]


async def calculate_quant_metrics(user_id: str) -> dict:
    async with get_db_session() as session:
        r = await session.execute(
            select(DBOrder)
            .where(
                (DBOrder.user_id == user_id)
                & (DBOrder.order_status == OrderStatus.CLOSED)
            )
        )
        all_orders: List[DBOrder] = r.scalars().all()
    
        r = await session.execute(
            select(Users.balance)
            .where(Users.user_id == user_id)
        )
        balance = r.first()[0]
    
    # Calculations
    if not all_orders:
        return {}
        
    date_returns: List[Dict[str, float]] = calculate_cumulative_return(
        balance, 
        [vars(order) for order in all_orders]
    )
    
    benchmark_returns = get_benchmark_returns()
    
    returns = []
    for item in date_returns:
        returns.append(list(item.values())[0])
    
    data = {
        'balance': balance,
        'std': std(returns),
        'sharpe': sharpe(returns,),
        'beta': beta(returns, benchmark_returns),
        'winrate': sum(1 for order in all_orders if order.realised_pnl > 0) / len(all_orders)
    }
    
    data['treynor'] = treynor(
        sum(returns) / len(returns),
        sum(benchmark_returns) / len(benchmark_returns),
        data['beta']
    )
    pct_risk_per = calcualte_risk_per_trade(balance, [vars(order) for order in all_orders])
    data['risk_of_ruin'] = risk_of_ruin(
        balance, 
        sum(pct_risk_per) / len(pct_risk_per),
        100,
    )
    
    return data


# Initialisation
# ^^^^^^^^^^^^^^
logger = logging.getLogger(__name__)
portfolio = APIRouter(prefix='/portfolio', tags=['portfolio'])
REDIS_CLIENT = redis.Redis(
    host=REDIS_HOST, 
    connection_pool=SYNC_REDIS_CONN_POOL
)

@portfolio.get('/orders',)
async def orders(
    user_id: str = Depends(verify_jwt_token_http),
    username: Optional[str] = None,
    order_status: Annotated[List[OrderStatus], Query()] = None,
    market_type: Annotated[List[MarketType], Query()] = None,
    ticker: Annotated[List[str], Query()] = None
):      
    if username is not None and username != 'null':
        user_id = await check_visible_user(username)
        if not user_id:
            raise HTTPException(status_code=403)
    
    if not order_status:
        order_status = []
    if not market_type:
        market_type = []
    if not ticker:
        ticker = []
        
    prim_cache_key = 'orders'
    sec_cache_key = \
        f"{''.join(order_status) + ''.join(market_type) + ''.join(ticker)}".strip() \
        or 'all'
    
    existing_data = REDIS_CLIENT.get(user_id)
    if existing_data:
        existing_data = json.loads(existing_data)
        if prim_cache_key in existing_data:
            if sec_cache_key in existing_data[prim_cache_key]:
                return [
                    FuturesContractRead(**item) 
                    for item in existing_data[prim_cache_key][sec_cache_key]
                ]
    else:
        existing_data = {}
    
    existing_data.setdefault(prim_cache_key, {})
    all_orders = []
    
    # Retrieving
    try:
        query = \
            select(DBOrder)\
            .where(DBOrder.user_id == user_id)
        
        if order_status:
            query = query.where(DBOrder.order_status.in_(order_status))
        if market_type:
            query = query.where(DBOrder.market_type.in_(market_type))
        if ticker:
            query = query.where(DBOrder.ticker.in_(ticker))
        
        async with get_db_session() as s:
            r = await s.execute(query)
            all_orders = [vars(order) for order in r.scalars().all()]
        
        existing_data[prim_cache_key][sec_cache_key] = all_orders
        REDIS_CLIENT.set(user_id, json.dumps(existing_data))
        
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))
    finally:
        return [FuturesContractRead(**order) for order in all_orders]


@portfolio.get("/performance", response_model=PerformanceMetrics)
async def performance(
    market_type: MarketType,
    interval: Optional[GrowthInterval] = GrowthInterval.MONTH,
    user_id: str = Depends(verify_jwt_token_http),
    username: Optional[str] = None,
) -> PerformanceMetrics:
    """
    Returns performance metrics for the account

    Args:
        market_type (MarketType)
        user_id (str): JWT Token in header
        username (Optional[str])
    Returns:
        JSON (PerformanceMetrics)
    """ 
    if username is not None and username != 'null':
        user_id = await check_visible_user(username)
        if not user_id:
            raise HTTPException(status_code=403)

    existing_data = REDIS_CLIENT.get(user_id)
    
    if existing_data:
        existing_data = json.loads(existing_data)
        if 'performance' in existing_data:
            return PerformanceMetrics(**existing_data['performance'])
    else:
        existing_data = {}

    existing_data['performance'] = {}
    task = asyncio.create_task(calculate_quant_metrics(user_id))
    
    
    query = \
        select(DBOrder)\
        .where(
            (DBOrder.user_id == user_id)
            & (DBOrder.order_status == OrderStatus.CLOSED)
            & (DBOrder.market_type == market_type)
        ) \
        .limit(1000)
    
    today = datetime.now()
    options = {
        GrowthInterval.DAY: DBOrder.created_at >= today,
        GrowthInterval.WEEK: DBOrder.created_at >= today - timedelta(days=today.weekday()),
        GrowthInterval.MONTH: DBOrder.created_at >= today.replace(day=1),
        GrowthInterval.YEAR: DBOrder.created_at >= datetime(year=today.year, month=1, day=1),
    }
    
    clause = options.get(interval, None)
    if clause:
        query = query.where(clause)
    
    try:
        async with get_db_session() as session:
            r = await session.execute(query)
            
            all_orders = [vars(order) for order in r.scalars().all()]
            
            r = await session.execute(
                select(Users.balance)
                .where(Users.user_id == user_id)
            )
            
            existing_data['performance']['balance'] = r.first()[0]
        
        
        existing_data['performance']['total_profit'] = sum(order['realised_pnl'] for order in all_orders)
        all_dates = set(order['created_at'].date() for order in all_orders)
        temp = {
            item: 0
            for item in all_dates
        }
        
        for item in all_orders:
            temp[item['created_at'].date()] += item['realised_pnl']
        existing_data['performance']['daily'] = sum(v for _, v in temp.items())
        
        # Cache the data
        await task
        existing_data['performance'].update(task.result())
        REDIS_CLIENT.set(user_id, json.dumps(existing_data))
    except Exception as e:
        print(f'{type(e)} - {str(e)}')
        logger.error(f'{type(e)} - {str(e)}')
    finally:
        return PerformanceMetrics(**existing_data['performance'])


# @portfolio.get("/quantitative",)
# async def quantitative_metrics(
#     username: Optional[str] = None,
#     user_id: str = Depends(verify_jwt_token_http),
# ):
#     """
#     Args:
#         user_id (str, optional): Depends(verify_jwt_token) Header JWT Verification.
#         risk_free (Optional[float], optional): The risk free rate or benchmark rate to be comapred to.

#     Returns:
#         QuantitativeMetrics()
#     """ 
#     key_ = 'quantitative'
    
#     if username is not None:
#         user_id = await check_visible_user(username)
#         if not user_id:
#             raise HTTPException(status_code=403)
    
#     existing_data = REDIS_CLIENT.get(user_id)
    
#     if existing_data:
#         existing_data = json.loads(existing_data)
#         if key_ in existing_data:
#             return QuantitativeMetrics(**existing_data[key_])
#     else:
#         existing_data = {}
    
#     return QuantitativeMetrics(**await calculate_quant_metrics(user_id))


@portfolio.get("/growth", response_model=List[GrowthModel])
async def growth(
    interval: GrowthInterval,
    market_type: MarketType,
    username: Optional[str] = None,
    user_id: str = Depends(verify_jwt_token_http),
) -> List[GrowthModel]:    
    """
    Returns JSON for building portfolio growth chart in frontend
    
    Args:
        - user_id (JWTToken)
        - interval (GrowthInterval)
        - username (Optional[str]): Defaults to None
    Returns:
        - JSON (List[GrowthInterval])
    """ 
    if username is not None and username != 'null':
        user_id = await check_visible_user(username)
        if not user_id:
            raise HTTPException(status_code=403)
    
    key_ = 'growth_data'
    inner_key_ = interval.value + market_type.value
    existing_data = REDIS_CLIENT.get(user_id)
    
    if existing_data:
        existing_data = json.loads(existing_data)
        if key_ in existing_data:
            if interval in existing_data[key_]:
                if inner_key_ in existing_data[key_]:
                    return existing_data[key_][inner_key_]
    else:
        existing_data = {}
    
    existing_data.setdefault(key_, {})
    final_list = []
    
    try:
        
        # Constructing query to get orders
        today = datetime.now()
        today = datetime(
            day=today.day, 
            month=today.month, 
            year=today.year
        )
        
        query = \
            select(DBOrder)\
            .where(
                (DBOrder.user_id == user_id) 
                & (DBOrder.order_status == OrderStatus.CLOSED)
                & (DBOrder.market_type == market_type)
            )
        
        options = {
            GrowthInterval.DAY: DBOrder.created_at >= today,
            GrowthInterval.WEEK: DBOrder.created_at >= today - timedelta(days=today.weekday()),
            GrowthInterval.MONTH: DBOrder.created_at >= today.replace(day=1),
            GrowthInterval.YEAR: DBOrder.created_at >= datetime(year=today.year, month=1, day=1),
        }
        
        clause = options.get(interval, None)
        if clause is not None:
            query = query.where(clause)
        
        async with get_db_session() as session:
            r = await session.execute(query)
            all_orders: List[DBOrder] = r.scalars().all()
            
            r = await session.execute(
                select(Users.balance)
                .where(Users.user_id == user_id)
            )
            current_balance = r.first()[0]
            
        # Performing calculations
        starting_balance = current_balance
        for order in all_orders:
            starting_balance += -1 * order.realised_pnl

        final_list = \
            list(
                sorted(
                    [
                        {
                            'time': int(order.created_at.timestamp()),
                            'value': round((order.realised_pnl / starting_balance) * 100, 2),
                        }
                        for order in all_orders
                    ],
                    key=lambda item: item['time']
                )
            )
            
        existing_data[key_].update({
            inner_key_: final_list
        })
        REDIS_CLIENT.set(user_id, json.dumps(existing_data))    
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))
    finally:
        return [
            GrowthModel(**item) 
            for item in final_list 
            if final_list.count(item) == 1
        ]
    

@portfolio.get("/allocation", response_model=List[Optional[AssetAllocation]])
async def distribution(
    market_type: MarketType,
    user_id: str = Depends(verify_jwt_token_http),
    username: Optional[str] = None,
) -> List[Optional[AssetAllocation]]:
    """

    Args:
        user_id (str, optional): _description_. Defaults to Depends(verify_jwt_token_http).
        username (Optional[str], optional): _description_. Defaults to None.

    Raises:
        HTTPException: Profile isn't visible

    Returns:
        List[Optional[TickerDistribution]]: _description_
    """    
    if username:
        user_id = await check_visible_user(username)
        if not user_id:
            raise HTTPException(status_code=403)
    
    key_ = 'allocation'
    existing_data = REDIS_CLIENT.get(user_id)
    
    if existing_data:
        existing_data = json.loads(existing_data)
        if existing_data.get(key_, {}).get(market_type, None):
            return [
                AssetAllocation(name=k, value=v) 
                for k, v in existing_data[key_][market_type].items()
            ]
    else:
        existing_data = {}
        
    existing_data.setdefault(key_, {})
    existing_data[key_][market_type] = {}

    try:
        async with get_db_session() as session:
            r = await session.execute(
                select(DBOrder)
                .where(
                    (DBOrder.user_id == user_id)
                    & (DBOrder.order_status != OrderStatus.CLOSED)
                    & (DBOrder.order_status != OrderStatus.NOT_FILLED)
                    # & (DBOrder.order_status != OrderStatus.EXPIRED)
                    & (DBOrder.market_type == market_type)
                )
                .limit(1000)
            )
            
            all_orders: List[DBOrder] = r.scalars().all()
        
        if not all_orders:
            raise ValueError("No orders")

        ticker_map = {
            ticker: 0
            for ticker in 
            set(order.ticker for order in all_orders)
        }
        
        for order in all_orders:
            price = order.filled_price or order.limit_price or order.price
            ticker_map[order.ticker] += price * order.quantity
        
        total = sum(ticker_map.values())
        ticker_map = {
            k: v / total
            for k, v in ticker_map.items()
        }
        
        existing_data[key_][market_type]  = ticker_map
        REDIS_CLIENT.set(user_id, json.dumps(existing_data))    
        
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))
    finally:
        return [
            AssetAllocation(name=k, value=v) 
            for k, v in existing_data[key_][market_type].items()
        ]

    
@portfolio.get('/weekday-results')
async def weekday_results(
    user_id: str = Depends(verify_jwt_token_http),
    username: Optional[str] = None,
):
    """
    Returns data to weekday gains chart in frontend

    Args:
        user_id (str): Defaults to Depends(verify_jwt_token_http).
        username (Optional[str],): _description_. Defaults to None.

    Raises:
        HTTPException: account with username=(username) isn't visible

    Returns:
        JSON (WinsLosses)
    """    
    if username is not None and username != 'null':
        user_id = await check_visible_user(username)
        if not user_id:
            raise HTTPException(status_code=403)
        
    key_ = 'weekday_results'
    existing_data = REDIS_CLIENT.get(user_id)

    if existing_data:
        existing_data = json.loads(existing_data)
        if key_ in existing_data:
            return WinsLosses(**existing_data[key_])
    else:
        existing_data = {}
    existing_data[key_] = {}
    
    try:
        num_range = range(7)
        wins = [0 for _ in num_range]    
        losses = [0 for _ in num_range]
        
        async with get_db_session() as session:
            r = await session.execute(
                select(DBOrder)
                .where(
                    (DBOrder.user_id == user_id)
                    & (DBOrder.order_status == OrderStatus.CLOSED)
                )
            )
            all_orders: List[DBOrder] = r.scalars().all()
    
        for order in all_orders:
            if order.realised_pnl < 0:
                losses[order.created_at.weekday()] += 1
            elif order.realised_pnl > 0:
                wins[order.created_at.weekday()] += 1
        
        existing_data[key_] = {'wins': wins, 'losses': losses}        
        REDIS_CLIENT.set(user_id, json.dumps(existing_data))
        
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))
    finally:
        return WinsLosses(**existing_data[key_])


@portfolio.post("/copy")
async def copy_trades(
    body: CopyTradeRequest, 
    user_id: str = Depends(verify_jwt_token_http)
):
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
            
            master = r.first()

            if not master:
                raise HTTPException(status_code=403)
            
            payload = body.model_dump()
            payload.update({
                'master': master[0],
                'watcher': user_id,
            })
            
            record = UserWatchlist(**payload)
            session.add(record)
            
            await session.commit()            
    except HTTPException:
        raise
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))
        