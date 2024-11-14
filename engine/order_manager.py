from sqlalchemy import update, select
from datetime import datetime
from uuid import UUID
import json
from collections import defaultdict

# Local
from utils.db import get_db_session
from db_models import Orders
from exceptions import DoesNotExist, InvalidAction
from enums import OrderStatus


class OrderManager:
    def __init__(self) -> None:
        self._orders = defaultdict(dict)
        self.closed_orders = set()


    async def _validate_sl_tp_and_entry(
            self,
            order: dict = None,
            stop_loss_price: float = None,
            take_profit_price: float = None,
            entry_price: float = None
        ) -> bool:
        """
        Validates the TP and SL (if they're supplied)
        are greater and less than the entry price

        Args:
            order (dict): _description_

        Returns:
            bool: _description_
        """        
        # Entry Price
        if not entry_price:
            entry_price = order.get("price", None) if \
                order.get("price", None) else order.get("limit_price")
        
        # Stop Loss
        try:
            if not stop_loss_price:
                stop_loss_price = order.get("stop_loss", None)
            if stop_loss_price:
                if stop_loss_price >= entry_price:
                    raise InvalidAction("Stop less must be less than entry price")
        except AttributeError:
            pass
        
        # Take profit
        try:
            if not take_profit_price:
                take_profit_price = order.get("take_profit", None)
            if take_profit_price:
                if take_profit_price <= entry_price:
                    raise InvalidAction("Take profit must be greater than entry price")
        except AttributeError:
            pass
        
        return True


    async def add_entry(
        self,
        order_id: str, 
        entry_list: list,
        order: dict
    ) -> None:
        """Adds order to orders dictionary

        Args:
            order_id (str): _description_
            entry_price (float): _description_
            order_list (list): _description_
            stop_loss_price (float, optional): _description_. Defaults to None.
            take_profit_price (float, optional): _description_. Defaults to None.
        """        
        try:
            if await self._validate_sl_tp_and_entry(
                stop_loss_price=order['stop_loss'],
                take_profit_price=order['take_profit'],
                entry_price=order.get('filled_price', None) if order.get('filled_price', None) else order['price']
            ):
                self._orders[order_id]['entry_price'] = order.get('filled_price', None) if \
                    order.get('filled_price', None) else order.get('price', None)                    
                self._orders[order_id]['entry_list'] = entry_list
                self._orders[order_id]['ticker'] = order['ticker']
                
                # print(json.dumps(self._orders, indent=4))
        except InvalidAction:
            raise


    async def add_take_profit(
        self,
        order_id: str, 
        take_profit_list: list,
        order: dict
    ) -> None:
        """
        Adds the take profit details to the orders
        list of references

        Args:
            order_id (str)
            take_profit_list (list)
            order (dict)
        """        
        try:
            if await self._validate_sl_tp_and_entry(
                stop_loss_price=order['stop_loss'],
                take_profit_price=order['take_profit'],
                entry_price=order.get('filled_price', None) if order.get('filled_price', None) else order['price']
            ):
                self._orders[order_id]['take_profit_price'] = order.get('take_profit', None)
                self._orders[order_id]['take_profit_list'] = take_profit_list
                
                # print(json.dumps(self._orders, indent=4))
                # print('-' * 10)
        except InvalidAction:
            raise
        
    
    async def add_stop_loss(
        self,
        order_id: str,
        stop_loss_list: list,
        order: dict
    ) -> None:
        """
        Adds the stop loss details to the orders
        list of references

        Args:
            order_id (str)
            stop_loss_list (list)
            order (dict)
        """        
        try:
            if await self._validate_sl_tp_and_entry(
                stop_loss_price=order['stop_loss'],
                take_profit_price=order['take_profit'],
                entry_price=order.get('filled_price', None) if order.get('filled_price', None) else order['price']
            ):
                self._orders[order_id]['stop_loss'] = order.get('stop_loss', None)
                self._orders[order_id]['stop_loss_list'] = stop_loss_list
                
                # print(json.dumps(self._orders, indent=4))
                # print('-' * 10)
        except InvalidAction:
            raise

    def check_exists(self, order_id: str) -> bool:
        """Checks if the order_id is in the orders record
        if it isn't, return False

        Args:
            order_id (str): _description_

        Returns:
            bool: _description_
        """        
        if order_id in self._orders:
            return True
        raise DoesNotExist("Order")
    
    
    def get_order(self, order_id: str):
        """Returns the dictionary for the order 
        if it exists within the orders record

        Args:
            order_id (str): _description_

        Returns:
            _type_: _description_
        """
        try:
            if self.check_exists(order_id):
                return self._orders[order_id]
            return None
        except DoesNotExist:
            raise    


    def is_placed(self, order_id: str):
        """Returns true if OrderStats is Filled or PartiallyFilled
        else False

        Args:
            order_id (str): _description_

        Returns:
            bool: _description_
        """        
        try:
            if self.check_exists(order_id):
                order_status = self._orders[order_id]["order_list"][2]["order_status"]
                if order_status == OrderStatus.FILLED:
                    return "filled"
                
                if order_status == OrderStatus.PARTIALLY_FILLED:
                    return "partially filled"
                
                return False
        except DoesNotExist:
            raise
        

    async def _update_order_price_in_orderbook(
            self,
            order_id: str,
            new_price: float,
            field:str,
            asks: dict = None,
            bids: dict = None,
        ):
        """
        Shifts the position of the respective order
        within the orderbook for either bid or ask. If you wanted
        to reflect this change in the order object itself you'd have to
        do so manually

        Args:
            order_id (str): _description_
            new_entry_price (float): _description_
            bids (list): _description_
        
        Raises:
            DoesNotExist: If the order doesn't exist
        """        
        try:
            if self.check_exists(order_id):
                if await self._validate_sl_tp_and_entry(
                    order=self._orders[order_id]["entry_list"][2],
                    stop_loss_price=new_price if field == "stop_loss" else None,
                    take_profit_price=new_price if field == "take_profit" else None,
                    entry_price=new_price if field == "entry" else None
                ):
                    original_price = self._orders[order_id][f"{field}_price"]
                    order_list = self._orders[order_id][f"{field}_list"]
                    ticker = self._orders[order_id]['ticker']
                    
                    if bids:
                        if order_list in bids[original_price]:
                            bids[ticker][original_price].remove(order_list)
                        bids[ticker][new_price].append(order_list)
                        return True
                    
                    elif asks:
                        if order_list in asks[original_price]:
                            asks[ticker][original_price].remove(order_list)
                        asks[ticker][new_price].append(order_list)
                        return True
                    return False
        except DoesNotExist:
            raise
    
    
    async def update_entry_price_in_orderbook(
        self,
        order_id: str,
        new_entry_price: float,
        bids: dict
    ) -> None:        
        return await self._update_order_price_in_orderbook(order_id, new_entry_price, "entry", bids=bids)


    async def update_stop_loss_in_orderbook(
        self,
        order_id: str,
        new_stop_loss_price: float,
        asks: dict
    ) -> None:
        return await self._update_order_price_in_orderbook(order_id, new_stop_loss_price, "stop_loss", asks=asks)
        
        
    async def update_take_profit_in_orderbook(
        self,
        order_id: str,
        new_take_profit_price: float,
        asks: dict
    ) -> None:
        return await self._update_order_price_in_orderbook(order_id, new_take_profit_price, "take_profit", asks=asks)
            
    
    async def update_order_in_db(self, order: dict) -> None:
        """
        Updates the order's record in persistent store

        Args:
            data (dict):
        """        
        order.pop('type', None)
        if isinstance(order["created_at"], str):
            order["created_at"] = datetime.strptime(order["created_at"], "%Y-%m-%d %H:%M:%S.%f")
        
        async with get_db_session() as session:
            await session.execute(
                update(Orders)
                .where(Orders.order_id == order['order_id'])
                .values(**order)
            )

            await session.commit()
    
    
    async def _get_order_from_db(self, order_id: str | UUID) -> dict:
        """
        Retrieves an order within the DB with the order_id

        Args:
            order_id (str | UUID)

        Returns:
            dict: A dictionary representation of the order without the _sa_instance_state key
        """        
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Orders)
                    .where(Orders.order_id == order_id)
                )
                
                return {
                    key: (str(value) if isinstance(value, (UUID, datetime)) else value) 
                    for key, value in vars(result.scalar()).items()
                    if key != '_sa_instance_state'
                }
        except Exception as e:
            print("Retrieve order\n", type(e), str(e))
            print("-" * 10)
    
    
    async def update_touched_orders(self, orders: list[dict]) -> None:
        async with get_db_session() as session:
            await session.execute(
                update(Orders),
                orders
            )
            await session.commit()
        
        for order in orders:
            print(f'Order: {order['order_id']} updated')
    
    
    async def delete(
        self,
        order_id: str | UUID,
        bids: dict[float, list],
        asks: dict[float, list]
    ) -> None:
        """
        Deletes all traces of the order from the asks and bids orderbooks
        Args:
            order_id (str | UUID): _description_
        """        
        if order_id not in self._orders:
            return

        ticker = self._orders[order_id]['ticker']

        bid_price = self._orders[order_id]["entry_price"]
        entry_list = self._orders[order_id]['entry_list']
        
        stop_loss_price = self._orders.get(order_id, {}).get("stop_loss_price", None)
        stop_loss_list = self._orders.get(order_id, {}).get("stop_loss_list", None)

        take_profit_price = self._orders.get(order_id, {}).get("take_profit_price", None)
        take_profit_list = self._orders.get(order_id, {}).get("take_profit_list", None)

        
        
        # Setting as closed
        order = await self._get_order_from_db(order_id)
        order['order_status'] = OrderStatus.CLOSED
        await self.update_order_in_db(order)
        
        
        # Deleting from arrays and from _orders
        if bid_price is not None and entry_list is not None:
            if bid_price in bids and entry_list in bids[bid_price]:
                bids[ticker][bid_price].remove(entry_list)

        if stop_loss_price is not None and stop_loss_list is not None:
            if stop_loss_price in asks.get(ticker, {}) and stop_loss_list in asks[ticker][stop_loss_price]:
                asks[ticker][stop_loss_price].remove(stop_loss_list)

        if take_profit_price is not None and take_profit_list is not None:
            if take_profit_price in asks.get(ticker, {}) and take_profit_list in asks[ticker][take_profit_price]:
                asks[ticker][take_profit_price].remove(take_profit_list)

        if order_id in self._orders:
            del self._orders[order_id]

        print(f"Closed Order: {order['order_id'][-5:]} successfully!")
        print("-" * 10)
        
    
    async def declare_closed(self, order_id: str) -> None:
        """
        Adds order id to a set
        
        Args:
            order_id (str): _description_
        """        
        if order_id not in self.closed_orders:
            self.closed_orders.add(order_id)
            return  True
        return False
