from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.auth.route import auth
from api.routes.account.route import account
from api.routes.order.route import order

app = FastAPI(root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # "*", 
        "http://192.168.1.145",
        "http://192.168.1.145:5173",
    ],
    allow_headers=["*"],
    allow_methods=["*"],
    allow_credentials=True,
)

app.include_router(auth)
app.include_router(account)
app.include_router(order)
