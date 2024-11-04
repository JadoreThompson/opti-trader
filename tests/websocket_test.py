import asyncio
import json
import random
import threading
import time
from uuid import uuid4

import websockets

# Local
from enums import OrderType
from models import OrderRequest, MarketOrder


async def main(user_id, order_id=None):
    BASE_URL = "ws://127.0.0.1:8000"

    async with websockets.connect(BASE_URL + '/stream/trade') as socket:
        await socket.send(json.dumps({'user_id': user_id}))
        m = await socket.recv()
        # while True:
            # message = {
            #     'type': 'market_order',
            #     'market_order': {
            #         'ticker': 'BTC/USDT',
            #         'quantity': random.randint(100, 100000),
            #         'price': 100
            #     }
            # }

        order_ids = []
        for _ in range(2):
            message = {
                'type': 'market_order',
                'market_order': {
                    'ticker': 'BTC/USDT',
                    'quantity': random.randint(100, 100000),
                    'stop_loss': {
                        'price': 100
                    },
                    'take_profit': {
                        'price': 500
                    }
                }
            }

            await socket.send(json.dumps(message))
            m = await socket.recv()
            m = json.loads(m)        
            print("Received message in websocket test!")
            print(m)
            print("-" * 10)
        
            order_ids.append(m['order_id'])
            await asyncio.sleep(2)
            
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
                
        
        for order_id in order_ids:
            print("-" * 10)
            print(order_id)
            print("-" * 10)
            for _ in range(5):
                message = {
                    # 'type': 'stop_loss_change',
                    # 'stop_loss_change': {
                    'type': 'take_profit_change',
                    'take_profit_change': {
                        'order_id': order_id,
                        'price': 1000
                    }
                }
            
                await socket.send(json.dumps(message))
                
                m = await socket.recv()
                # m = json.loads(m)
                
                print("-" * 10)
                print("Received message in websocket test!")
                print(m)
                print("-" * 10)
                
                await asyncio.sleep(2)



def run(user_id):
    asyncio.run(main(user_id))


def run2():
    print(1)
    time.sleep(0.5)
    message = {
        'type': 'close_order',
        'close_order': {
            'order_id': str(uuid4()),
            'ticker': 'BTC/USDT',
            'quantity': random.randint(100, 100000),
        }
    }
    asyncio.run(main(message))


def start():
    user_id = input("User id: ")
    # order_id = input("Order Id: ")
    asyncio.run(main(user_id,))
    

if __name__ == "__main__":
    start()
