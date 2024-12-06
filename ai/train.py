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
from .utils import CURRENT_FOLDER, LOOK_BACK, build_dataset


def plot_price():
    plt.plot(new_df['price'])
    plt.show()

tf.random.set_seed(7)

dataset = 'datasets/market_data.csv'
scaler = MinMaxScaler(feature_range=(0, 1))
PRICE_COL = 'price'

df = pd.read_csv(os.path.dirname(__file__) + f'/{dataset}')
df[PRICE_COL] = df[PRICE_COL].astype(float)
new_df = scaler.fit_transform(df[[PRICE_COL]])

train_size = int(len(new_df) * 0.8)
train, test = new_df[:train_size], new_df[train_size: ]

trainX, trainY = build_dataset(train, LOOK_BACK)
testX, testY = build_dataset(test, LOOK_BACK)


# Model
with tf.device('/GPU:0'):
    # Initialisation
    model = Sequential()
    model.add(LSTM(LOOK_BACK, input_shape=(LOOK_BACK, 1), return_sequences=True))
    model.add(LSTM(int(LOOK_BACK * 1.2)))
    model.add(Dense(1))
    
    model.compile(loss='mean_squared_error', optimizer='adam')
    model.fit(trainX, trainY, epochs=500, batch_size=64, verbose=2)
    
    # Predictions
    train_preds = model.predict(trainX)
    test_preds = model.predict(testX)
    
    eval_pred = model.evaluate(trainX, trainY, batch_size=64, verbose=2)
    print("Normalised RMSE: ", round((np.sqrt(eval_pred) / (max(df[PRICE_COL]) - min(df[PRICE_COL]))) * 100), 4)
    
    print('Saving Model...')
    model.save(CURRENT_FOLDER + '/models/pred_3.keras')
    print('Model saved (+_+) >> ', CURRENT_FOLDER + '/models/pred_3.keras')
    

def plot_train_test(time_steps, dataset, train_preds, test_preds):
    plt.plot(dataset, label='Actual Price')
    plt.plot(np.arange(time_steps, time_steps + len(train_preds)), train_preds, label='Train Predictions')
    plt.plot(np.arange(time_steps + len(train_preds), time_steps + len(test_preds) + len(train_preds)), test_preds, label="Test Predictions")

    plt.ylabel("Scaled Price")
    plt.xlabel("Time")
    plt.legend()
    plt.show()

plot_train_test(LOOK_BACK, new_df, train_preds, test_preds)
