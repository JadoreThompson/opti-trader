from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from .exc import JWTError
from .routes import auth_route, order_route

app = FastAPI()


app.include_router(auth_route)
app.include_router(order_route)


@app.exception_handler(JWTError)
async def jwt_error_hanlder(req: Request, exc: JWTError):
    raise HTTPException(status_code=403, detail=str(exc))


@app.exception_handler(ValidationError)
async def validation_error_handler(req: Request, exc: ValidationError):
    errors = exc.errors()
    error_messages = [f"{err['loc'][-1]}: {err['msg']}" for err in errors]
    raise HTTPException(status_code=422, detail=error_messages)