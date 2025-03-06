from collections import defaultdict
from db_models import MarketData
from .models import OHLC, Timeframe


def generate_ohlc(data: list[MarketData], timeframe: Timeframe) -> list[OHLC]:
    grouped_data = defaultdict(list)
    timeframe_seconds = timeframe.get_seconds()

    for entry in data:
        bucket = (entry.time // timeframe_seconds) * timeframe_seconds
        grouped_data[bucket].append(entry)

    return [
        OHLC(
            open=entries[0].price,
            high=max(e.price for e in entries),
            low=min(e.price for e in entries),
            close=entries[-1].price,
            time=timestamp,
        )
        for timestamp, entries in sorted(grouped_data.items())
    ]
