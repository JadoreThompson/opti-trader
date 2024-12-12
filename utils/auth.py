from datetime import timedelta, datetime

# Security
from uuid import UUID
import argon2.exceptions
from jwt import InvalidTokenError, encode, decode
from passlib.context import CryptContext

#SA
from sqlalchemy import select

# FA
from fastapi import Request, Depends
from fastapi.security import OAuth2PasswordBearer

# Local
from config import PH
from db_models import Users
from exceptions import DoesNotExist, InvalidError, InvalidAction
from models.models import _User
from utils.db import get_db_session


SECRET_KEY = "secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY_MINUTES = 10 ** 5

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def create_jwt_token(data: dict) -> str:
    """
    Returns JWT Token
    Args:
        data (dict)

    Returns:
        token[str]: JWT Token
    """    
    data['exp'] = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRY_MINUTES)
    return encode(data, SECRET_KEY, algorithm=ALGORITHM)
    

def verify_jwt_token_http(token: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload['sub']
    except InvalidTokenError:
        raise InvalidAction("User unauthorised")
    
    except Exception as e:
        print('verify jwt http: ', type(e), str(e))


def verify_jwt_token_ws(token: str) -> str:
    try:
        payload = decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload['sub']
    except InvalidTokenError:
        raise InvalidAction("User unauthorised")
    

async def check_user_exists(user: _User) -> Users:
    """
    Checks if the user exists in the database and verifies their credentials.

    Args:
        user: User object containing email and password.
    
    Return:
        - DB Users instance
    
    Raises:
        DoesNotExist: If the user does not exist in the database.
        InvalidError: Password doesn't match.
        Exception: For any other errors encountered during execution.
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(select(Users).where(Users.email == user.email))
            existing_user: Users = result.scalars().first()

            if not existing_user:
                raise DoesNotExist("User")

            if PH.verify(existing_user.password, user.password):
                return existing_user
    except argon2.exceptions.InvalidHashError:
        raise InvalidError("Invalid credentials")
    
    except (DoesNotExist, InvalidError) as e:
        raise
        
    except Exception as e:
        print("Error in check user exists: ", type(e), str(e))
