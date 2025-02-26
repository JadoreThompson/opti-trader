from fastapi import FastAPI
from api.routes.order.route import order

app = FastAPI(root_path="/api")

app.include_router(order)

from sqlalchemy import insert
from db_models import Orders
from utils.db import get_db_session


async def enter_order(details: dict):
    async with get_db_session() as sess:
        await sess.execute(
            insert(Orders)
            .values(details)
        )
        await sess.commit()
    