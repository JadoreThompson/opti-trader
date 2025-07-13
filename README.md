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

The times below represent the execution time for the `FuturesEngine::place_order` method not calling the PositionManager’s `apply_entry_fill` and `apply_close` methods as they calculated extra things un concerning to the match i.e. filled price, closed_at and close_price.

**GC Enabled**

| Test Name | Min (µs) | Max (µs) | Mean (µs) | StdDev (µs) | Median (µs) | IQR (µs) | Outliers | OPS (Kops/s) | Rounds | Iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `test_futures_engine_place_order_performance[10000]` | 3.1 | 1,230.6 | 11.24 | 19.15 | 9.6 | 9.25 | 124;150 | 88.97 | 10000 | 1 |
| `test_futures_engine_place_order_performance[1000]` | 3.2 | 79.0 | 11.78 | 8.21 | 10.8 | 11.45 | 185;15 | 84.88 | 1000 | 1 |
| `test_futures_engine_place_order_performance[2000]` | 3.2 | 100.3 | 12.13 | 8.40 | 10.6 | 11.40 | 408;28 | 82.43 | 2000 | 1 |
| `test_futures_engine_place_order_performance[100000]` | 3.0 | 71,279.2 | 13.03 | 280.19 | 10.6 | 11.70 | 23;694 | 76.77 | 100000 | 1 |
| `test_futures_engine_place_order_performance[500]` | 3.2 | 527.7 | 14.69 | 25.84 | 11.8 | 11.90 | 12;15 | 68.07 | 500 | 1 |
| `test_futures_engine_place_order_performance[100]` | 3.6 | 98.9 | 16.90 | 16.12 | 13.15 | 13.10 | 9;7 | 59.17 | 100 | 1 |

**GC Disabled**

| Test Name | Min (µs) | Max (µs) | Mean (µs) | StdDev (µs) | Median (µs) | IQR (µs) | Outliers | OPS (Kops/s) | Rounds | Iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `test_futures_engine_place_order_performance[1000]` | 3.1 | 56.1 | 10.06 | 5.51 | 8.7 | 9.1 | 397;4 | 99.45 | 1000 | 1 |
| `test_futures_engine_place_order_performance[2000]` | 3.1 | 50.3 | 10.69 | 5.97 | 9.3 | 11.05 | 890;4 | 93.50 | 2000 | 1 |
| `test_futures_engine_place_order_performance[10000]` | 3.0 | 152.9 | 10.76 | 6.45 | 9.4 | 11.1 | 3858;49 | 92.92 | 10000 | 1 |
| `test_futures_engine_place_order_performance[100000]` | 3.0 | 7,047.3 | 11.69 | 34.56 | 10.0 | 8.9 | 623;1638 | 85.57 | 100000 | 1 |
| `test_futures_engine_place_order_performance[100]` | 3.1 | 66.1 | 12.20 | 10.41 | 9.05 | 10.0 | 9;3 | 81.96 | 100 | 1 |
| `test_futures_engine_place_order_performance[500]` | 3.2 | 329.1 | 13.98 | 21.40 | 10.9 | 9.45 | 16;18 | 71.53 | 500 | 1 |

The times below represent the execution time for the `FuturesEngine::place_order` method calling the PositionManager’s `apply_entry_fill` and `apply_close` methods.

**GC Enabled**

| Test Name | Min (µs) | Max (µs) | Mean (µs) | StdDev (µs) | Median (µs) | IQR (µs) | Outliers | OPS (Kops/s) | Rounds | Iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `test_futures_engine_place_order_performance[1000]` | 7.4 (1.06) | 75.0 (1.00) | 13.93 (1.00) | 6.15 (1.00) | 14.2 (1.04) | 8.8 (1.00) | 123;9 | 71.80 (1.00) | 1000 | 1 |
| `test_futures_engine_place_order_performance[2000]` | 7.0 (1.00) | 921.8 (12.29) | 14.33 (1.03) | 21.34 (3.47) | 13.7 (1.00) | 8.8 (1.00) | 16;30 | 69.80 (0.97) | 2000 | 1 |
| `test_futures_engine_place_order_performance[500]` | 7.3 (1.04) | 143.1 (1.91) | 14.52 (1.04) | 8.73 (1.42) | 14.4 (1.05) | 9.0 (1.02) | 27;7 | 68.88 (0.96) | 500 | 1 |
| `test_futures_engine_place_order_performance[10000]` | 7.2 (1.03) | 939.1 (12.52) | 14.61 (1.05) | 15.83 (2.58) | 14.5 (1.06) | 9.1 (1.03) | 136;122 | 68.43 (0.95) | 10000 | 1 |
| `test_futures_engine_place_order_performance[100]` | 7.1 (1.01) | 76.6 (1.02) | 16.12 (1.16) | 10.56 (1.72) | 15.2 (1.11) | 10.6 (1.20) | 6;4 | 62.02 (0.86) | 100 | 1 |
| `test_futures_engine_place_order_performance[100000]` | 7.3 (1.04) | 130,715.2 (>1000.0) | 20.40 (1.46) | 685.75 (111.59) | 15.5 (1.13) | 9.3 (1.06) | 35;1501 | 49.03 (0.68) | 100000 | 1 |

**GC Disabled**

| Test Name | Min (µs) | Max (µs) | Mean (µs) | StdDev (µs) | Median (µs) | IQR (µs) | Outliers | OPS (Kops/s) | Rounds | Iterations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `test_futures_engine_place_order_performance[1000]` | 7.4 (1.28) | 73.6 (1.14) | 13.95 (1.00) | 5.51 (1.07) | 14.55 (1.00) | 8.9 (1.02) | 305;5 | 71.67 (1.00) | 1000 | 1 |
| `test_futures_engine_place_order_performance[2000]` | 7.2 (1.24) | 64.6 (1.00) | 14.10 (1.01) | 5.17 (1.00) | 14.85 (1.02) | 9.0 (1.03) | 895;6 | 70.94 (0.99) | 2000 | 1 |
| `test_futures_engine_place_order_performance[100000]` | 5.8 (1.00) | 2,009.1 (31.10) | 14.48 (1.04) | 12.98 (2.51) | 14.50 (1.00) | 8.7 (1.00) | 1075;626 | 69.06 (0.96) | 100000 | 1 |
| `test_futures_engine_place_order_performance[10000]` | 7.4 (1.28) | 193.3 (2.99) | 14.61 (1.05) | 6.70 (1.30) | 14.90 (1.03) | 9.0 (1.03) | 775;59 | 68.47 (0.96) | 10000 | 1 |
| `test_futures_engine_place_order_performance[500]` | 7.3 (1.26) | 118.1 (1.83) | 14.61 (1.05) | 7.68 (1.48) | 15.00 (1.03) | 9.6 (1.10) | 34;7 | 68.44 (0.95) | 500 | 1 |
| `test_futures_engine_place_order_performance[100]` | 6.7 (1.16) | 72.9 (1.13) | 15.79 (1.13) | 10.12 (1.96) | 14.50 (1.00) | 9.5 (1.09) | 8;4 | 63.32 (0.88) | 100 | 1 |

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