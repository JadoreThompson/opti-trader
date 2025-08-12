import os
from urllib.parse import quote

from dotenv import load_dotenv


BASE_PATH = os.path.dirname(__file__)


load_dotenv(os.path.join(BASE_PATH, ".env"))


DB_USER_CREDS = f"{os.getenv("DB_USERNAME")}:{quote(os.getenv("DB_PASSWORD"))}"
DB_HOST_CREDS = f"{os.getenv("DB_HOST")}:{quote(os.getenv("DB_PORT"))}"
DB_NAME = os.getenv("DB_NAME")
DB_URL = f"postgresql+psycopg2://{DB_USER_CREDS}@{DB_HOST_CREDS}/{DB_NAME}"
print(DB_URL)
