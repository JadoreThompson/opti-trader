from typing import Callable, Type, TypeVar
from fastapi import Request
from fastapi.responses import JSONResponse

from config import COOKIE_ALIAS
from .exc import JWTError
from .typing import JWTPayload
from .utils import decode_jwt_token, validate_jwt_payload


T = TypeVar("T")


async def verify_jwt(req: Request) -> JWTPayload:
    """Verify the JWT token from the request cookies and validate it.

    Args:
        req (Request)

    Raises:
        JWTError: If the JWT token is missing, expired, or invalid.

    Returns:
        JWTPayload: The decoded JWT payload if valid.
    """
    token = req.cookies.get(COOKIE_ALIAS)

    if not token:
        raise JWTError("Authentication token is missing")

    payload = decode_jwt_token(token)
    return await validate_jwt_payload(payload)


def convert_csv(
    param_name: str, target_type: Type[T], default: list[T] | None = None
) -> Callable[[Request], list[T]]:
    """Converts a query parameter from csv format to list[T]

    Args:
        param_name (str)
        target_type (Type[T]): Type for each item in list.
        default (list[T] | None, optional): Default value if param isn't passed.
            Defaults to None.
    """

    def wrapper(req: Request) -> list[T]:
        value = req.query_params.get(param_name)
        if not value:
            return default

        try:
            return [target_type(item.strip()) for item in value.strip().split(",")]
        except (ValueError, TypeError):
            raise JSONResponse(
                status_code=400, content={"error": f"Invalid {param_name}"}
            )

    return wrapper
