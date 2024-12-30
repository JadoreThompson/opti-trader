import csv

from datetime import datetime, timedelta
from io import BytesIO
import logging
from typing import List
from sqlalchemy import asc, select

# FA
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse

# Local
from enums import IntervalTypes
from db_models import MarketData
from models.models import TickerData
from utils.auth import verify_jwt_token_http
from utils.db import get_db_session


instruments = APIRouter(prefix="/instruments", tags=["instrument"])


@instruments.get("/", response_model=List[TickerData])
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
    
    if not all_data:
        m = (int(now.timestamp()) - target_time) // interval.value
        nt = (m * 60) + target_time
        return [TickerData(time=nt)]
    
    ticker_data_list: list[dict] = []
    
    for i in range(len(all_data)):
        data_point = all_data[i]
        
        time_passed = (data_point['date'] - target_time) // chosen_interval_seconds
        price = data_point['price']
        
        if time_passed >= 1:
            for _ in range(time_passed):
                new_item = {
                    'time': target_time + chosen_interval_seconds,
                    'open': ticker_data_list[-1]['close'] if ticker_data_list else price,
                    'high': price,
                    'low': price,
                    'close': price
                }
                ticker_data_list.append(new_item)
                target_time += chosen_interval_seconds            
                        
        existing = ticker_data_list[-1]
        existing['high'] = max(existing['high'], price)
        existing['low'] = min(existing['low'], price)
        existing['close'] = price
    
    time_passed = (int(now.timestamp()) - target_time) // chosen_interval_seconds
    last_price = ticker_data_list[-1]['close']
    
    for _ in range(time_passed):
        target_time += chosen_interval_seconds
        new_item = {
            'time': target_time,
            'open': last_price,
            'high': last_price,
            'low': last_price,
            'close': last_price
        }    
        ticker_data_list.append(new_item)
    
    ticker_data_list.sort(key=lambda item: item['time'])
    
    return [TickerData(**item) for item in ticker_data_list]


@instruments.get('/csv')
async def to_csv(
    ticker: str,
    interval: IntervalTypes,
    user_id: str = Depends(verify_jwt_token_http),
):
    try:
        data: list[TickerData] = await get_data(ticker=ticker, interval=interval, user_id=user_id)
        
        filename = f'csvs/{user_id}_{ticker}_{interval.value}_{datetime.now().timestamp()}.csv'
        # wr = csv.writer(file)
        
        with open(filename, 'w', newline='') as f:
            wr = csv.writer(f, delimiter=',')            
            wr.writerow(list(vars(data[0]).keys()))
            
            for item in data:
                wr.writerow(list(vars(item).values()))
            
        return FileResponse(filename)
    except Exception as e:
        logger = logging.getLogger(__name__)