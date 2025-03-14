import jwt
from cryptography.fernet import Fernet, InvalidToken as FernetInvalidToken
from datetime import datetime
from fastapi import HTTPException, Request
from typing import TypedDict
from .config import JWT_ALGO, JWT_EXP, JWT_ALIAS, JWT_SECRET_KEY
from .exc import InvalidJWT


ENCRYPTION_KEY: bytes = Fernet.generate_key()
CIPHER = Fernet(ENCRYPTION_KEY)


class JWT(TypedDict):
    sub: str  # user_id
    em: str  # email
    username: str
    exp: datetime


def generate_jwt_token(payload: JWT) -> str:
    """Generates a JWT string"""
    payload["exp"] = datetime.now() + JWT_EXP
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGO)


def verify_jwt_http(req: Request) -> JWT:
    """Verifies the JWT, Raises Invalid JWT upon failure"""
    token: str | None = req.cookies.get(JWT_ALIAS, None)

    if token is None:
        raise HTTPException(status_code=401, detail="Unauthorised")

    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise InvalidJWT("Token has expired")
    except jwt.InvalidTokenError:
        raise InvalidJWT("Invalid token")


def verify_jwt(cookies: dict[str, str]) -> JWT:
    """Verifies the JWT, Raises Invalid JWT upon failure"""
    token: str | None = cookies.get(JWT_ALIAS, None)
    if token is None:
        raise HTTPException(status_code=401, detail="Unauthorised")

    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise InvalidJWT("Token has expired")
    except jwt.InvalidTokenError:
        raise InvalidJWT("Invalid token")


def encrypt_jwt(payload: JWT) -> str:
    """
    Generates an encrypted JWT string which is to be used
    when authenticating a request to the orders websocket.

    Args:
        payload (JWT).

    Returns:
        str: Encrypted JWT.
    """
    jwt: str = generate_jwt_token(payload)
    return CIPHER.encrypt(jwt.encode()).decode()


def decrypt_token(token: str) -> JWT:
    """
    Decrypts the token generated by encrypted_jwt
    and returns the decoded JWT payload.

    Args:
        token (str).

    Returns:
        JWT: jwt payload.

    Raises:
        InvalidJWT: Decryption failed.
        - Also raises the excetions from verify_jwt.
    """
    try:
        decrypted_token = CIPHER.decrypt(token.encode()).decode()
        return verify_jwt({JWT_ALIAS: decrypted_token})
    except FernetInvalidToken:
        raise InvalidJWT("Invalid token")
