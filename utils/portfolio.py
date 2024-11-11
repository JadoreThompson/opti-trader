from sqlalchemy import select
from utils.db import get_db_session
from db_models import Users


async def get_monthly_returns(orders: list, all_dates: set) -> dict[str, float]:
    """
    Returns a dictionary with the key being YYYY-MM and value being the cumulative return
    for that month

    Args:
        orders (list): _description_
        all_dates (set): _description_

    Returns:
        dict[str, float]: _description_
    """    
    all_dates = set(f"{date_item:%Y-%m}" for date_item in all_dates)
    monthly_return = {key: 0 for key in all_dates}
    
    for order in orders:        
        start_price = (order.get('filled_price', None) or order.get('price', None))
        initial_value = order['quantity'] * start_price
        price_change = ((order['close_price'] - start_price) / start_price) + 1
        monthly_return[f"{order['created_at']:%Y-%m}"] += round((initial_value * price_change) - initial_value, 2)
    return monthly_return


async def get_balance(user_id: str) -> float:
    async with get_db_session() as session:
        result = await session.execute(
            select(Users.balance).where(Users.user_id == user_id)
        )
        return result.scalar()