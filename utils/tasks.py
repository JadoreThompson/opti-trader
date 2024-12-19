import asyncio
import logging
import random
import string
import secrets
import time

from asgiref.sync import sync_to_async
from celery import Celery
from sqlalchemy import select
from uuid import UUID

from config import MAILER
from db_models import Users, UserWatchlist
from enums import OrderType
from utils.db import get_db_session


app = Celery(broker='redis://localhost:6379/0')
app.conf.result_backend = None
logger = logging.getLogger(__name__)
TOKENS = {}


def generate_token(length: int=6) -> str:
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length)).upper()


@app.task
def send_confirmation_email(recipient: str, token: str):
    MAILER.send_email(
        to=[recipient], 
        subject="Email Confirmation", 
        body="Here is your token {token}".format(token=token)
    )


@app.task
def send_copy_trade_email(recipients: list[str], name: str, **kwargs) -> None:    
    try:
        if not recipients:
            return
        
        subject = """
        {name} placed a {order_type}\
        """
        
        body = """
        Details:
            Ticker: {ticker}\
            Price: {price}
            Time: {time}
        """
        
        subject = subject.format(
            name=name,
            order_type=kwargs['order_type'],
        )
        
        body = body.format(
            ticker=kwargs['ticker'],
            price=kwargs['price'],
            time=kwargs['created_at']
        )
        
        MAILER.send_email(
            to=recipients, 
            subject=subject, 
            body=body
        )

        print('Sent emails')
    except Exception as e:
        logger.error('{} - {}'.format(type(e), str(e)))