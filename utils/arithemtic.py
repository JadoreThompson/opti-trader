import asyncio    
import math
from typing import List
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import yfinance as yf

# Local
from exceptions import InvalidAction
from enums import OrderStatus


# TODO: Trim everything


RISK_FREE = 4.0
BENCHMARK_TICKER = "^GSPC"

async def get_benchmark_returns(months_ago: int, ticker: str = BENCHMARK_TICKER) -> list[float]:
    """
    Returns

    Args:
        ticker (str)

    Raises:
        InvalidAction: Ticker not supported

    Returns:
        list[float]: A list of percentage returns for the benchmark
    """
    try:
        end = datetime.now().date()
        months_ago += 1
        start = end - relativedelta(months=months_ago)
        ticker_data = yf.download(ticker, start=start, end=end, interval="1mo")
        
        if ticker_data.empty:
            raise ValueError("Ticker possibly not supported")

        monthly_returns = ticker_data['Adj Close'].values.tolist()
        monthly_returns = [sum(item) for item in monthly_returns]
            
        return [
            round(((monthly_returns[i] - monthly_returns[i - 1]) / monthly_returns[i - 1]) * 100, 2)
            for i in range(1, len(monthly_returns))
        ]
    
    except ValueError:
        raise InvalidAction('Ticker not supported')


async def std(returns: List[float]) -> float:
    """Standard Deviation Calculation"""
    if not returns:
        return 0.0
    try:
        length_of_returns = len(returns)
        average_return = sum(returns) / length_of_returns
        individual_deviations = [(r - average_return) ** 2 for r in returns]
        return round(math.sqrt(sum(individual_deviations) / length_of_returns), 3)
    except ZeroDivisionError:
        return 0.0


async def sharpe(returns: List[float], risk_free: float = None) -> float:
    """Sharpe Ratio"""
    risk_free = RISK_FREE if not risk_free else risk_free
    try:
        std_dev = await std(returns)
        return round((sum(returns) - (risk_free * len(returns))) / std_dev, 3)
    except ZeroDivisionError:
        return 0.0


async def downward_std(returns: List[float]) -> float:
    """Returns downside deviation"""
    if not returns:
        return 0.0
    try:
        length_of_returns = len(returns)
        average_return = sum(returns) / length_of_returns
        individual_deviations = [(r - average_return) ** 2 for r in returns]
        downside_deviation = sum(d for d in individual_deviations if d < 0)
        return round(math.sqrt(downside_deviation / length_of_returns), 3)
    except ZeroDivisionError:
        return 0.0


async def sortino(returns: List[float], risk_free: float = None) -> float:
    """Sortino Ratio"""
    risk_free = RISK_FREE if not risk_free else risk_free
    try:
        downside_dev = await downward_std(returns)
        return round((sum(returns) / (risk_free * len(returns))) / downside_dev, 3)
    except ZeroDivisionError:
        return 0.0
        

async def beta(portfolio_returns: list[float], benchmark_returns: list[float]) -> float:
    """
    Returns the Beta for a portfolio against a benchmark
    
    Args:
        portfolio_returns (list[float])
        benchmark_returns (list[float])

    Returns:
        float: Beta
    """
    try:
        length = len(portfolio_returns)
        benchmark_returns = benchmark_returns[:length]
        
        avg_portfolio_return = sum(portfolio_returns) / length
        avg_benchmark_returns = sum(benchmark_returns) / length
        
        port_variations = [item - avg_portfolio_return for item in portfolio_returns]
        benchmark_variations = [item - avg_benchmark_returns for item in benchmark_returns]
        
        covariation = round(sum(port_variations[i] * benchmark_variations[i] for i in range(length)) / length, 2)
        return covariation
    
    except ZeroDivisionError:
        return 0.0
    

async def treynor(avg_pf_return: float, avg_bm_return: float, pf_beta: float) -> float:
    """
    Returns the Treynor Ratio for a portfolio
    
    Args:
        avg_pf_return (float): Average portfolio return
        avg_bm_return (float): Average benchmark return
        pf_beta (float): Portfolio's Beta

    Returns:
        float: Treyno Ratio
    """    
    try:
        (avg_pf_return - avg_bm_return) / pf_beta
    except ZeroDivisionError:
        return 0.0


async def ghpr(pf_returns: list[float]) -> float:
    """
    Returns the Geometric Holding Period Return for a portfolio
    
    Returns:
        float
    """
    if len(pf_returns) < 2:
        return 0.0
    
    pf_returns = [1 + pf_return for pf_return in pf_returns]
    
    multiplied_value = pf_returns[0] * pf_returns[1]
    
    for i in range(2, len(pf_returns)):
        multiplied_value *= pf_returns[i]
    
    return multiplied_value ** (1 - (len(multiplied_value)))


async def risk_of_ruin(
    win_rate: float,
    risk_per_trade: float,
    total_trades: int
) -> float:
    """
    Returns the risk of ruin for a portfolio
    Args:
        win_rate (float):
        risk_per_trade (float): The Average percentage of an account's balance that's risked per trade
        total_trades (int): The total amount of trades you want to calculate the risk of ruin for. E.g.
        I want to calculte the risk of ruin over 100 trades so I pass in 100

    Returns:
        float: Risk of ruin as a percentage
    """   
    if win_rate > 1:
        win_rate /= 100
        
    try:
        return ((1 - win_rate) / (1 - win_rate)) ** (total_trades * risk_per_trade)
    except ZeroDivisionError:
        return 0.0



async def get_quantitative_metrics(
    risk_per_trade: float,
    winrate: float,
    monthly_returns: dict,
    balance: float, 
    benchmark_ticker: str = BENCHMARK_TICKER, 
    months_ago: int = 6,
    total_num_trades: int = 100,
) -> dict:
    """Returns quantitative metrics

    Args:
        benchmark_ticker (str): _description_
        months_ago (int): _description_

    Raises:
        InvalidAction: benchmark ticker not supported or you provided benchmark ticker without
        months ago and vice versa
    """    
    # TODO: Reduce time take to get YFinance Data
    # TODO: Ensure the percentages are being taken from the beginning of the month
    #       or from the beginning of the segment
    if not total_num_trades:
        total_num_trades = 100
    
    print(total_num_trades)
    
    if benchmark_ticker and not months_ago or months_ago and not benchmark_ticker:
        raise InvalidAction("User specified benchmark ticker without specifying months_ago")
    
    # Getting metrics
    pf_returns_monetary = [v for _, v in monthly_returns.items()]
    pf_returns_pct = [(((balance - (-1 * v)) - balance) / balance) * 100 for _, v in monthly_returns.items()]
    
    bm_returns = await get_benchmark_returns(months_ago, benchmark_ticker)
    bm_returns = bm_returns[:len(pf_returns_monetary)]
    
    
    quant_metrics_map = {
        'sharpe': sharpe(pf_returns_pct),
        'std': std(pf_returns_pct),
        'beta': beta(pf_returns_pct, bm_returns),
        'risk_of_ruin': risk_of_ruin(winrate, risk_per_trade, total_num_trades)
    }
    
    quant_metrics_map = dict(
        zip([k for k in quant_metrics_map], await asyncio.gather(*[v for _, v in quant_metrics_map.items()]))
    )
    
    quant_metrics_map['treynor'] = await treynor(
            sum(pf_returns_pct) / len(pf_returns_pct),
            sum(bm_returns) / len(pf_returns_pct),
            quant_metrics_map['beta']
        )
    
    return quant_metrics_map
    

if __name__ == "__main__":
    result = asyncio.run(sharpe([1]))
    print(result)
