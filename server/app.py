from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from .exc import JWTError
from .routes import auth_route, order_route

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_route)
app.include_router(order_route)


@app.exception_handler(JWTError)
async def jwt_error_hanlder(req: Request, exc: JWTError):
    return JSONResponse(status_code=403, content={'error': str(exc)})


@app.exception_handler(ValidationError)
async def validation_error_handler(req: Request, exc: ValidationError):
    errors = exc.errors()
    error_messages = [f"{err['loc'][-1]}: {err['msg']}" for err in errors]
    return JSONResponse(status_code=422, content={'error': error_messages})
