from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.auth.route import auth
from api.routes.account.route import account
from api.routes.order.route import order

app = FastAPI(root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
    allow_credentials=True,
)

app.include_router(auth)
app.include_router(account)
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
    