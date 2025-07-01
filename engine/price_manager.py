class PriceManager:
    def __init__(self, orderbook: OrderBook):
        self.orderbook = orderbook
        self._current_price = 0.0

    async def update_price(self, price: float):
        self._current_price = price
        
    async def _publish_price(
        self,
    ) -> None:
        """
        Periodically posts price to the pubsub channel and writes to the db
        """
        await self._fetch_instrument_id()
        await REDIS_CLIENT.set(f"{self.instrument}.price", self._cur_price)
        await REDIS_CLIENT.publish(f"{self.instrument}.live", self._cur_price)

        randnum = lambda: round(random.random() * 100, 2)  # Here during dev

        while True:
            self._cur_price = randnum()  # Here during dev
            self._prev_price_queue.append(self._cur_price)  # Here during dev

            try:
                price = self._prev_price_queue.popleft()
            except IndexError:
                price = self._cur_price = randnum()  # Here during dev

            await REDIS_CLIENT.set(f"{self.instrument}.price", price)
            await REDIS_CLIENT.publish(f"{self.instrument}.live", price)

            if self._instrument_id:
                async with self.lock:
                    async with get_db_session() as sess:
                        await sess.execute(
                            insert(MarketData).values(
                                instrument=self.instrument,
                                instrument_id=self._instrument_id,
                                time=datetime.now().timestamp(),
                                price=price,
                            )
                        )
                        await sess.commit()

            asyncio.create_task(self._update_upl(price))
            await asyncio.sleep(self._price_delay)

    async def _update_upl(self, price: float) -> None:
        """
        Updates upl for all filled and partially filled orders
        within the tracker

        Args:
            price (float)
        """
        if self._tracker:
            tracker_copy = self._tracker.copy()
            for _, pos in tracker_copy.items():
                if pos.order.payload["status"] in (
                    OrderStatus.FILLED,
                    OrderStatus.PARTIALLY_CLOSED,
                ):
                    calculate_upl(pos.order, price, self)
                    self._pusher.append(pos.order.payload, speed="fast")

                    if pos.order.payload["status"] == OrderStatus.CLOSED:
                        self._pusher.append(
                            {
                                "user_id": pos.order.payload["user_id"],
                                "amount": pos.order.payload["realised_pnl"],
                            },
                            "balance",
                        )
