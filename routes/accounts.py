import asyncio
import logging
from datetime import (
    datetime,
    timedelta
)
from typing import (
    Any,
    Optional,
    Dict,
)

# Local
from config import PH
from db_models import (
    UserWatchlist,
    Users
)
from exceptions import (
    DuplicateError,
    DoesNotExist,
    InvalidAction
)
from models.models import (
    AuthResponse,
    LoginUser,
    ModifyAccountBody,
    RegisterBodyWithToken,
    RegisterBody,
    UserMetrics
)
from utils.auth import (
    check_user_exists,
    create_jwt_token,
    verify_jwt_token_http
)
from utils.db import (
    check_visible_user,
    get_db_session
)
from utils.tasks import (
    send_confirmation_email,
    generate_token
)

# SA
from sqlalchemy import (
    insert,
    select,
    func,
    text,
    update
)
from sqlalchemy.exc import IntegrityError

# FA
from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)
accounts = APIRouter(prefix="/accounts", tags=['accounts'])
TOKENS = {}
TOKENS_REQUEST_LIMIT = 2
TOKENS_RATE_LIMIT = timedelta(minutes=5)

@accounts.post("/register")
async def register(body: RegisterBody):
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
            token = generate_token()
            TOKENS[body.email] = [token, datetime.now(), 1]
            send_confirmation_email.delay(body.email, token)
        except IntegrityError as e:
            raise DuplicateError('User already exists')
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
            
    except (InvalidAction, DuplicateError):
        raise InvalidAction('User already exists')
    except Exception as e:
        logger.error(f'{type(e)} - {str(e)}')
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
        
        if not user.authenticated:
            raise DoesNotExist
        
        return AuthResponse(
            username=user.username, 
            token=create_jwt_token({'sub': str(user.user_id)})
        )
    except DoesNotExist as e:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})
    except InvalidAction as e:
        raise
    except Exception as e:
        logger.error(f'{type(e)} - {str(e)}')
        raise


@accounts.post("/authenticate")
async def authenticate(body: RegisterBodyWithToken):
    try:
        if body.email not in TOKENS:
            raise InvalidAction("Register for account")

        current = datetime.now()
        og_token, creation_time, count = TOKENS[body.email]
        
        if creation_time - current > TOKENS_RATE_LIMIT:
            raise InvalidAction("Token has expired")

        if og_token != body.token:
            raise InvalidAction('Invalid token')
            
        body.password = PH.hash(body.password)

        async with get_db_session() as session:
            result = await session.execute(
                insert(Users).values(
                    **{ k: v for k, v in vars(body).items() if k != 'token' },
                    authenticated=True
                )
                .returning(Users.user_id, Users.username)
            )
            
            await session.commit()
            details = result.first()
        
        del TOKENS[body.email]    
        return AuthResponse(
            username=details[1], 
            token=create_jwt_token({'sub': str(details[0])})
        )
            
    except InvalidAction:
        raise
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))
        raise HTTPException(status_code=500, detail='Internal server error')
        

@accounts.post("/modify")
async def modify(body: ModifyAccountBody, user_id: str=Depends(verify_jwt_token_http)):
    try:
        async with get_db_session() as session:
            r = await session.execute(
                update(Users)
                .where(Users.user_id == user_id)
                .values(**{k: v for k, v in vars(body).items() if v != None})
                .returning(Users.username, Users.user_id)
            )
            await session.commit()
            r = r.first()
            
        return AuthResponse(
            username=r[0], 
            token=create_jwt_token({'sub': str(r[1])})
        )
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))


@accounts.get("/metrics", response_model=UserMetrics)
async def metrics(
    user_id: str = Depends(verify_jwt_token_http),
    username: str = None,
    page: Optional[int] = 0,
) -> UserMetrics:
    PAGE_SIZE = 5
    
    data = {
        'followers': {
            'count': 0,
            'entities': [],
        },
        'following': {
            'count':0,
            'entities': [],
        }
    }
    
    if username is not None and username != 'null':
        user_id = await check_visible_user(username)            
        if not user_id:
            raise HTTPException(status_code=403)
        
    try:
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
                    .offset(page_num * PAGE_SIZE)
                    .limit(PAGE_SIZE)
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
                    ))
                    .offset(page_num * PAGE_SIZE)
                    .limit(PAGE_SIZE)
                )
                return count.scalar(), entities.all()
            
        follower_result, following_result = await asyncio.gather(
            *[
                get_follwers(user_id, page), 
                get_following(user_id, page)
            ]
        )

        data['followers']['count'] = follower_result[0]
        data['followers']['entities'] = [item[0] for item in follower_result[1]]
        data['following']['count'] = following_result[0]
        data['following']['entities'] = [item[0] for item in following_result[1]]

    except Exception as e: 
        logger.error(f'{type(e)} - {str(e)}')
    finally:
        return UserMetrics(**data)


@accounts.get("/search")
async def search(
    prefix: str,
    page: Optional[int] = 0,
    user_id: str = Depends(verify_jwt_token_http),
) -> list:
    PAGE_SIZE = 10
    try:
        async with get_db_session() as session:
            resp = await session.execute(
                select(Users.username)
                .where(Users.username.like(f"%{prefix}%"))
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            return [item[0] for item in resp]
    except Exception as e:
        logger.error(f'{type(e)} - {str(e)}')


@accounts.post("/token")
async def send_token(body: Dict[str, str]) -> None:
    try:
        current = datetime.now()
        token = generate_token()
        count = 1
        
        if body['email'] in TOKENS:
            _, creation_time, count = TOKENS[body['email']]
            
            if count == TOKENS_REQUEST_LIMIT:
                raise InvalidAction('Try again later')
            
            if current - creation_time < TOKENS_RATE_LIMIT:
                count += 1
        
        TOKENS[body['email']] = [token, current, count]
        send_confirmation_email.delay(body['email'], token)
    except InvalidAction:
        raise
    except Exception as e:
        logger.error(f'{type(e)} - {str(e)}')
