import json
from datetime import datetime, timedelta
from typing import List

# Local
from utils.auth import verify_jwt_token_http
from utils.db import get_db_session
from db_models import Orders, Users
from models.models import LeaderboardItem

# SA
from sqlalchemy import select

# FA
from fastapi import APIRouter, Depends


leaderboard = APIRouter(prefix='/leaderboard', tags=['leaderboard'])
leaderboard_cache = {}


@leaderboard.get('/', response_model=List[LeaderboardItem])
async def get_leaderboard(user_id: str = Depends(verify_jwt_token_http)) -> List[LeaderboardItem]:
    """
    Args:
        user_id (str, optional): Defaults to Depends(verify_jwt_token_http).
        
    Returns:
        list[LeaderboardItem]: The top 10 people with highest earnings for the current week
    """    
    try:
        td = datetime.now()
        
        if leaderboard_cache:
            if td.weekday() != 4 or leaderboard_cache['date'] == td.date():
                return leaderboard_cache['data']
        
        async with get_db_session() as session:
            r = await session.execute(
                select(Orders)
                .where(
                    (Orders.created_at > (td - timedelta(days=td.weekday())))
                    & (Orders.realised_pnl > 0)
                )
            )
            all_orders: list[Orders] = r.scalars().all()

            users = await session.execute(
                select(Users.user_id, Users.email)
                .where(Users.user_id.in_(set([order.user_id for order in all_orders])))
            )

            leaderboard: dict = {
                str(item[0]): {
                    'earnings': 0,
                    'email': item[1]
                } for item in users.all()
            }
        
        for order in all_orders:
            leaderboard[str(order.user_id)]['earnings'] += order.realised_pnl
        
        leaderboard_items = [(pointer, item) for pointer, item in enumerate(leaderboard.items())]
        leaderboard_items.sort(key=lambda item: item[1][1]['earnings'], reverse=True)
        leaderboard_cache['date'] = td.date()
        leaderboard_cache['data'] = [
            LeaderboardItem(
                rank=i + 1, 
                username=leaderboard_items[i][1][1]['email'], 
                earnings=leaderboard_items[i][1][1]['earnings']
            ) 
            for i in range(len(leaderboard_items[:10]))
        ]
        return leaderboard_cache['data']

    except Exception as e:
        print('leaderboard >> ', type(e), str(e))
        