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
from .utils import LOOK_BACK, build_dataset, normalise

tqdm.pandas()
load_dotenv()

# Constants
# ^^^^^^
JWT_TOKEN = os.getenv('JWT_TOKEN')

CURRENT_FOLDER = os.path.dirname(__file__)
DATASET_FILENAME = 'datasets/market_data.csv'
PRICE_COL = 'price'

SCALER = MinMaxScaler(feature_range=(0, 1))
MODEL_FILENAMAE = 'models/pred_3.keras'
MODEL = tf.keras.models.load_model(CURRENT_FOLDER + f'/{MODEL_FILENAMAE}')


def download_data() -> None:
    r = requests.get("http://127.0.0.1:80/instruments/csv?ticker=APPL&interval=1m", 
                     headers={'Authorization': f'Bearer {JWT_TOKEN}'})
    
    with open(CURRENT_FOLDER + '/datasets/my_data.csv', 'wb') as f:
        f.write(r.content)


# Testing
# ^^^^^^

# download_data()

df = pd.read_csv(CURRENT_FOLDER + f'/{DATASET_FILENAME}')
df[PRICE_COL] = df[PRICE_COL].astype(float)
scaled_price, _ = build_dataset(dataset=SCALER.fit_transform(df[[PRICE_COL]]), look_back=80)

preds = MODEL.predict(scaled_price)
normalied_preds = normalise(arr=preds, scaler=SCALER)

df = df
preds = [None for _ in range(80)]
preds.extend(normalied_preds)
print('Length of preds: ', len(preds))
df['predictions'] = preds
print(df.head())

# Plot
# ^^^^^^
def plot_data():
    plt.plot(df[PRICE_COL], label='market price')
    plt.plot(df['predictions'], label='predictions')
    plt.legend()
    plt.show()


plot_data()
