from datetime import datetime, timedelta
from typing import List
from sqlalchemy import asc, select

# FA
from fastapi import APIRouter, Depends

# Local
from enums import IntervalTypes
from db_models import MarketData
from models.models import TickerData
from utils.auth import verify_jwt_token_http
from utils.db import get_db_session


instrument = APIRouter(prefix="/instrument", tags=["instrument"])


@instrument.get("/", response_model=List[TickerData])
async def get_data(
    ticker: str,
    interval: IntervalTypes,
    user_id: str = Depends(verify_jwt_token_http),
):
    now = datetime.now()
    d = now - timedelta(weeks=2)
    target_time = int(datetime(year=d.year, month=d.month, day=d.day).timestamp())
    chosen_interval_seconds = interval.to_seconds()
    
    async with get_db_session() as session:
        result = await session.execute(
            select(MarketData)
            .where((MarketData.date > target_time) & (MarketData.ticker == ticker))
            .order_by(asc(MarketData.date))
        )
        all_data = [vars(item) for item in result.scalars().all()]
        
    candle_data_list = []
    
    for i in range(len(all_data)):
        dp = all_data[i]
        
        time_passed = (dp['date'] - target_time) // chosen_interval_seconds
        price = dp['price']
        
        if time_passed >= 1:
            for _ in range(time_passed):
                new_item = {
                    'time': target_time + chosen_interval_seconds,
                    'open': all_data[i - 1]['price'] if i > 0 else price,
                    'high': price,
                    'low': price,
                    'close': price
                }
                candle_data_list.append(new_item)
                target_time += chosen_interval_seconds            
                        
        existing = candle_data_list[-1]
        existing['high'] = max(existing['high'], price)
        existing['low'] = min(existing['low'], price)
        existing['close'] = price
        
    # for dp in all_data:        
    #     time_passed = (dp['date'] - target_time) // chosen_interval_seconds
    #     price = dp['price']
        
    #     if time_passed >= 1:
    #         for _ in range(time_passed):
    #             new_item = {
    #                 'time': target_time + chosen_interval_seconds,
    #                 'open': price,
    #                 'high': price,
    #                 'low': price,
    #                 'close': price
    #             }
    #             candle_data_list.append(new_item)
    #             target_time += chosen_interval_seconds            
                        
    #     existing = candle_data_list[-1]
    #     existing['high'] = max(existing['high'], price)
    #     existing['low'] = min(existing['low'], price)
    #     existing['close'] = price
    
    time_passed = (int(now.timestamp()) - target_time) // chosen_interval_seconds
    last_price = candle_data_list[-1]['close']
    
    for _ in range(time_passed):
        target_time += chosen_interval_seconds
        new_item = {
            'time': target_time,
            'open': last_price,
            'high': last_price,
            'low': last_price,
            'close': last_price
        }    
        candle_data_list.append(new_item)
    
    return [TickerData(**item) for item in candle_data_list]
