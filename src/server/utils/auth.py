import jwt

from datetime import datetime, timedelta
from fastapi import Response
from dataclasses import asdict
from sqlalchemy import select

from config import COOKIE_ALIAS, PRODUCTION, JWT_SECRET_KEY, JWT_ALGO, JWT_EXPIRY_MINS
from db_models import Users
from utils.db import get_db_session
from ..typing import JWTPayload
from ..exc import JWTError


def generate_jwt(**kwargs) -> str:
    """Generates a JWT token

    Args:
        kwargs: kwargs for JWT object

    Returns:
        str: JWT token
    """
    if kwargs.get("exp") is None:
        kwargs["exp"] = datetime.now() + timedelta(minutes=JWT_EXPIRY_MINS)

    kwargs["sub"] = str(kwargs["sub"])
    payload = JWTPayload(**kwargs)
    return jwt.encode(asdict(payload), JWT_SECRET_KEY, algorithm=JWT_ALGO)


def decode_jwt(token: str) -> JWTPayload:
    try:
        return JWTPayload(**jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGO]))
    except jwt.ExpiredSignatureError:
        raise JWTError("Token has expired")
    except jwt.InvalidTokenError:
        raise JWTError("Invalid token")


async def validate_jwt_payload(payload: JWTPayload) -> JWTPayload:
    """Validate a JWT token and return the decoded payload.

    Args:
        payload (JWTPayload): The decoded JWT payload.

    Raises:
        JWTError: If the user referenced in the payload does not exist.

    Returns:
        JWTPayload: The validated JWT payload.
    """
    print(1)
    async with get_db_session() as sess:
        print(2, sess.bind.url)
        res = await sess.execute(select(Users).where(Users.user_id == payload.sub))
        # print(res)
        user = res.scalar_one_or_none()

    print(3)
    if not user:
        raise JWTError("Invalid user")

    return payload


def set_cookie(user_id: int, rsp: Response | None = None) -> Response:
    token = generate_jwt(sub=user_id)
    if rsp is None:
        rsp = Response()
    rsp.set_cookie(COOKIE_ALIAS, token, httponly=True, secure=PRODUCTION)
    return rsp


def remove_cookie(rsp: Response | None = None) -> None:
    if rsp is None:
        rsp = Response()

    rsp.delete_cookie(COOKIE_ALIAS, httponly=True, secure=PRODUCTION)
    return rsp
