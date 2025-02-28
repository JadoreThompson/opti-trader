from fastapi import APIRouter, Depends
from sqlalchemy import select


from db_models import Users
from utils.db import get_db_session
from .model import Profile
from ...middleware import JWT, verify_cookie

account = APIRouter(prefix="/account", tags=["account"])

@account.get('/')
async def get_account(jwt: JWT = Depends(verify_cookie)) -> Profile:
    async with get_db_session() as sess:
        res = await sess.execute(
            select(Users)
            .where(Users.user_id == jwt['sub'])
        )
        user = res.scalar()
    
    return Profile(**vars(user))