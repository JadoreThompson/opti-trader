import argon2.exceptions
from sqlalchemy import select

from config import PH
from db_models import Users
from exceptions import DoesNotExist, InvalidError
from models import User
from utils.db import get_db_session


async def check_user_exists(user: User) -> bool:
    """
    Checks if the user exists in the database and verifies their credentials.

    :param user: User object containing email and password.
    :return: True if the user exists and credentials are valid, otherwise raises an exception.

    :raises DoesNotExist: If the user does not exist in the database.
    :raises InvalidError: If the provided credentials are invalid.
    :raises Exception: For any other errors encountered during execution.
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Users).where(Users.email == user.email))
            existing_user = result.scalars().first()

            if not existing_user:
                raise DoesNotExist("User")

            if PH.verify(existing_user.password, user.password):
                return True
    except argon2.exceptions.InvalidHashError:
        raise InvalidError("Invalid credentials")
    except DoesNotExist as e:
        print("[CHECK USER][ERROR] >> ", type(e), str(e))
        raise
    except InvalidError as e:
        print("[CHECK USER][ERROR] >> ", type(e), str(e))
        raise
    except Exception as e:
        print("[CHECK USER][ERROR] >> ", type(e), str(e))
        raise
