# Local
from sqlalchemy import insert

from config import PH
from db_models import Users
from exceptions import DuplicateError, DoesNotExist, InvalidError
from models import User

# FA
from fastapi import APIRouter, HTTPException

from utils.accounts import check_user_exists
from utils.db import get_db_session


accounts = APIRouter(prefix="/accounts", tags=['accounts'])


@accounts.post("/register")
async def register(body: User):
    """
    Registers a new user account.
    If the user already exists, raises DuplicateError.

    Args:
        body (User): The user information for registration.
    Raises:
        HTTPException: If registration is successful, raises with status code 200.
        DuplicateError: If the user already exists.
        Exception: For unexpected errors.
    """
    try:
        result = await check_user_exists(body)
        if result:
            raise DuplicateError("An account already exists")

    except DoesNotExist:
        password = PH.hash(body.password)
        async with get_db_session() as session:
            await session.execute(insert(Users).values(email=body.email, password=password))
            await session.commit()
            raise HTTPException(status_code=200)

    except InvalidError:
        raise InvalidError("User already exists")
    except Exception as e:
        print("[REGISTER][ERROR] >> ", type(e), str(e))
        raise


@accounts.post("/login")
async def login(body: User):
    """
    Authenticates a user account.
    Checks if the user exists and provides access if valid.

    Args:
        body (User): The user information for login.
    Raises:
        HTTPException: If login is successful, raises with status code 200.
        DoesNotExist: If the user does not exist.
        Exception: For unexpected errors.
    """
    try:
        if await check_user_exists(body):
            raise HTTPException(status_code=200)
        raise DoesNotExist("User")
    except DoesNotExist as e:
        print("[LOGIN][ERROR] >> ", type(e), str(e))
        raise
    except Exception as e:
        print("[LOGIN][ERROR] >> ", type(e), str(e))
        raise
