# **Overview**
This is a FIFO Matching Engine built in Python, offering a websocket for live price and order updates along with HTTP endpoints built with FastAPI. This application leverages a Redis based lock system built by myself to combat the polling and synchronous nature of the built-in multiprocessing Queue https://github.com/JadoreThompson/r-mutex.

# **Pre-requisites**
If you're interested on working on this codebase you'll need prior knowledge of asynchronous programming, FastAPI and database management.

# **Requirements**
Version numbers can be found in https://github.com/JadoreThompson/opti-trader/blob/main/requirements.txt
- Python 3.12
- Postgres
- Redis

# **Installation**
Here's the structure for your .env file
```
# Argon
TIME_COST=1
MEMORY_COST=1_024_000
PARALLELISM=1

# Cookie
COOKIE_ALIAS=my-cookie-key
COOKIE_ALGO=HS256
COOKIE_SECRET=secret

# DB
DB_NAME=<db_name>
DB_HOST=<db_host>
DB_PORT=<db_port>
DB_USER=<db_user>
DB_PASSWORD=<db_password>

# Redis
ORDER_UPDATE_CHANNEL=order.updates
BALANCE_UPDATE_CHANNEL=balance.updates
ORDER_LOCK_PREFIX=orderlock

# Tests
TEST_BASE_URL=http://localhost:8000/api
```

An alembic.ini boilerplate can be found here - https://alembic.sqlalchemy.org/en/latest/tutorial.html.

Now it's time to install

```
## If you don't have Redis installed, download Docker and run this command
docker run --name <container_name e.g. myredis> -d -p 6379:6379 redis

git clone https://github.com/JadoreThompson/opti-trader.git

python -m venv venv

pip install -r requirements.txt

### Create you alembic.ini file

### Setup your .env file

### Perform migrations
alembic upgrade head

### Run the application
python __main__.py
```


# **Documentation**
### **Engine Payloads**
There are 3 payload types that can be sent to the engine which are declared as EnginePayloadCategory:
```
NEW = 0
MODIFY = 1
CLOSE = 2
```

- **NEW**: A new order to be match and placed into the orderbook
- **MODIFY**: A request to modify the limit price, take profit and stop loss price of an order of which all are optional

#### **Sending a payload**
To send a payload you must follow this schema. The value of content is always a dictionary containing the data for the request. For example a new order request is a dictionary representation of a record in the orders table.
```json
{
	"category": EnginePayloadCategory,
	"content": dict
}
```

### **System Flow**
The big 3 classes are the Futures Engine, Pusher and Orderbook.

The Futures Engine initialises the pusher then commences with initialise orderbook objects, passing the pusher into each one upon verifying that the pusher is running. Each Order Book object is responsible for maintaining the bids and asks levels along with a tracker and methods for interacting with the structures. The tracker is dictionary where the key is a string representation of the UUID it holds in the DB and the value is a Position object. The Position object, much like the tracker, serves the purpose of allowing quick lookup and locating of orders with 3 attributes being the order, take profit and stop loss which all of them are of type Order which is a simple container class that holds the dictionary representation of the db record such that any changes to it are reflected globally through each leg of the Position

### **System Flow**

The three core components of the system are:

1. **Futures Engine**
2. **Pusher**
3. **Order Book**

The Futures Engine is responsible for initializing the Pusher and ensuring it is running before creating Order Book instances. Each Order Book manages bid and ask levels while also maintaining a tracker for efficient order lookup and interaction.

The tracker is a dictionary where:

- The key is a string representation of the order’s UUID, as stored in the database.
- The value is a Position object.

The Position object acts as a reference point for orders, allowing quick lookups. It consists of three attributes:

1. **Order**
2. **Take Profit**
3. **Stop Loss**

Each of these attributes is of type Order, a lightweight container class that holds the dictionary representation of the corresponding database record and tag which is used to identify the type of order it is; whether it's the entry, take profit or stop loss representation of the order. Any modifications made to an order are automatically reflected across all references in the system.

When it comes to the naming of the Redis keys, for the pub-sub it's `<instrument>.live` and for retrieving the current price it's `<instrument>.price`.

The Pusher serves as a global throttle and consolidator for database updates, reducing complexity in lock control and managing the pub-sub channel. It ensures that updates are efficiently relayed to users subscribed to the WebSocket.

It has three distinct methods: `_push_fast`, `_push_slow`, and `_push_balance`. Each method operates with a specific delay, which can be adjusted to control the speed of updates. Updates are stored in a queue, and on each cycle, a batch of updates (determined by the batch size set during initialization) is extracted and processed.

Both the OrderBook and Pusher classes use Redis' pub-sub system to send updates to the manager class within the `/instrument` and `/order` WebSocket endpoints. The corresponding `ClientManager` classes subscribe to these updates.

The OrderBook and FuturesEngine both rely on a single client-facing method, `append`, to add data to the queue.

# **Future**
In the future, I plan to add a spot engine and integrate a crypto layer, enabling cryptocurrency trading within this engine. In the near future I'll be improving the throughput of the engine and posting benchmarks.