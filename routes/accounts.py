from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

# Local
from config import PH
from db_models import Users
from exceptions import DuplicateError, DoesNotExist, InvalidError
from models.models import LoginUser, RegisterUser
from utils.auth import check_user_exists, create_jwt_token
from utils.db import get_db_session

# FA
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse


accounts = APIRouter(prefix="/accounts", tags=['accounts'])


@accounts.post("/register")
async def register(body: RegisterUser):
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
        try:
            body.password = PH.hash(body.password)

            async with get_db_session() as session:
                user = await session.execute(
                    insert(Users).values(**vars(body))
                    .returning(Users)
                )
                
                await session.commit()
                return JSONResponse(
                    status_code=200,
                    content={'token': create_jwt_token({'sub': str(user.scalar().user_id)})}
                )
        except IntegrityError as e:
            raise DuplicateError('User already exists')
        except Exception as e:
            print('register inner error: ', type(e), str(e))
            
    except InvalidError:
        raise InvalidError("User already exists")
    except DuplicateError:
        raise
    except Exception as e:
        print('register outer: ', type(e), str(e))
        raise


@accounts.post("/login")
async def login(body: LoginUser):
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
        user = await check_user_exists(body)
        
        return JSONResponse(
                status_code=200,
                content={'token': create_jwt_token({'sub': str(user.user_id)})}
            )
    except DoesNotExist as e:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})
    except InvalidError as e:
        print('Invalid error: ', type(e), str(e))
        raise
    except Exception as e:
        print("[LOGIN][ERROR] >> ", type(e), str(e))
        raise
