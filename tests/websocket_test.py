import asyncio
import json
import random
import threading
import time
from uuid import uuid4

import websockets

# Local
from enums import OrderType
from models.matching_engine_models import OrderRequest, MarketOrder


async def main(user_id=None, order_id=None):
    BASE_URL = "ws://127.0.0.1:8000"
    TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0ZWRjYjA5Zi0zMWRlLTRlYzMtODc0NS1lYjJkMGQzZTBjYjkiLCJleHAiOjE3Mzc1MTYyODJ9.nk6CL0vreDoaAQLdpNKi2AQVQMrUMkLzjilv9pYJP-o'
    
    async with websockets.connect(BASE_URL + '/stream/trade') as socket:
        await socket.send(json.dumps({'token': TOKEN}))
        m = await socket.recv()
        
        message = {
            'type': 'close_order',
            'close_order': {
                'ticker': 'APPL',
                'quantity': 1000
            }
        }
        
        await socket.send(json.dumps(message))
        
        # while True:
        #     message = {
        #         'type': 'market_order',
        #         'market_order': {
        #             'ticker': 'BTC/USDT',
        #             'quantity': random.randint(100, 100000),
        #             'price': 100
        #         }
        #     }

        # order_ids = []
        
        # for _ in range(2):
        #     message = {
        #         'type': 'limit_order',
        #         'limit_order': {
        #             'ticker': 'SOL/USDT',
        #             'quantity': random.randint(0, 1),
        #             'limit_price': 130,
        #             'stop_loss': {
        #                 'price': 100
        #             },
        #             'take_profit': {
        #                 'price': 500
        #             }
        #         }
        #     }

        #     await socket.send(json.dumps(message))
        #     m = await socket.recv()
        #     m = json.loads(m)        
        #     print("Received message in websocket test!")
        #     print(m)
        #     print("-" * 10)
        #     await asyncio.sleep(3)
        
        #     order_ids.append(m['order_id'])
        #     await asyncio.sleep(2)
            
        #     await asyncio.sleep(1)

        #     print("-" * 10)
        #     print("Received message in websocket test!")
        #     print(m)
        #     print("-" * 10)

        #     await asyncio.sleep(2)
        # else:
    
        # for _ in range(500):
        #     message = {
        #         'type': 'close_order',
        #         'close_order': {
        #             'order_id': order_id
        #         }
        #     }
            
        #     await socket.send(json.dumps(message))
        #     await asyncio.sleep(2)
                
        
        # for order_id in order_ids:
        #     print("-" * 10)
        #     print(order_id)
        #     print("-" * 10)
        #     for _ in range(5):
        #         message = {
        #             # 'type': 'stop_loss_change',
        #             # 'stop_loss_change': {
        #             'type': 'take_profit_change',
        #             'take_profit_change': {
        #                 'order_id': order_id,
        #                 'price': 1000
        #             }
        #         }
            
        #         await socket.send(json.dumps(message))
                
        #         m = await socket.recv()
        #         # m = json.loads(m)
                
        #         print("-" * 10)
        #         print("Received message in websocket test!")
        #         print(m)
        #         print("-" * 10)
                
        #         await asyncio.sleep(2)


def start():
    # order_id = input("Order Id: ")
    asyncio.run(main())
    

if __name__ == "__main__":
    start()
