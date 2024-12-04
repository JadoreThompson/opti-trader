import numpy as np
import matplotlib.pyplot as plt


# Constants
# ------------------------------------
LOOK_BACK = 80
# ------------------------------------


# Tools
# ------------------------------------
def build_dataset(dataset, look_back=1) -> tuple[np.ndarray, np.ndarray]:
    if look_back < 1:
        raise Exception('Look back must be a positive integer')
    
    x, y = [], []
    l = len(dataset)
    for i in range(len(dataset)):
        x.append(dataset[i: i + look_back])
        
        next = i + look_back
        if next < l:
            y.append(dataset[next])
    
    diff = len(x) - abs(len(x) - len(y))
    return np.array(x[:diff]), np.array(y)


def normalise(arr, scaler) -> list:
    return [item[0] for item in scaler.inverse_transform(arr)]


def plot_data(market_price, results, **kwargs) -> None:
    r = np.arange(LOOK_BACK, LOOK_BACK + len(market_price))
    
    plt.plot(market_price, label='market price')
    plt.plot(r, results, label='results')
    
    plt.legend()
    plt.show()
# ------------------------------------