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

| Test Name | Min (µs) | Max (µs) | Mean (µs) | StdDev (µs) | Median (µs) | IQR (µs) | Outliers | OPS (Kops/s) | Rounds | Iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| test_futures_engine_place_order_performance[1000] | 12.1 | 476.4 | 23.47 | 16.77 | 20.70 | 14.95 | 20;6 | 42.61 | 1000 | 1 |
| test_futures_engine_place_order_performance[10000] | 12.2 | 23,704.3 | 28.32 | 237.51 | 22.80 | 12.00 | 5;217 | 35.31 | 10000 | 1 |
| test_futures_engine_place_order_performance[500] | 12.6 | 166.8 | 22.11 | 9.93 | 20.15 | 14.05 | 37;4 | 45.23 | 500 | 1 |
| test_futures_engine_place_order_performance[100000] | 12.7 | 90,619.1 | 26.74 | 407.25 | 21.50 | 13.20 | 45;1083 | 37.39 | 100000 | 1 |
| test_futures_engine_place_order_performance[2000] | 13.1 | 615.9 | 24.30 | 17.83 | 21.20 | 14.30 | 54;26 | 41.16 | 2000 | 1 |
| test_futures_engine_place_order_performance[100] | 13.3 | 91.7 | 27.02 | 13.20 | 24.85 | 14.45 | 12;4 | 37.00 | 100 | 1 |

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