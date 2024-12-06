import os
import numpy as np
import matplotlib.pyplot as plt


# Constants
# ------------------------------------
LOOK_BACK = 100
CURRENT_FOLDER = os.path.dirname(__file__)
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
