from encodings import normalize_encoding
import os
import sys

import numpy as np
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

import pandas as pd
from tqdm import tqdm

# Local
from .utils import LOOK_BACK, build_dataset, normalise, plot_data


tqdm.pandas()


# Constants
# --------------------------------------
FOLDER = os.path.dirname(__file__)
DATASET_FILENAME = 'datasets/market_data.csv'
PRICE_COL = 'price'

SCALER = MinMaxScaler(feature_range=(0, 1))
MODEL_FILENAMAE = 'pred_2.keras'
MODEL = tf.keras.models.load_model(FOLDER + f'/{MODEL_FILENAMAE}')
# --------------------------------------

# Testing
# --------------------------------------
df = pd.read_csv(FOLDER + f'/{DATASET_FILENAME}')
df[PRICE_COL] = df[PRICE_COL].astype(float)
scaled_price, _ = build_dataset(dataset=SCALER.fit_transform(df[[PRICE_COL]]), look_back=LOOK_BACK)

preds = MODEL.predict(scaled_price)
normalied_preds = normalise(arr=preds, scaler=SCALER)

df = df[:len(normalied_preds)]
df['predictions'] = normalied_preds
# --------------------------------------

plot_data(market_price=df[PRICE_COL], results=df['predictions'])
