from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import pandas as pd
import numpy as np

app = FastAPI(title="Quantora API", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BINANCE_API_URL = "https://api.binance.com/api/v3/klines"

def fetch_binance_data(symbol: str, interval: str, limit: int = 250):
    try:
        url = f"{BINANCE_API_URL}?symbol={symbol.upper()}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch market data from Binance.")
        
        raw_data = response.json()
        df = pd.DataFrame(raw_data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data fetch error: {str(e)}")

def calculate_indicators(df: pd.DataFrame):
    close = df['close']
    volume = df['volume']

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean() if len(close) >= 200 else ema50

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()

    vol_sma20 = volume.rolling(window=20).mean()
    vol_ratio = volume.iloc[-1] / (vol_sma20.iloc[-1] + 1e-10)

    high_low = df['high'] - df['low']
    atr = high_low.rolling(window=14).mean()

    return {
        "price": float(close.iloc[-1]),
        "ema20": float(ema20.iloc[-1]),
        "ema50": float(ema50.iloc[-1]),
        "ema200": float(ema200.iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
        "macd": float(macd_line.iloc[-1]),
        "macd_signal": float(signal_line.iloc[-1]),
        "volume_ratio": float(vol_ratio),
        "volatility": float(atr.iloc[-1])
    }

def get_bias_for_df(df):
    ind = calculate_indicators(df)
    price = ind["price"]
    rsi = ind["rsi"]
    ema20 = ind["ema20"]
    ema50 = ind["ema50"]
    ema200 = ind["ema200"]
    macd = ind["macd"]
    signal = ind["macd_signal"]

    score = 0
    if price > ema20: score += 1
    else: score -= 1
    if price > ema50: score += 1
    else: score -= 1
    if price > ema200: score += 2
    else: score -= 2
    if rsi > 55: score += 1
    elif rsi < 45: score -= 1
    if macd > signal: score += 1
    else: score -= 1

    if score > 1: return "BULLISH", ind
    elif score < -1: return "BEARISH", ind
    else: return "NEUTRAL", ind

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "quantora-api", "mode": "multi-timeframe intelligence engine"}

@app.get("/api/analysis")
def get_market_analysis(symbol: str = Query("BTCUSDT"), timeframe: str = Query("1h")):
    # Analyze main timeframe
    df_main = fetch_binance_data(symbol, timeframe)
    bias, ind = get_bias_for_df(df_main)

    # Cross-examine other timeframes for confluence
    timeframes_to_check = ["15m", "1h", "4h", "1d"]
    confluence = {}
    
    for tf in timeframes_to_check:
        try:
            df_tf = fetch_binance_data(symbol, tf, limit=100)
            tf_bias, _ = get_bias_for_df(df_tf)
            confluence[tf] = tf_bias
        except:
            confluence[tf] = "NEUTRAL"

    support = float(df_main['low'].tail(20).min())
    resistance = float(df_main['high'].tail(20).max())

    bullish_scenario = {
        "entry_zone": f"${support * 1.002:.2f} - ${support * 1.008:.2f}",
        "target": f"${resistance:.2f}",
        "invalidation": f"${support * 0.99:.2f}",
        "risk_reward": "1 : 2.2",
        "note": "Constructed on local support bounce and volume absorption."
    }

    bearish_scenario = {
        "entry_zone": f"${resistance * 0.992:.2f} - ${resistance * 0.998:.2f}",
        "target": f"${support:.2f}",
        "invalidation": f"${resistance * 1.01:.2f}",
        "risk_reward": "1 : 2.0",
        "note": "Constructed on rejection at immediate overhead resistance."
    }

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "price": ind["price"],
        "market_bias": bias,
        "confluence": confluence,
        "indicators": ind,
        "scenarios": {
            "bullish": bullish_scenario,
            "bearish": bearish_scenario
        },
        "support_resistance": {
            "support": support,
            "resistance": resistance
        },
        "disclaimer": "Educational simulation and multi-timeframe intelligence report. Not financial advice."
    }
