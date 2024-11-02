import asyncio
import json
import threading
import ccxt

# Local
from config import REDIS_CLIENT, TICKERS


async def watch_price(ticker, exch):
    """Publishes ticker price to channel, triggers event"""
    price = 0

    while True:
        try:
            new_price = float(exch.fetch_mark_price(ticker).get('info', {}).get('indexPrice', None))
            if new_price > price:
                price = new_price
                await REDIS_CLIENT.publish(channel='prices', message=json.dumps({ticker: round(price, 2)}))
                print(f"{ticker}", price)
        except Exception as e:
            print(type(e), str(e))
            continue


async def price_overseer():
    exch = ccxt.binance()
    exch.load_markets()

    tasks = [watch_price(ticker, exch) for ticker in TICKERS]
    await asyncio.gather(*tasks)


def run():
    asyncio.run(price_overseer())


if __name__ == "__main__":
    run()
