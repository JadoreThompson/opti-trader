# Opti-Trader

Opti-Trader is a high-performance, trading engine suited with a robust core for order matching, position management, and real-time data propagation, built entirely with modern Python asynchronous capabilities.

### ⚠️ Project Status: In Development ⚠️

This project is currently under active development. The architecture is solidifying, but APIs may change, features are still being added, and comprehensive testing is ongoing. Thus the documentation reflects what is currently complete which is the **FuturesEngine**.

## Core Features

- **Futures Matching Engine:** A dedicated engine for matching futures orders, handling various order types, and managing the entire order lifecycle.
- **High-Performance Order Book:** Implements a sophisticated order book using sorted dictionaries for price levels and doubly-linked lists for FIFO order priority, enabling O(1) access for order operations.
- **Comprehensive Position Management:** Tracks the complete lifecycle of a trading position, including entry, partial fills, cancellations, PnL calculation (realised and unrealised), and status changes.

## Architecture & Technology Stack

Opti-Trader is built with a focus on performance, scalability, and modern development practices.

- **Backend:** Python 3.10+
- **Database:** PostgreSQL
- **Data Validation:** Pydantic

## System Components

| Component | Description |
| --- | --- |
| **engine/** | The core trading logic, containing all modules related to matching, orders, and positions. |
| engine/matching_engines | Implements the primary logic for matching incoming orders against the order book. Currently features a FuturesEngine. |
| engine/orderbook | A container (no dunder support) that manages bid/ask levels. |
| engine/position | A state machine that represents a single trading position, handling all state transitions from PENDING to CLOSED or CANCELLED. |

## Benchmark Results

## Benchmark Results

**GC Disabled**

| Test Name | Min (µs) | Max (µs) | Mean (µs) | StdDev (µs) | Median (µs) | IQR (µs) | Outliers | OPS (Kops/s) | Rounds | Iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `test_futures_engine_place_order_performance[1000]` | 3.1 | 56.1 | 10.06 | 5.51 | 8.7 | 9.1 | 397;4 | 99.45 | 1000 | 1 |
| `test_futures_engine_place_order_performance[2000]` | 3.1 | 50.3 | 10.69 | 5.97 | 9.3 | 11.05 | 890;4 | 93.50 | 2000 | 1 |
| `test_futures_engine_place_order_performance[10000]` | 3.0 | 152.9 | 10.76 | 6.45 | 9.4 | 11.1 | 3858;49 | 92.92 | 10000 | 1 |
| `test_futures_engine_place_order_performance[100000]` | 3.0 | 7,047.3 | 11.69 | 34.56 | 10.0 | 8.9 | 623;1638 | 85.57 | 100000 | 1 |
| `test_futures_engine_place_order_performance[100]` | 3.1 | 66.1 | 12.20 | 10.41 | 9.05 | 10.0 | 9;3 | 81.96 | 100 | 1 |
| `test_futures_engine_place_order_performance[500]` | 3.2 | 329.1 | 13.98 | 21.40 | 10.9 | 9.45 | 16;18 | 71.53 | 500 | 1 |

**GC Enabled**

| Test Name | Min (µs) | Max (µs) | Mean (µs) | StdDev (µs) | Median (µs) | IQR (µs) | Outliers | OPS (Kops/s) | Rounds | Iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `test_futures_engine_place_order_performance[10000]` | 3.1 | 1,230.6 | 11.24 | 19.15 | 9.6 | 9.25 | 124;150 | 88.97 | 10000 | 1 |
| `test_futures_engine_place_order_performance[1000]` | 3.2 | 79.0 | 11.78 | 8.21 | 10.8 | 11.45 | 185;15 | 84.88 | 1000 | 1 |
| `test_futures_engine_place_order_performance[2000]` | 3.2 | 100.3 | 12.13 | 8.40 | 10.6 | 11.40 | 408;28 | 82.43 | 2000 | 1 |
| `test_futures_engine_place_order_performance[100000]` | 3.0 | 71,279.2 | 13.03 | 280.19 | 10.6 | 11.70 | 23;694 | 76.77 | 100000 | 1 |
| `test_futures_engine_place_order_performance[500]` | 3.2 | 527.7 | 14.69 | 25.84 | 11.8 | 11.90 | 12;15 | 68.07 | 500 | 1 |
| `test_futures_engine_place_order_performance[100]` | 3.6 | 98.9 | 16.90 | 16.12 | 13.15 | 13.10 | 9;7 | 59.17 | 100 | 1 |

## Getting Started

### Prerequisites

- Python 3.10 or higher

### Installation & Setup

```bash
git clone https://github.com/JadoreThompson/opti-trader.git

cd opti-trader

python -m venv venv

.\venv\Scripts\activate

pip install -r requirements.txt
```