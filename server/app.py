from fastapi import FastAPI, HTTPException, Request
from .exc import JWTError

app = FastAPI()

@app.exception_handler(JWTError)
async def jwt_error_hanlder(req: Request, exc: JWTError):
    raise HTTPException(status_code=401, detail=str(exc))