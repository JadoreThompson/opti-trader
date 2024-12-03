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
        x.append(dataset[i])
        
        next = i + look_back
        if next < l:
            y.append(dataset[next])
    
    diff = len(x) - abs(len(x) - len(y))
    return np.array(x[:diff]), np.array(y)
    

tf.random.set_seed(7)
# tf.debugging.set_log_device_placement(True)

filename = 'appl.csv'

df = pd.read_csv(os.path.dirname(__file__) + f'/{filename}')
df = df.drop(columns=['id', 'ticker', 'date'])
df['price'] = df['price'].astype(float)

scaler = MinMaxScaler(feature_range=(0, 1))
df = scaler.fit_transform(df)

train_size = int(len(df) * 0.8)
train, test = df[:train_size], df[train_size: ]

# - 100: Correct predictions, slightly too early
# - 35: decent
look_back = 100
trainX, trainY = build_dataset(train, look_back)
testX, testY = build_dataset(test, look_back)

trainX = np.reshape(trainX, (trainX.shape[0], len(trainX[0]), trainX.shape[1]))
testX = np.reshape(testX, (testX.shape[0], len(testX[0]), testX.shape[1]))

# LSTM
with tf.device('/GPU:0'):
    model = Sequential()
    model.add(LSTM(4, input_shape=(look_back, 1)))
    model.add(Dense(1))
    model.compile(loss='mean_squared_error', optimizer='adam')
    model.fit(trainX, trainY, epochs=300, batch_size=1, verbose=2)
    train_preds = model.predict(trainX)
    test_preds = model.predict(testX)


plt.plot(df, label='Actual Price')
plt.plot(train_preds, label='Train Price')

test_preds = train_preds.extend(test_preds)
plt.plot(test_preds, label='Test Preds')
plt.show()