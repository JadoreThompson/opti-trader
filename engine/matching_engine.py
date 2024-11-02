import asyncio
import json
import sys
import threading
from collections import defaultdict
from datetime import datetime
import random
from typing import Tuple
from uuid import uuid4, UUID

from sqlalchemy import update, select

# Local
from config import REDIS_CLIENT
from db_models import Orders
from enums import OrderType, OrderStatus
from models import OrderRequest
from tests.test_config import config
from utils.db import get_db_session


class MatchingEngine:
    def __init__(self):
        """
        Bids and asks data structure
        {
            price[float]: [ [timestamp[float], quantity[float], order_data[dict] ] ]
        }
        """
        self.pubsub = REDIS_CLIENT.pubsub()

        self.bids, self.asks = config()
        self.bids_price_levels, self.asks_price_levels = self.bids.keys(), self.asks.keys()
        self.current_price: int

    # -----------------------------------------
    #                 Start of Class
    # -----------------------------------------

    async def listen_to_client_events(self) -> None:
        """
        Listens for actions from the client
        :return:
        """
        print("Matching Engine Running...")
        async with self.pubsub as pubsub:
            await pubsub.subscribe("to_order_book")

            async for message in pubsub.listen():
                if message.get('type', None) == 'message':
                    asyncio.create_task(self.handle_incoming_order(message['data']))


    async def handle_incoming_order(self, request: dict) -> None:
        """
        - Funnels into the designated computation channel
        - Once computation complete, either submitted to order book
            if the engine couldn't match it. Or it's status is updated to filled
            in the DB

        :param request[dict] -> the order details as a dictionary
        """
        data = json.loads(request)

        if data.get('order_type', '').strip():
            order_type = data['order_type']
        else:
            order_type = data.get('type')

        self.user_id = data['user_id']

        # Bid
        if order_type == OrderType.MARKET:
            if not await self.validate_tp_sl(data, 'price'):
                return

            if await self.match_buy_order(data):
                data['order_status'] = OrderStatus.FILLED

                # Set the stop loss and take-profit bid and sell orders
                await self.establish_sl_tp(data)
                await self.update_in_db(data)
                return

        # Ask
        elif order_type == OrderType.CLOSE:
            # Checking if the user specified a quantity
            data = await self.get_order_details(data)

            # Order doesn't exist
            if not data:
                await REDIS_CLIENT.publish(
                    channel=f'trades_{self.user_id}',
                    message=json.dumps({'error': "order doesn't exist"})
                )
                return

            quantity = data['close_order']['quantity'] \
                if data.get('close_order', {}).get('quantity', None) else None

            # Excessive quantity
            if quantity:
                if quantity > data['quantity']:
                    await REDIS_CLIENT.publish(
                        channel=f'trades_{self.user_id}',
                        message={'warning': "close amount can't be higher than initial quantity"}
                    )
                    return

            # Either filled or not filled
            if await self.match_close_order(data, quantity=quantity):
                data['order_status'] = OrderStatus.CLOSED
                await self.update_in_db(data)
                return

        # To Order book
        await self.add_to_order_book(data, order_type)

    async def match_buy_order(
            self,
            data: dict,
            quantity: float = None,
            price: float = None,
            count: int = 0) -> bool:
        """
        Matches the order to the stored orders
        :return:
        """
        if not quantity:
            quantity = data['quantity']
        if not price:
            price = data['price']

        # Getting a price for asks
        i = 5
        while i >= 0 and len(self.asks[price]) == 0:
            try:
                price = self.find_next_ask_level(price)
                if price:
                    break
                i += 1
            except ValueError:
                return False

        need_updates = []
        filled = False

        for order in self.asks[price]:
            if quantity - order[1] >= 0:
                quantity -= order[1]
                order[1], order[2]['order_status'] = 0, OrderStatus.FILLED
                order[2]['quantity'] = order[1]
                self.asks[price].remove(order)

            elif quantity - order[1] < 0:
                quantity = 0
                order[1] -= quantity
                order[2]['quantity'] = order[1]
                order[2]['order_status'] = OrderStatus.PARTIALLY_FILLED

            need_updates.append(order)

            if not quantity:
                filled = True
                self.current_price = price
                break

        await self.update_touched_orders(need_updates)

        count += 1
        if count < 3 and not filled:
            filled = await self.match_buy_order(data, quantity, price, count)

        if filled:
            print("Filled at: {} - {}".format(self.current_price, data['order_id']))
        else:
            print("Couldn't get filled: ", price)

        return filled

    def find_next_ask_level(self, price) -> float:
        """
        Returns the next price level containing asks
        :param price:
        :return:
        """

        try:
            price_map = {
                key: abs(price - key)
                for key in self.asks_price_levels
                if key <= price and key != price
            }

            lowest = min([val for _, val in price_map.items()])

            for key in price_map:
                q = price_map[key]
                if q == lowest:
                    return key
        except ValueError:
            # ValueError is thrown when the price_map is empty
            raise

    def find_next_bid_level(self, price) -> float:
        """
        Returns the next price level containing asks
        :param price:
        :return:
        """

        try:
            price_map = {
                key: abs(price - key)
                for key in self.bids_price_levels
                if key >= price and key != price
            }

            lowest = min([val for _, val in price_map.items()])

            for key in price_map:
                q = price_map[key]
                if q == lowest:
                    return key
        except ValueError:
            # ValueError is thrown when the price_map is empty
            raise

    async def get_order_details(self, request: dict) -> dict | None:
        """
        -   Intended use is to retrieve all attributes
            for an order when the order_id is passed in the
            message -> Specifically for Close Order Requests
        :return:
        """
        async with get_db_session() as session:
            r = await session.execute(
                select(Orders)
                .where(
                    (Orders.order_id == request['close_order']['order_id'])
                    & (Orders.user_id == request['user_id'])
                )
            )
            try:
                return vars(r.scalar())
            except TypeError:
                return None

    async def match_close_order(
            self,
            data: dict,
            quantity: float = None,
            price: float = None,
            count: int = 0) -> bool:
        """
        Matches the order to the stored orders
        :return:
        """
        if not quantity:
            quantity = data['quantity']
        if not price:
            price = data['price']

        # Getting a price for bids
        i = 5
        while i >= 0 and len(self.bids[price]) == 0:
            try:
                price = self.find_next_bid_level(price)
                if price:
                    break
                i += 1
            except ValueError:
                return False

        need_updates = []
        filled = False

        for order in self.bids[price]:
            if quantity - order[1] >= 0:
                quantity -= order[1]
                order[1], order[2]['order_status'] = 0, OrderStatus.FILLED
                order[2]['quantity'] = order[1]
                self.bids[price].remove(order)

            elif quantity - order[1] < 0:
                quantity = 0
                order[1] -= quantity
                order[2]['quantity'] = order[1]
                order[2]['order_status'] = OrderStatus.PARTIALLY_FILLED

            need_updates.append(order)

            if not quantity:
                filled = True
                self.current_price = price
                break

        await self.update_touched_orders(need_updates)

        count += 1
        if count < 3 and not filled:
            filled = await self.match_close_order(data, quantity, price, count)

        if filled:
            print("Filled at: ", price, end=f"{data['order_id']}\n")
        else:
            print("Couldn't get filled: ", price)

        return filled


    async def add_to_order_book(self, data: dict, order_type: str, created_at=None) -> None:
        """
        Adds the order into it's rightful channel either Bids or Ask
        :param created_at:
        :param data:
        :param order_type:
        :return:
        """
        if not created_at:
            created_at = datetime.now().timestamp()

        if order_type == OrderType.MARKET:
            self.bids[data['price']].append([created_at, data['quantity'], data])
            print("*" * 20)
            print("{} >> Submitted to orderbook".format(data['order_id']))
            print("*" * 20)

        elif order_type == OrderType.CLOSE:
            self.asks[data['price']].append([created_at, data['quantity'], data])
            print("^" * 20)
            print("{} >> Submitted to orderbook".format(data['order_id']))
            print("^" * 20)


    async def update_in_db(self, order: dict) -> None:
        """
        Persists changes to the order in database
        :param order:
        :return:
        """
        try:
            order = {
                k: (str(v) if isinstance(v, (UUID, datetime)) else v)
                for k, v in order.items()
                if k != '_sa_instance_state'
            }
            dt = order['created_at']
            order['created_at'] = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f")

            async with get_db_session() as session:
                await session.execute(
                    update(Orders)
                    .values(order)
                )
                await session.commit()

            order['created_at'] = dt
            await REDIS_CLIENT.publish(
                channel="trades_{}".format(order['user_id']),
                message=json.dumps(order)
            )

        except Exception as e:
            print("Update DB Order Error: ", type(e), str(e))
            pass

    async def update_touched_orders(self, orders: list) -> None:
        """
        Updates each order's record in the DB
        and sends out a publishing message to the designated pubsub channel
        for updates
        :param orders[list]
        :return:
        """
        try:
            to_be_updated = []

            for order in orders:
                order[2].pop('quantity')
                to_be_updated.append(order[2])

            async with get_db_session() as session:
                await session.execute(
                    update(Orders),
                    to_be_updated
                )
                await session.commit()

            # Sending updates to clients
            for i in range(0, len(to_be_updated), 10):
                await asyncio.gather(*[
                    REDIS_CLIENT.publish(
                        channel="trades_{}".format(order['user_id']),
                        message=json.dumps(
                            {k: (str(v) if isinstance(v, (UUID, datetime)) else v) for k, v in order.items()})
                    )
                    for order in to_be_updated[i: i + 10]
                ])

        except Exception as e:
            print("Updating touched orders: ", type(e), str(e))
            pass


    async def establish_sl_tp(self, data) -> None:
        """
        Places a bid / ask for the TP and SL of  the order
        :param data:
        :return:
        """
        try:
            if not await self.validate_tp_sl(data, 'price'):
                return

            if not data.get('stop_loss', None) and not data.get('take_profit', None):
                return

            if data.get('stop_loss', None):
                self.asks[data['stop_loss']].append([
                    data['created_at'],
                    data['quantity'],
                    data
                ])
                print("Submitted SL order to the orderbook")
                pass

            if data.get('take_profit', None):
                self.asks[data['stop_loss']].append([
                    data['created_at'],
                    data['quantity'],
                    data
                ])
                print("Submitted TP order to the orderbook")

        except Exception as e:
            print("ERROR: Establish Tp, Sl -> ", type(e), str(e))
            return


    async def validate_tp_sl(self, data: dict, price_field: str) -> bool:
        """
        Ensures TP and SL are priced above and below
        the execution price
        :param data:
        :return:
        """
        if data.get('stop_loss', None):
            if data[price_field] <= data['stop_loss']:
                await REDIS_CLIENT.publish(
                    channel=f"trades_{data['user_id']}",
                    message=json.dumps({'error': 'Stop loss must be less than execution price'})
                )
                return False

        if data.get('take_profit', None):
            if data[price_field] >= data['take_profit']:
                await REDIS_CLIENT.publish(
                    channel=f"trades_{data['user_id']}",
                    message=json.dumps({'error': 'Take profit must be greater than execution price'})
                )
                return False

        return True


# -----------------------------------------
#                          End of Class
# -----------------------------------------
def match_trades(orderbook):
    asyncio.run(orderbook.match_buy_order())


def listen(orderbook):
    asyncio.run(orderbook.listen_to_client_events())


def run():
    engine = MatchingEngine()

    threads = [
        # threading.Thread(target=match_trades, args=[orderbook], daemon=True),
        threading.Thread(target=listen, args=[engine], daemon=True),
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    run()
