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


async def main():
    BASE_URL = "ws://127.0.0.1:8000"

    async with websockets.connect(BASE_URL + '/stream/trade') as socket:
        await socket.send(json.dumps({'user_id': "a7e1d03f-ee09-40e6-9cbc-7ba78ff1bdcb"}))
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

        for _ in range(5):
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

            print("-" * 10)
            print("Received message!")
            print(m)
            print("-" * 10)

            await asyncio.sleep(2)



def run():
    asyncio.run(main())


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
    threads = [
        threading.Thread(target=run, daemon=True),
        # threading.Thread(target=run2, daemon=True),
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    start()
