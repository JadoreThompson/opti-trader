## **Description**

A FIFO matching engine built in Python with order closing based on pro-rata allocation. WebSocket and HTTP endpoints are served via a Uvicorn server using FastAPI as the framework of choice.

Postgres functions power the `db_listener` module, updating an in-memory cache of user orders upon INSERT or UPDATE queries. Preventing stale data while simultaneously optimizing performance. Originally, each request triggered a database query, but with this module, queries only occur when the database changes. Thus approach improves efficiency, especially since the platform isn't designed for high-frequency trading (HFT). As a result, order-related endpoints achieve latency as low as 9 ms.

Following an event-driven architecture, Redis Pub/Sub is used to broadcast updates such as order fills, closures, partial fills, and other notifications that active users need to receive.

## Prerequisites

- Python 3.12

## **Installation**

```powershell
git clone <https://github.com/JadoreThompson/opti-trader.git>

pip install -r requirements.txt

python app.py

```

## **Contact**

If you're interested in collaborating or have any opportunities, feel free to contact me at [jadorethompson6@gmail.com](mailto:jadorethompson6@gmail.com) or connect with me on [LinkedIn](https://www.linkedin.com/in/jadore-t-49379a295/).
