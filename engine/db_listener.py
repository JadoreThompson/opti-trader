import select
import psycopg2
import psycopg2.extensions
# from config import DB_URL
import time
from utils.db import delete_from_internal_cache
import json


def main(DB_URL: str):
    DB_URL = DB_URL.replace('+asyncpg', '')
    conn = psycopg2.connect(DB_URL)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    curs = conn.cursor()
    curs.execute("LISTEN order_change;")

    print('Listening for DB Updates')
    while True:
        time.sleep(1)
        try:
            # if select.select([conn],[],[],5) == ([],[],[]):
            #     print("Timeout")
            # else:
            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                delete_from_internal_cache(
                    user_id=json.loads(notify.payload)['user_id'],
                    channel=['orders', 'active_orders']
                )
        except Exception as e:
            print(type(e), str(e))
            