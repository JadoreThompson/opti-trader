# Local
from exceptions import DoesNotExist, InvalidAction
from enums import OrderStatus


class OrderManager:
    def __init__(self) -> None:
        self._orders = {}


    def _validate_sl_tp_entry(
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


    def add_order(
            self,
            order_id: str, 
            entry_price: float,
            order_list: list,
            stop_loss_price: float = None,
            take_profit_price: float = None,
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
            if self._validate_sl_tp_entry(
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                entry_price=entry_price
            ):
                self._orders[order_id] = {
                    "entry_price": entry_price,
                    "stop_loss_price": stop_loss_price,
                    "take_profit_price": take_profit_price,
                    "order_list": order_list
                }
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
        

    def _update_order_price(
            self,
            order_id: str,
            new_price: float,
            field:str,
            asks: dict = None,
            bids: dict = None,
        ):
        """Updates the entry price for the order
        if the order isn't filled or partially filled.
        If the order is parially or filled, it'll raise an InvalidAction
        error.

        Args:
            order_id (str): _description_
            new_entry_price (float): _description_
            bids (list): _description_
        
        Raises:
            DoesNotExist: If the order doesn't exist
        """        
        try:
            if self.check_exists(order_id):
                if self._validate_sl_tp_entry(
                        order=self._orders[order_id]["order_list"][2],
                        stop_loss_price=new_price if field == "stop_loss" else None,
                        take_profit_price=new_price if field == "take_profit" else None,
                        entry_price=new_price if field == "entry" else None
                    ):
                    original_price = self._orders[order_id][f"{field}_price"]
                    order_list = self._orders[order_id]["order_list"]
                    
                    if bids:
                        bids[original_price].remove(order_list)
                        bids[new_price].append(order_list)
                    elif asks:
                        asks[original_price].remove(order_list)
                        asks[new_price].append(order_list)
                
                print(f"Updated {field} price successfully!")
        except DoesNotExist:
            raise
    
    
    def update_entry_price(
        self,
        order_id: str,
        new_entry_price: float,
        bids: dict
    ) -> None:
        is_placed = self.is_placed(order_id)
        if isinstance(is_placed, bool):
            self._update_order_price(order_id, new_entry_price, "entry", bids=bids)
            return
        raise InvalidAction(f"Can't edit entry price on {is_placed} order")


    def update_stop_loss(
        self,
        order_id: str,
        new_stop_loss_price: float,
        asks: dict
    ) -> None:
        self._update_order_price(order_id, new_stop_loss_price, "stop_loss", asks=asks)
        
        
    def update_take_profit(
        self,
        order_id: str,
        new_take_profit_price: float,
        asks: dict
    ) -> None:
        self._update_order_price(order_id, new_take_profit_price, "take_profit", asks=asks)
        

    def remove_order(self, order_id: str, bids: dict, asks: dict) -> None:
        """
        Removes the Take Profit, Stop loss and Execution Order from
        the bid and asks

        Args:
            order_id (str): _description_
            bids (list): _description_
            asks (list): _description_
        """        
        try:
            if self.check_exists(order_id):
                order = self._orders[order_id]
                
                if order.get("entry_price", None) in bids:
                    bids[order["entry_price"]].remove(order["order_list"])
                if order.get("stop_loss_price", None) in bids:
                    bids[order["stop_loss_price"]].remove(order["order_list"])
                if order.get("take_profit_price", None) in asks:
                    asks[order["take_profit_price"]].remove(order["order_list"])
                
                # Discarding all trace of order
                del self._orders[order_id]
        except DoesNotExist:
            raise
            
        
manager = OrderManager()
        