"""
BTC-USDT RSI Live Trading Bot (Binance)

Strategy:
- RSI < 28 → buy 25% of available USDT
- RSI > 72 → sell all BTC
- Stop-loss at 5% below entry price
- Checks every 1 hour

Run backtest first:  python backtest.py
Run live:            python bot.py
"""

import json
import time
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException
import pandas as pd

SYMBOL = "BTCUSDT"
RSI_PERIOD = 14
RSI_BUY = 28
RSI_SELL = 72
POSITION_SIZE = 0.25
STOP_LOSS_PCT = 0.05
MIN_NOTIONAL = 10.0  # Binance minimum order in USDT
CHECK_INTERVAL = 3600  # 1 hour in seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)


def load_client():
    with open("keys.json") as f:
        keys = json.load(f)
    creds = list(keys["binance"].values())[0]
    return Client(creds["API_KEY"], creds["API_SECRET"])


def compute_rsi(closes, period=14):
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def get_rsi_and_price(client):
    klines = client.get_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_1HOUR, limit=100)
    closes = pd.Series([float(k[4]) for k in klines])
    rsi_series = compute_rsi(closes, RSI_PERIOD)
    return float(rsi_series.iloc[-1]), float(klines[-1][4])


def get_balance(client, asset):
    return float(client.get_asset_balance(asset=asset)["free"])


def run():
    client = load_client()
    owns_position = False
    buy_price = None

    log.info("Bot started — %s | RSI buy<%d sell>%d | stop-loss %.0f%% | position %.0f%%",
             SYMBOL, RSI_BUY, RSI_SELL, STOP_LOSS_PCT * 100, POSITION_SIZE * 100)

    while True:
        try:
            rsi_value, price = get_rsi_and_price(client)
            log.info("Price=$%.2f  RSI=%.1f  position=%s", price, rsi_value, "OPEN" if owns_position else "NONE")

            # Stop-loss check
            if owns_position and buy_price and price <= buy_price * (1 - STOP_LOSS_PCT):
                btc = get_balance(client, "BTC")
                qty = round(btc, 5)
                if qty > 0:
                    client.order_market_sell(symbol=SYMBOL, quantity=qty)
                    log.warning("STOP-LOSS — sold %.5f BTC at $%.2f (entry $%.2f, loss %.1f%%)",
                                qty, price, buy_price, (buy_price - price) / buy_price * 100)
                owns_position = False
                buy_price = None

            # Buy signal
            elif rsi_value < RSI_BUY and not owns_position:
                usdt = get_balance(client, "USDT")
                spend = usdt * POSITION_SIZE
                if spend >= MIN_NOTIONAL:
                    qty = round(spend / price, 5)
                    client.order_market_buy(symbol=SYMBOL, quantity=qty)
                    owns_position = True
                    buy_price = price
                    log.info("BUY  %.5f BTC at $%.2f (RSI=%.1f, spent $%.2f)", qty, price, rsi_value, spend)
                else:
                    log.warning("Buy signal but balance too low ($%.2f < $%.2f min)", spend, MIN_NOTIONAL)

            # Sell signal
            elif rsi_value > RSI_SELL and owns_position:
                btc = get_balance(client, "BTC")
                qty = round(btc, 5)
                if qty > 0:
                    client.order_market_sell(symbol=SYMBOL, quantity=qty)
                    pnl = qty * (price - buy_price)
                    log.info("SELL %.5f BTC at $%.2f (RSI=%.1f, P&L %+.2f)", qty, price, rsi_value, pnl)
                owns_position = False
                buy_price = None

        except BinanceAPIException as e:
            log.error("Binance API error: %s", e)
        except Exception as e:
            log.error("Unexpected error: %s", e)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
