import sys
import requests
import matplotlib.pyplot as plt

import os
from dotenv import load_dotenv

import numpy as np
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

import pandas as pd
from tqdm import tqdm

# Local
from .utils import CURRENT_FOLDER, LOOK_BACK, build_dataset, normalise

tqdm.pandas()
load_dotenv()

# Constants
# ^^^^^^
JWT_TOKEN = os.getenv('JWT_TOKEN')
DATASET_FILENAME = 'datasets/market_data.csv'
PRICE_COL = 'price'

SCALER = MinMaxScaler(feature_range=(0, 1))
MODEL_FILENAME = 'models/pred_7.keras'
MODEL = tf.keras.models.load_model(CURRENT_FOLDER + f'/{MODEL_FILENAME}')


def download_data() -> None:
    r = requests.get("http://127.0.0.1:80/instruments/csv?ticker=APPL&interval=1m", 
                     headers={'Authorization': f'Bearer {JWT_TOKEN}'})
    
    with open(CURRENT_FOLDER + '/datasets/my_data.csv', 'wb') as f:
        f.write(r.content)


# Testing
# ^^^^^^
df = pd.read_csv(CURRENT_FOLDER + f'/{DATASET_FILENAME}')
df[PRICE_COL] = df[PRICE_COL].astype(float)
scaled_price, _ = build_dataset(dataset=SCALER.fit_transform(df[[PRICE_COL]]), look_back=LOOK_BACK)

preds = MODEL.predict(scaled_price)
normalied_preds = normalise(arr=preds, scaler=SCALER)

preds = [None for _ in range(LOOK_BACK)]
preds.extend(normalied_preds)
df['predictions'] = preds


# Plot
# ^^^^^^
def plot_data():
    plt.plot(df[PRICE_COL], label='market price')
    plt.plot(df['predictions'], label='predictions')
    plt.legend()
    plt.show()


plot_data()
