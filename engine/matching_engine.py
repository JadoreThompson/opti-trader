import asyncio
import json
from collections import defaultdict
from datetime import datetime
import random
from typing import Tuple
from uuid import uuid4, UUID
import redis

from sqlalchemy import update, select

# Local
# from config import REDIS_CLIENT
from db_models import Orders
from enums import OrderType, OrderStatus, _InternalOrderType
from exceptions import DoesNotExist, InvalidAction
from models.matching_engine_models import OrderRequest
from tests.test_config import config
from utils.db import get_db_session
from engine.order_manager import OrderManager


# Redis
REDIS_CONN_POOL = redis.asyncio.connection.ConnectionPool(max_connections=20)
REDIS_CLIENT = redis.asyncio.client.Redis(connection_pool=REDIS_CONN_POOL)


class MatchingEngine:
    def __init__(self):
        """
        Bids and asks data structure
        {
            price[float]: [ [timestamp[float], quantity[float], order_data[dict] ] ]
        }
        """
        self.redis = REDIS_CLIENT
        self.order_manager = OrderManager()

        self.bids, self.asks = config()
        
        self.bids_price_levels = self.bids.keys()
        self.asks_price_levels = self.asks.keys()
        
        self.current_price: int
        
    
    async def listen_to_client_events(self):
        """
            Listens to messages from the to_order_book channel
            and relays to the handler
        """        
        print("Matching Engine Listening...")
        async with self.redis.pubsub() as pubsub:
            await pubsub.subscribe("to_order_book")
            async for message in pubsub.listen():
                await asyncio.sleep(0.1)
                if message.get("type", None) == "message":
                    asyncio.create_task(self.handle_incoming_message(message["data"]))


    async def handle_incoming_message(self, data: dict):
        """
        Handles the routing of the request into the right
        functions

        Args:
            data (dict): A dictionary representation of the request
        """        
        await asyncio.sleep(0.1)
        data = json.loads(data)
        
        action_type = data["type"]
        channel = f"trades_{data['user_id']}"
        
        if action_type == OrderType.MARKET:
            await self.handle_market_order(data, channel)
            
        elif action_type == OrderType.LIMIT:
            await self.handle_limit_order(channel, data)
            
        elif action_type == OrderType.CLOSE:
            await self.handle_sell_order(data, channel)
            
        elif action_type == OrderType.ENTRY_PRICE_CHANGE:
            await self.handle_entry_price_change(
                data,
                data['order_id'],
                data['new_take_profit_price'],
                channel
            )
            
        elif action_type == OrderType.TAKE_PROFIT_CHANGE:
            await self.handle_take_profit_change(
                data,
                data['order_id'],
                data['new_take_profit_price'],
                channel
            )
        
        elif action_type == OrderType.STOP_LOSS_CHANGE:
            await self.handle_stop_loss_change(
                data,
                data['order_id'],
                data['new_stop_loss_price'],
                channel
            )
        
        print("Finished all")
                
                
    async def publish_update_to_client(self, channel: str, message: str) -> None:
        """
        Publishes message to channel using REDIS

        Args:
            channel (str):
            message (str): 
        """        
        try:
            await self.redis.publish(channel=channel, message=message)
        except Exception as e:
            print("Publish update to client:", type(e), end=f"\n{str(e)}\n")
            pass
    
    
    async def place_tp_sl(self, data: dict) -> None:
        try:
            # TP
            if data.get('take_profit', None):
                take_profit_data = data.copy()
                take_profit_data['internal_order_type'] = _InternalOrderType.TAKE_PROFIT_ORDER
                take_profit_list = [take_profit_data["created_at"], take_profit_data["quantity"], take_profit_data]
                
                self.asks[take_profit_data['ticker']][take_profit_data["take_profit"]].append(take_profit_list)
                
                await self.order_manager.add_take_profit(
                    take_profit_data['order_id'],
                    take_profit_list,
                    take_profit_data
                )
            
            # Stop Loss
            if data.get('stop_loss', None):
                stop_loss_data = data.copy()
                stop_loss_data['internal_order_type'] = _InternalOrderType.STOP_LOSS_ORDER
                stop_loss_list = [stop_loss_data["created_at"], stop_loss_data["quantity"], stop_loss_data]
                
                self.asks[stop_loss_data['ticker']][stop_loss_data["stop_loss"]].append(stop_loss_list)
                
                await self.order_manager.add_stop_loss(
                    stop_loss_data['order_id'],
                    stop_loss_list,
                    stop_loss_data
                )
            
            print(f"Placed TP and SL for Order: {data['order_id'][:5]}")
        except Exception as e:
            print("Error placing TP SL\n", type(e), str(e))            
            print('-' * 10)
            
    
    async def handle_market_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a buy order

        Args:
            data (dict)
        """    
        result: tuple = await self.match_buy_order(data, ticker=data['ticker'])
        print("Handle buy order result\n", result)
        print('-' * 10)
        
        # Not filled
        if result[0] == 0:
            await self.redis.publish(
                channel=channel,
                message=json.dumps({
                    "status": "error",
                    "message": "Insufficient asks to fulfill bid order",
                    "order_id": data["order_id"]
                })    
            )
            return

        # Relaying message to user
        status_message = {
            1: {
                "channel": channel,
                "message": json.dumps({
                    "status": "update", 
                    "message": "Order partially filled",
                    "order_id": data["order_id"]
                })
            },
            
            2: {
                "channel": channel,
                "message": json.dumps({
                    "status": "success",
                    "message": "Order successfully placed",
                    "order_id": data["order_id"]
                })
            }
        }.get(result[0])
        
        await self.publish_update_to_client(**status_message)

        # Order was successfully filled
        if result[0] == 2:
            try:
                data["filled_price"] = result[1]
                data['order_status'] = OrderStatus.FILLED
                
                await self.place_tp_sl(data)
                await self.order_manager.add_entry( # Adding to reference list
                    data["order_id"],
                    [data["created_at"], data["quantity"], data],
                    data
                )                
                
                await self.order_manager.update_order_in_db(data)

            except InvalidAction as e:
                await self.publish_update_to_client(channel=channel, message=json.dumps({
                    'status': 'error',
                    'message': str(e),
                    'order_id': data['order_id']
                }))
                
            finally:
                return
        
        
        # Order was partially filled so we add to orderbook
        data['order_status'] = OrderStatus.PARTIALLY_FILLED
        await self.order_manager.update_order_in_db(data)
        await self.add_order_to_orderbook(data, data["quantity"], bids=self.bids)
    
    
    async def find_ask_price_level(
        self,
        bid_price: float,
        ticker: str,
        max_attempts: int = 5,
    ):
        """
        Finds the closest ask price level with active orders
        to the bid_price

        Args:
            bid_price (float): 
            max_attempts (int, optional): Defaults to 5.

        Returns:
            Price: The ask price with the lowest distance
            None: No asks to match the bid price execution
        """
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Finding the price with the lowest distance from the bid_price
                price_map = {
                    key: abs(bid_price - key)
                    for key in list(self.asks_price_levels[ticker])
                    if key >= bid_price
                    and self.asks[ticker][key]
                }
                
                lowest_distance = min(val for _, val in price_map.items())
                
                for price, distance in price_map.items():
                    if distance == lowest_distance:
                        return price
                
                attempt += 1
            except ValueError:
                return None
        return None
    
    
    async def match_buy_order(
        self, 
        ticker: str,
        data: dict = None,
        bid_price: float = None,
        quantity: float =  None,
        attempts: float = 0
    ) -> tuple:
        """
        Recursively calls itself if the quantity
        for the order is partially filled ( > 0)
        . Once filled it'll return 2
        

        Args:
            data (dict)

        Returns:
            (0,): Order couldn't be filled due to insufficient asks
            (1,): Order was partially filled
            (2, ask_price): Order was successfully filled
        """
        bid_price = data["price"] if not bid_price else bid_price
        quantity = data["quantity"] if not quantity else quantity
        
        
        ask_price = await self.find_ask_price_level(bid_price, ticker=ticker)
        if not ask_price:
            return (0, )
        
        
        touched_orders = []
        
        # Fulfilling the order
        for order in self.asks[ticker][ask_price]:
            # Adding the order to the batch that needs to be updated
            order_copy = order[2]
            order_copy.pop('internal_order_type', None)
            touched_orders.append(order_copy)            
            
            # Checking if the order can be filled
            internal_order_type = order[2].get('internal_order_type', None)
            
            if quantity - order[1] >= 0:
                quantity -= order[1]
                
                if internal_order_type == _InternalOrderType.STOP_LOSS_ORDER or\
                    internal_order_type == _InternalOrderType.TAKE_PROFIT_ORDER:
                    order[2]['order_status'] = OrderStatus.CLOSED
                    order[2]['closed_at'] = datetime.now()
                    order[2]['close_price'] = ask_price
                else:
                    order[2]['filled_price'] = ask_price
                    order[2]['order_status'] = OrderStatus.FILLED
                
                self.asks[ticker][ask_price].remove(order)
            
            elif quantity - order[1] < 0:
                order[1] -= quantity
                
                if internal_order_type == _InternalOrderType.STOP_LOSS_ORDER or\
                    internal_order_type == _InternalOrderType.TAKE_PROFIT_ORDER:
                    order[2]['order_status'] = OrderStatus.PARTIALLY_CLOSED
                else:
                    order[2]['order_status'] = OrderStatus.PARTIALLY_FILLED
                
                # Updating all touched orders
                await self.order_manager.update_touched_orders(touched_orders)
                
                return (2, ask_price)
        
        # Trying again 3 times
        if attempts < 2:
            attempts += 1
            return await self.match_buy_order(
                bid_price=bid_price, 
                quantity=quantity, 
                attempts=attempts,
                ticker=ticker,
            )

        # Order was partially filled
        # Updating all touched orders
        await self.order_manager.update_touched_orders(touched_orders)
        return (1, )
    
    
    async def handle_limit_order(self, channel: str, order: dict) -> None:
        """
        Places a bid order on the desired price
        for the limit order along with placing the TP and SL of the order

        Args:
            order (dict)
        """        
        
        try:
            order_list = [order['created_at'], order['quantity'], order]
            self.bids[order['ticker']][order['limit_price']].append(order_list)
            
            await self.place_tp_sl(order)
            await self.order_manager.add_entry(
                order['order_id'],
                order_list,
                order
            )
            
            await self.publish_update_to_client(
                channel=channel,
                message=json.dumps({
                    'status': 'success',
                    'message': 'Limit order created successfully',
                    'order_id': order['order_id']
                })
            )
        
        except (InvalidAction, DoesNotExist) as e:
            await self.publish_update_to_client(channel=channel, message=json.dumps({
                    'status': 'error',
                    'message': str(e),
                    'order_id': order['order_id']
                }))
        
    
    async def handle_sell_order(self, data: dict, channel: str) -> None:
        """
        Handles the creation and submission to orderbook
        for a sell order

        Args:
            data (dict)
        """    
        result: tuple = await self.match_sell_order(data)
        print("Tried to match sell order, result: ", result)
        print("\n")
        
        # Not closed
        if result[0] == 0:
            await self.redis.publish(
                channel=channel,
                message=json.dumps({
                    "status": "error",
                    "message": "Insufficient asks to fulfill sell order",
                    "order_id": data["order_id"]
                })    
            )
            return

        # Relaying message to user
        status_message = {
            1: {
                "channel": channel,
                "message": json.dumps({
                    "status": "update", 
                    "message": "Order partially closed",
                    "order_id": data["order_id"]
                })
            },
            
            2: {
                "channel": channel,
                "message": json.dumps({
                    "status": "success",
                    "message": "Order successfully closed",
                    "order_id": data["order_id"]
                })
            }
        }.get(result[0])
        
        await self.publish_update_to_client(**status_message)


        # Order was successfully closed
        if result[0] == 2:
            try:
                data['close_price'] = result[1]
                data['closed_at'] = datetime.now()
                data['order_status'] = OrderStatus.CLOSED
                
                data.pop('market_price', None)
                
                await self.order_manager.update_order_in_db(data)
                await self.order_manager.delete(
                    data['order_id'],
                    self.bids, 
                    self.asks
                )    
                
            except InvalidAction as e:
                print("Error in handling buy order\n", str(e))
                print('-' * 10)
                await self.publish_update_to_client(channel=channel, message=str(e))
            finally:
                return
        
        
        # Order was partially closed so we add to orderbook
        data['order_status'] = OrderStatus.PARTIALLY_CLOSED
        await self.order_manager.update_order_in_db(data)
        await self.add_order_to_orderbook(data, data["quantity"], asks=self.asks)

    
    async def find_bid_price_level(
      self,
      ask_price: float,
      max_attempts: int = 5  
    ):
        """
        Finds the closest bid price level with active orders
        to the ask_price

        Args:
            bid_price (float): 
            max_attempts (int, optional): Defaults to 5.

        Returns:
            Price: The ask price with the lowest distance
            None: No asks to match the bid price execution
        """
        attempt = 0
        while attempt < max_attempts:
            try:
                # Finding the price with the lowest distance from the ask_price
                price_map = {
                    key: abs(ask_price - key)
                    for key in self.bids_price_levels
                    if key >= ask_price
                    and self.bids[key]
                }
                
                lowest_distance = min(val for _, val in price_map.items())
                
                for price, distance in price_map.items():
                    if distance == lowest_distance:
                        return price
                
                attempt += 1
            except ValueError:
                return None
        return None
        
    
    async def match_sell_order(
        self,
        data: dict = None,
        ask_price: float = None, # Current ask price level
        quantity: float =  None,
        attempts: float = 0
    ) -> tuple:
        """
        Recursively calls itself if the quantity
        for the order is partially filled ( > 0). 
        Once filled it'll return 2
        

        Args:
            data (dict)

        Returns:
            (0,): Order couldn't be filled due to insufficient asks
            (1,): Order was partially filled
            (2, ask_price): Order was successfully filled
        """        
        ask_price = ask_price if ask_price else data["market_price"]
        quantity = quantity if quantity else data["quantity"]
        
        bid_price = await self.find_bid_price_level(ask_price)
        if not bid_price:
            return (0, )
        
        
        # Fulfilling the order
        for order in self.bids[bid_price]:
            if quantity <= 0: 
                break
            
            if quantity - order[1] >= 0:
                quantity -= order[1]
                self.bids[bid_price].remove(order) # Order is now satisfied
            
            elif quantity - order[1] < 0:
                order[1] -= quantity
                
                print("-" * 10)
                print(f"Order: {data["order_id"][:5]} filled at {bid_price}")
                print("-" * 10)
                
                return (2, bid_price)
        
        # Trying again 3 times
        if attempts < 2:
            attempts += 1
            return self.match_sell_order(
                ask_price=ask_price, quantity=quantity, attempts=attempts)

        # Order was partially filled
        return (1, )
    
    
    async def handle_entry_price_change(
        self,
        order: dict,
        order_id: str,
        new_entry_price: float,
        channel: str
    ) -> None:
        """
        Movess the bid order from the original price level to the new price level

        Args:
            order_id (str): _description_
            new_take_profit_price (float): _description_
        """
        try:
            if await self.order_manager.update_entry_price_in_orderbook(order_id, new_entry_price, self.asks):
                order['limit_price'] = order['price'] = new_entry_price
                order.pop('new_entry_profit_price', None)
                
                await self.order_manager.update_order_in_db(order)
                
                await self.publish_update_to_client(channel, message=json.dumps({
                    'status': 'success',
                    'message': 'Entry price changed successfully',
                    'order_id': order_id
                }))
                return
            
            await self.publish_update_to_client(
                channel=channel,
                message=json.dumps({
                    'status': 'error',
                    'message': "Couldn't update entry price",
                    'order_id': order_id
                })
            )
            
        except (InvalidAction, DoesNotExist) as e:
            await self.publish_update_to_client(channel=channel, message=json.dumps({
                'status': 'error',
                'message': str(e),
                'order_id': order_id
            }))
    
    
    async def handle_take_profit_change(
        self,
        order: dict,
        order_id: str,
        new_take_profit_price: float,
        channel: str
    ) -> None:
        """
        Movess the ask order from the original price level to the new price level

        Args:
            order_id (str): _description_
            new_take_profit_price (float): _description_
        """
        try:
            if await self.order_manager.update_take_profit_in_orderbook(order_id, new_take_profit_price, self.asks):
                order['take_profit'] = new_take_profit_price
                order.pop('new_take_profit_price', None)
                
                await self.order_manager.update_order_in_db(order)
                
                await self.publish_update_to_client(channel, message=json.dumps({
                    'status': 'success',
                    'message': 'Take Profit changed successfully',
                    'order_id': order_id
                }))
                return
            
            await self.publish_update_to_client(
                channel=channel,
                message=json.dumps({
                    'status': 'error',
                    'message': "Couldn't update take profit",
                    'order_id': order_id
                })
            )
            
        except (InvalidAction, DoesNotExist) as e:
            await self.publish_update_to_client(channel=channel, message=json.dumps({
                'status': 'error',
                'message': str(e),
                'order_id': order_id
            }))
            

    async def handle_stop_loss_change(
        self,
        order: dict,
        order_id: str,
        new_stop_loss_price: float,
        channel: str
    ) -> None:
        try:
            if await self.order_manager.update_stop_loss_in_orderbook(order_id, new_stop_loss_price, self.asks):
                order['stop_loss'] = new_stop_loss_price
                order.pop('new_stop_loss_price', None)
                
                await self.order_manager.update_order_in_db(order)
                
                await self.publish_update_to_client(channel, message=json.dumps({
                    'status': 'success',
                    'message': 'Stop loss changed successfully',
                    'order_id': order_id
                }))
                
                return
            
            await self.publish_update_to_client(
                channel=channel,
                message=json.dumps({
                    'status': 'error',
                    'message': "Couldn't update stop loss",
                    'order_id': order_id
                })
            )
        
        except (InvalidAction, DoesNotExist) as e:
            await self.publish_update_to_client(channel=channel, message=json.dumps({
                'status': 'error',
                'message': str(e),
                'order_id': order_id
            }))


    async def add_order_to_orderbook(
        self,
        data: dict,
        quantity: float,
        bids: list = None,
        asks: list= None
    ) -> None:
        """
        Adds order to the price level for either the bids
        or asks

        Args:
            data (dict): 
            quantity (float): 
            bids (list, optional): Defaults to None.
            asks (list, optional): Defaults to None.
        """        
        book = 'bids' if bids else 'asks'
        target_book = asks if asks else bids
        
        target_book[data["price"]].append([
            data["created_at"], quantity, data
        ])
        
        await self.publish_update_to_client(
            f"trades_{data["user_id"]}", 
            json.dumps({
                "status": "update",
                "message": "Order added to orderbook"
            })
        )
        print("\n")
        print("-" * 10)
        print(f"Successfully added {data['order_id'][-5:]} to {book}")
        print("-" * 10)
        print("\n")
    

def run():
    engine = MatchingEngine()
    asyncio.run(engine.listen_to_client_events())
