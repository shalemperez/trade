"""
Backtest: BTC-USDT RSI Strategy
- RSI < 28 → buy 25% of USDT
- RSI > 72 → sell all BTC
- Stop-loss at 5% below entry price
"""

import json
from binance.client import Client
import pandas as pd

SYMBOL = "BTCUSDT"
RSI_PERIOD = 14
RSI_BUY = 28
RSI_SELL = 72
POSITION_SIZE = 0.25
STOP_LOSS_PCT = 0.05
INITIAL_USDT = 50.0
LOOKBACK = "2 years ago UTC"
MIN_NOTIONAL = 10.0  # Binance minimum order in USDT


def load_client():
    with open("keys.json") as f:
        keys = json.load(f)
    creds = list(keys["binance"].values())[0]
    return Client(creds["API_KEY"], creds["API_SECRET"])


def fetch_data(client):
    print("Fetching 2 years of BTC-USDT hourly data from Binance...")
    klines = client.get_historical_klines(
        SYMBOL, Client.KLINE_INTERVAL_1HOUR, LOOKBACK
    )
    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df = df.set_index("open_time")[["close"]]
    print(f"Loaded {len(df)} candles.")
    return df


def compute_rsi(closes, period=14):
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def run_backtest(df):
    df = df.copy()
    df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)
    df = df.dropna()

    usdt = INITIAL_USDT
    btc = 0.0
    owns_position = False
    buy_price = None
    trades = []

    for ts, row in df.iterrows():
        price = row["close"]
        rsi = row["rsi"]

        # Stop-loss check
        if owns_position and buy_price and price <= buy_price * (1 - STOP_LOSS_PCT):
            proceeds = btc * price
            pnl = proceeds - btc * buy_price
            usdt += proceeds
            trades.append({"time": ts, "action": "STOP-LOSS", "price": price, "pnl": pnl})
            btc = 0.0
            owns_position = False
            buy_price = None
            continue

        # Buy signal
        if rsi < RSI_BUY and not owns_position:
            spend = usdt * POSITION_SIZE
            if spend >= MIN_NOTIONAL:
                btc = spend / price
                usdt -= spend
                owns_position = True
                buy_price = price
                trades.append({"time": ts, "action": "BUY", "price": price, "pnl": 0})

        # Sell signal
        elif rsi > RSI_SELL and owns_position:
            proceeds = btc * price
            pnl = proceeds - btc * buy_price
            usdt += proceeds
            trades.append({"time": ts, "action": "SELL", "price": price, "pnl": pnl})
            btc = 0.0
            owns_position = False
            buy_price = None

    final_price = df["close"].iloc[-1]
    total_value = usdt + btc * final_price
    return trades, total_value


def print_results(trades, final_value):
    print("\n" + "=" * 52)
    print("  BACKTEST RESULTS — BTC-USDT RSI Strategy")
    print("=" * 52)
    print(f"  Initial capital : ${INITIAL_USDT:.2f} USDT")
    print(f"  Final value     : ${final_value:.2f} USDT")
    pnl = final_value - INITIAL_USDT
    pnl_pct = (pnl / INITIAL_USDT) * 100
    sign = "+" if pnl >= 0 else ""
    print(f"  P&L             : {sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%)")
    print(f"  Total trades    : {len(trades)}")

    sells = [t for t in trades if t["action"] in ("SELL", "STOP-LOSS")]
    if sells:
        wins = [t for t in sells if t["pnl"] > 0]
        stop_losses = [t for t in trades if t["action"] == "STOP-LOSS"]
        print(f"  Win rate        : {len(wins)}/{len(sells)} ({100*len(wins)//len(sells)}%)")
        print(f"  Stop-losses hit : {len(stop_losses)}")
        max_loss = min((t["pnl"] for t in sells), default=0)
        max_gain = max((t["pnl"] for t in sells), default=0)
        print(f"  Best trade      : +${max_gain:.2f}")
        print(f"  Worst trade     : ${max_loss:.2f}")

    print("=" * 52)

    if trades:
        print("\n  Last 10 trades:")
        for t in trades[-10:]:
            sign = "+" if t["pnl"] >= 0 else ""
            print(f"  {t['time'].strftime('%Y-%m-%d %H:%M')}  "
                  f"{t['action']:10s}  "
                  f"${t['price']:>10,.2f}  "
                  f"P&L: {sign}${t['pnl']:.2f}")
    print()


if __name__ == "__main__":
    client = load_client()
    df = fetch_data(client)
    print("Running backtest...")
    trades, final_value = run_backtest(df)
    print_results(trades, final_value)
