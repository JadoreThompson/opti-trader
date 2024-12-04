import sys
import requests

import os
from dotenv import load_dotenv

import numpy as np
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

import pandas as pd
from tqdm import tqdm

# Local
from .utils import LOOK_BACK, build_dataset, normalise, plot_data


tqdm.pandas()
load_dotenv()


# Constants
# --------------------------------------
JWT_TOKEN = os.getenv('JWT_TOKEN')

CURRENT_FOLDER = os.path.dirname(__file__)
DATASET_FILENAME = 'datasets/my_data.csv'
PRICE_COL = 'close'

SCALER = MinMaxScaler(feature_range=(0, 1))
MODEL_FILENAMAE = 'pred_2.keras'
MODEL = tf.keras.models.load_model(CURRENT_FOLDER + f'/{MODEL_FILENAMAE}')
# --------------------------------------


def download_data() -> None:
    r = requests.get("http://127.0.0.1:80/instruments/csv?ticker=APPL&interval=1m", 
                     headers={'Authorization': f'Bearer {JWT_TOKEN}'})
    
    with open(CURRENT_FOLDER + '/datasets/my_data.csv', 'wb') as f:
        f.write(r.content)


# Testing
# --------------------------------------
download_data()

df = pd.read_csv(CURRENT_FOLDER + f'/{DATASET_FILENAME}')
df[PRICE_COL] = df[PRICE_COL].astype(float)
scaled_price, _ = build_dataset(dataset=SCALER.fit_transform(df[[PRICE_COL]]), look_back=LOOK_BACK)

preds = MODEL.predict(scaled_price)
normalied_preds = normalise(arr=preds, scaler=SCALER)

df = df[:len(normalied_preds)]
df['predictions'] = normalied_preds
# --------------------------------------


plot_data(market_price=df[PRICE_COL], results=df['predictions'])
    