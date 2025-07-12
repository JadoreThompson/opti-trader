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

## Getting Started

Follow these instructions to set up the project for local development.

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