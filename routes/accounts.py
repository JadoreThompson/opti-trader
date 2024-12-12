import asyncio
from typing import Optional

# Local
from config import PH
from db_models import UserWatchlist, Users
from exceptions import DuplicateError, DoesNotExist, InvalidError
from models.models import AuthResponse, LoginUser, RegisterUser, UserMetrics
from utils.auth import check_user_exists, create_jwt_token, verify_jwt_token_http
from utils.db import check_visible_user, get_db_session

# SA
from sqlalchemy import insert, select, func, text
from sqlalchemy.exc import IntegrityError

# FA
from fastapi import APIRouter, Depends, HTTPException
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
                    .returning(Users.user_id, Users.username)
                )
                
                await session.commit()
                user = user.first()
                return AuthResponse(
                    username=user[1],
                    token=create_jwt_token({'sub': str(user[0])})
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
        return AuthResponse(
            userame=user.username, 
            token=create_jwt_token({'sub': str(user.user_id)})
        )
    except DoesNotExist as e:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})
    except InvalidError as e:
        print('Invalid error: ', type(e), str(e))
        raise
    except Exception as e:
        print("[LOGIN][ERROR] >> ", type(e), str(e))
        raise


@accounts.get("/metrics", response_model=UserMetrics)
async def metrics(
    user_id: str = Depends(verify_jwt_token_http),
    username: Optional[str] = None,
    page: Optional[int] = 0,
) -> UserMetrics:
    PAGE_SIZE = 10
    
    try:
        if username:
            user_id = await check_visible_user(username)            
            if not user_id:
                raise HTTPException(status_code=403)
        
        async def get_follwers(user_id: str, page_num: int):
            async with get_db_session() as session:
                count = await session.execute(
                    select(func.count(UserWatchlist.watcher))
                    .where(UserWatchlist.master == user_id)
                )
                entities = await session.execute(
                    select(Users.username)
                    .where(Users.user_id.in_(
                        select(UserWatchlist.watcher)
                        .where(UserWatchlist.master == user_id)
                    ))
                    .offset(page * PAGE_SIZE)
                )
                return count.scalar(), entities.all()
            
        async def get_following(user_id: str, page_num: int):
            async with get_db_session() as session:
                count = await session.execute(
                    select(func.count(UserWatchlist.master))
                    .where(UserWatchlist.watcher == user_id)
                )
                entities = await session.execute(
                    select(Users.username)
                    .where(Users.user_id.in_(
                        select(UserWatchlist.master)
                        .where(UserWatchlist.watcher == user_id)
                        .offset(page * PAGE_SIZE)
                    ))
                )
                return count.scalar(), entities.all()
            
        follower_result, following_result = await asyncio.gather(
            *[
                get_follwers(user_id, page), 
                get_following(user_id, page)
            ]
        )
        
        return UserMetrics(**{
            'followers': {
                'count': follower_result[0],
                'entities': [item[0] for item in follower_result[1]]
            },
            'following': {
                'count': following_result[0],
                'entities': [item[0] for item in following_result[1]]
            }
        })
        
    except Exception as e: 
        print('account metrics: ', type(e), str(e))
