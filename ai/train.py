import os
import matplotlib.pyplot as plt
import pandas as pd

import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.layers import LSTM
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error

# Local
from .utils import build_dataset, LOOK_BACK


def plot_price():
    plt.plot(new_df['price'])
    plt.show()


def plot_train_test(time_steps, dataset, train_preds, test_preds):
    plt.plot(dataset, label='Actual Price')
    plt.plot(np.arange(time_steps, time_steps + len(train_preds)), train_preds, label='Train Predictions')
    plt.plot(np.arange(time_steps + len(train_preds), time_steps + len(test_preds) + len(train_preds)), test_preds, label="Test Predictions")

    plt.ylabel("Scaled Price")
    plt.xlabel("Time")
    plt.legend()
    plt.show()
    

tf.random.set_seed(7)

filename = 'datasets/market_data.csv'

df = pd.read_csv(os.path.dirname(__file__) + f'/{filename}')
df['price'] = df['price'].astype(float)
new_df = df[['price']]

scaler = MinMaxScaler(feature_range=(0, 1))
new_df = scaler.fit_transform(new_df)

train_size = int(len(new_df) * 0.8)
train, test = new_df[:train_size], new_df[train_size: ]

trainX, trainY = build_dataset(train, LOOK_BACK)
testX, testY = build_dataset(test, LOOK_BACK)


# LSTM
with tf.device('/GPU:0'):
    model = Sequential()
    model.add(LSTM(25, input_shape=(LOOK_BACK, 1), return_sequences=True))
    model.add(LSTM(25))
    model.add(Dense(32))
    model.add(Dense(1))
    
    model.compile(loss='mean_squared_error', optimizer='adam')
    model.fit(trainX, trainY, epochs=500, batch_size=64, verbose=2)
    
    train_preds = model.predict(trainX)
    test_preds = model.predict(testX)    
    
    eval_pred = model.evaluate(trainX, trainY, batch_size=64, verbose=2)
    print("Normalised RMSE: ", round((np.sqrt(eval_pred) / (max(df['price']) - min(df['price']))) * 100), 4)
    
    print('Saving Model...')
    model.save('./pred.keras')
    print('Model saved -_-')


plot_train_test(LOOK_BACK, new_df, train_preds, test_preds) 