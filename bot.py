import time
import pandas as pd
import numpy as np
import requests
import os
from dotenv import load_dotenv
load_dotenv()

# Telegram bilgileri
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Binance verisini çekmek için
from binance.client import Client
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key, api_secret)

# Parametreler
symbol = 'BTCUSDT'
interval = '5m'
length = 32
percent = 0.7
coeff = 0.001

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, data=payload)

def get_ohlcv(symbol, interval, limit=100):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df.astype(float)
    return df[['open', 'high', 'low', 'close', 'volume']]

def VAR(src, length):
    valpha = 2 / (length + 1)
    vud1 = src.diff().clip(lower=0)
    vdd1 = -src.diff().clip(upper=0)
    vUD = vud1.rolling(9).sum()
    vDD = vdd1.rolling(9).sum()
    vCMO = (vUD - vDD) / (vUD + vDD)
    VAR = pd.Series(index=src.index, dtype='float64')
    for i in range(len(src)):
        if i == 0:
            VAR.iloc[i] = src.iloc[i]
        else:
            VAR.iloc[i] = valpha * abs(vCMO.iloc[i]) * src.iloc[i] + (1 - valpha * abs(vCMO.iloc[i])) * VAR.iloc[i - 1]
    return VAR

def compute_tott(df):
    src = df['close']
    ma = VAR(src, length)
    fark = ma * percent * 0.01

    longStop = pd.Series(index=ma.index)
    shortStop = pd.Series(index=ma.index)
    dirr = pd.Series(index=ma.index)
    MT = pd.Series(index=ma.index)
    OTT = pd.Series(index=ma.index)

    for i in range(len(ma)):
        if i == 0:
            longStop.iloc[i] = ma.iloc[i] - fark.iloc[i]
            shortStop.iloc[i] = ma.iloc[i] + fark.iloc[i]
            dirr.iloc[i] = 1
        else:
            longStopPrev = longStop.iloc[i - 1]
            shortStopPrev = shortStop.iloc[i - 1]
            longStop.iloc[i] = max(ma.iloc[i] - fark.iloc[i], longStopPrev) if ma.iloc[i] > longStopPrev else ma.iloc[i] - fark.iloc[i]
            shortStop.iloc[i] = min(ma.iloc[i] + fark.iloc[i], shortStopPrev) if ma.iloc[i] < shortStopPrev else ma.iloc[i] + fark.iloc[i]
            dirr.iloc[i] = dirr.iloc[i - 1]
            if dirr.iloc[i - 1] == -1 and ma.iloc[i] > shortStopPrev:
                dirr.iloc[i] = 1
            elif dirr.iloc[i - 1] == 1 and ma.iloc[i] < longStopPrev:
                dirr.iloc[i] = -1

        MT.iloc[i] = longStop.iloc[i] if dirr.iloc[i] == 1 else shortStop.iloc[i]
        OTT.iloc[i] = MT.iloc[i] * (200 + percent) / 200 if ma.iloc[i] > MT.iloc[i] else MT.iloc[i] * (200 - percent) / 200

    OTTup = OTT * (1 + coeff)
    OTTdn = OTT * (1 - coeff)

    df['ma'] = ma
    df['OTTup2'] = OTTup.shift(2)
    df['OTTdn2'] = OTTdn.shift(2)
    df['buy'] = (df['ma'] > df['OTTup2']) & (df['ma'].shift(1) <= df['OTTup2'].shift(1))
    df['sell'] = (df['ma'] < df['OTTdn2']) & (df['ma'].shift(1) >= df['OTTdn2'].shift(1))
    return df

def run():
    df = get_ohlcv(symbol, interval)
    df = compute_tott(df)
    if df['buy'].iloc[-1]:
        print("📈 BUY SIGNAL")
        send_telegram("📈 BUY SIGNAL (TOTT) — BTC/USDT 5m")
    elif df['sell'].iloc[-1]:
        print("📉 SELL SIGNAL")
        send_telegram("📉 SELL SIGNAL (TOTT) — BTC/USDT 5m")
    else:
        print("⏳ No signal")

# Sürekli çalıştır
while True:
    run()
    time.sleep(60)
