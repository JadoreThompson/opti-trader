from fastapi.security import HTTPBearer
import jwt
import uuid

from datetime import datetime
from fastapi import Depends, HTTPException, Request, WebSocket
from typing import TypedDict
from .config import COOKIE_ALGO, COOKIE_EXP, COOKIE_KEY, COOKIE_SECRET_KEY

TOKENS: dict[uuid.UUID, dict] = {}


class JWT(TypedDict):
    sub: str  # user_id
    em: str  # email
    exp: datetime


def generate_token(payload: JWT) -> str:
    payload["exp"] = datetime.now() + COOKIE_EXP
    return jwt.encode(payload, COOKIE_SECRET_KEY, algorithm=COOKIE_ALGO)


# def verify_cookie(req: Request = None, cookies: dict = None) -> JWT:
def verify_cookie_http(req: Request) -> JWT:
    # if req is not None:
    #     cookies = req.cookies

    # if cookies is None:
    #     print("Cookie is none")
    #     raise ValueError("Cookies not provided")
    cookies = req.cookies

    token: str | None = cookies.get(COOKIE_KEY, None)

    if token is None:
        raise HTTPException(status_code=401, detail="Unauthorised")

    try:
        # p = jwt.decode(token, COOKIE_SECRET_KEY, algorithms=[COOKIE_ALGO])
        # return p
        return jwt.decode(token, COOKIE_SECRET_KEY, algorithms=[COOKIE_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    

def verify_cookie(cookies: dict[str, str]) -> JWT:
    token: str | None = cookies.get(COOKIE_KEY, None)

    if token is None:
        raise HTTPException(status_code=401, detail="Unauthorised")

    try:
        return jwt.decode(token, COOKIE_SECRET_KEY, algorithms=[COOKIE_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# def verify_cookie(cookie: str = Depends(HTTPBearer())) -> JWT:
#     if cookie is None:
#         raise HTTPException(status_code=401, detail="Unauthorised")

#     try:
#         return jwt.decode(cookie, COOKIE_SECRET_KEY, algorithms=["HS256"])
#     except jwt.ExpiredSignatureError:
#         raise HTTPException(status_code=401, detail="Token has expired")
#     except jwt.InvalidTokenError:
#         raise HTTPException(status_code=401, detail="Invalid token")
