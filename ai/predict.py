import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.layers import LSTM
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error


def plot_price():
    plt.plot(df['price'])
    plt.show()


def build_dataset(dataset, look_back=1):
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


def plot_train_test(time_steps, dataset, train_preds, test_preds):
    plt.plot(dataset, label='Actual Price')
    plt.plot(np.arange(time_steps, time_steps + len(train_preds)), train_preds, label='Train Predictions')
    plt.plot(np.arange(time_steps + len(train_preds), time_steps + len(test_preds) + len(train_preds)), test_preds, label="Test Predictions")

    plt.ylabel("Scaled Price")
    plt.xlabel("Time")
    plt.legend()
    plt.show()
    

tf.random.set_seed(7)
# tf.debugging.set_log_device_placement(True)

filename = 'appl.csv'

df = pd.read_csv(os.path.dirname(__file__) + f'/{filename}')
df['price'] = df['price'].astype(float)
df = df[['price']]

scaler = MinMaxScaler(feature_range=(0, 1))
df = scaler.fit_transform(df)

train_size = int(len(df) * 0.8)
train, test = df[:train_size], df[train_size: ]

# - 100: Correct predictions, slightly too early
# - 35: decent
look_back = 80
trainX, trainY = build_dataset(train, look_back)
testX, testY = build_dataset(test, look_back)

# LSTM
with tf.device('/GPU:0'):
    model = Sequential()
    model.add(LSTM(50, input_shape=(look_back, 1), return_sequences=True))
    model.add(LSTM(50))
    model.add(Dense(32))
    model.add(Dense(1))
    
    model.compile(loss='mean_squared_error', optimizer='adam')
    model.fit(trainX, trainY, epochs=200, batch_size=64, verbose=2)
    
    train_preds = model.predict(trainX)
    test_preds = model.predict(testX)    
    
    eval_preds = model.evaluate(trainX, trainY, batch_size=64)
    print("Eval Preds: ", eval_preds)


plot_train_test(look_back, df, train_preds, test_preds) 