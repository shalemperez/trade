"""
Paper Trading — BTC-USDT RSI Strategy
Usa datos reales de Binance pero NO ejecuta órdenes reales.
Revisa cada 5 minutos y muestra el estado en vivo.
"""

import json
import time
from datetime import datetime
from binance.client import Client
import pandas as pd

SYMBOL = "BTCUSDT"
RSI_PERIOD = 14
RSI_BUY = 28
RSI_SELL = 72
POSITION_SIZE = 0.25
STOP_LOSS_PCT = 0.05
MIN_NOTIONAL = 10.0
INITIAL_USDT = 50.0
CHECK_INTERVAL = 300  # 5 minutos


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


def rsi_bar(rsi):
    """Visual RSI bar de 0-100."""
    filled = int(rsi / 5)
    bar = "█" * filled + "░" * (20 - filled)
    return f"[{bar}] {rsi:.1f}"


def print_status(price, rsi, usdt, btc, buy_price, trades, start_time):
    now = datetime.now().strftime("%H:%M:%S")
    elapsed = int((time.time() - start_time) / 60)
    portfolio_value = usdt + btc * price
    pnl = portfolio_value - INITIAL_USDT
    pnl_pct = (pnl / INITIAL_USDT) * 100
    pnl_sign = "+" if pnl >= 0 else ""

    print("\n" + "─" * 54)
    print(f"  {now}  |  Tiempo activo: {elapsed}m")
    print("─" * 54)
    print(f"  BTC/USDT     : ${price:>12,.2f}")
    print(f"  RSI (1h)     : {rsi_bar(rsi)}")

    # RSI signal hint
    if rsi < RSI_BUY:
        hint = "  ⚡ SEÑAL COMPRA ACTIVA"
    elif rsi > RSI_SELL:
        hint = "  ⚡ SEÑAL VENTA ACTIVA"
    elif rsi < 35:
        hint = "  ↓ Acercándose a zona de compra (<28)"
    elif rsi > 65:
        hint = "  ↑ Acercándose a zona de venta (>72)"
    else:
        hint = "  — Sin señal"
    print(hint)

    print("─" * 54)
    print(f"  USDT         : ${usdt:>10.2f}")
    print(f"  BTC          :  {btc:>10.5f}")
    if btc > 0 and buy_price:
        unrealized = btc * (price - buy_price)
        sl_price = buy_price * (1 - STOP_LOSS_PCT)
        print(f"  Entrada BTC  : ${buy_price:>10,.2f}")
        print(f"  Stop-loss    : ${sl_price:>10,.2f}  ({STOP_LOSS_PCT*100:.0f}% abajo)")
        u_sign = "+" if unrealized >= 0 else ""
        print(f"  P&L no real. : {u_sign}${unrealized:.2f}")
    print(f"  Portafolio   : ${portfolio_value:>10.2f}  ({pnl_sign}{pnl_pct:.1f}%)")
    print("─" * 54)
    print(f"  Trades simul.: {len(trades)}")
    if trades:
        last = trades[-1]
        t_sign = "+" if last['pnl'] >= 0 else ""
        print(f"  Último trade : {last['action']} @ ${last['price']:,.2f}  P&L: {t_sign}${last['pnl']:.2f}")
    print("─" * 54)
    print(f"  Próxima revisión en {CHECK_INTERVAL//60} minutos...")


def run():
    client = load_client()
    usdt = INITIAL_USDT
    btc = 0.0
    owns_position = False
    buy_price = None
    trades = []
    start_time = time.time()

    print("\n" + "=" * 54)
    print("  PAPER TRADING — BTC-USDT RSI Strategy")
    print("  Capital virtual: $50 USDT  |  SIN DINERO REAL")
    print(f"  RSI: compra <{RSI_BUY}  venta >{RSI_SELL}  stop-loss {STOP_LOSS_PCT*100:.0f}%")
    print("=" * 54)

    while True:
        try:
            rsi_value, price = get_rsi_and_price(client)

            # Stop-loss simulado
            if owns_position and buy_price and price <= buy_price * (1 - STOP_LOSS_PCT):
                proceeds = btc * price
                pnl = proceeds - btc * buy_price
                usdt += proceeds
                trades.append({"action": "STOP-LOSS", "price": price, "pnl": pnl})
                print(f"\n  ⛔ STOP-LOSS simulado @ ${price:,.2f}  P&L: ${pnl:.2f}")
                btc = 0.0
                owns_position = False
                buy_price = None

            # Compra simulada
            elif rsi_value < RSI_BUY and not owns_position:
                spend = usdt * POSITION_SIZE
                if spend >= MIN_NOTIONAL:
                    btc = spend / price
                    usdt -= spend
                    owns_position = True
                    buy_price = price
                    trades.append({"action": "BUY", "price": price, "pnl": 0})
                    print(f"\n  ✅ COMPRA simulada: {btc:.5f} BTC @ ${price:,.2f}  (RSI={rsi_value:.1f})")

            # Venta simulada
            elif rsi_value > RSI_SELL and owns_position:
                proceeds = btc * price
                pnl = proceeds - btc * buy_price
                usdt += proceeds
                trades.append({"action": "SELL", "price": price, "pnl": pnl})
                print(f"\n  ✅ VENTA simulada: {btc:.5f} BTC @ ${price:,.2f}  P&L: +${pnl:.2f}")
                btc = 0.0
                owns_position = False
                buy_price = None

            print_status(price, rsi_value, usdt, btc, buy_price, trades, start_time)

        except Exception as e:
            print(f"\n  Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
