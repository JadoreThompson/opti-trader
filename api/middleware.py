import uuid
from fastapi import HTTPException, Request
from config import COOKIE_KEY

TOKENS: dict[uuid.UUID, dict]= {}

def generate_token(payload: dict) -> uuid.UUID:
    global TOKENS
    
    key = uuid.uuid4()
    TOKENS[key] = payload
    return key

def verify_token(req: Request) -> dict:
    global TOKENS
    
    try:
        return TOKENS[req.cookies[COOKIE_KEY]]
    except KeyError:
        raise HTTPException(status_code=401, detail='Unauthorized')