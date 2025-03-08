import os
from dotenv import load_dotenv
from config import BASE_PATH

load_dotenv(dotenv_path=os.path.join(BASE_PATH, '.env'))

BASE_URL = os.getenv("TEST_BASE_URL")
