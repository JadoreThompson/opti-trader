import os
from datetime import timedelta
from dotenv import load_dotenv
from config import BASE_PATH

load_dotenv(dotenv_path=os.path.join(BASE_PATH, ".env"))


JWT_ALIAS = os.getenv("JWT_ALIAS")
JWT_ALGO = os.getenv("JWT_ALGO")
JWT_EXP = timedelta(days=1000)
JWT_SECRET_KEY = os.getenv("JWT_SECRET")
