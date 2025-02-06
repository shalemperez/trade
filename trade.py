from binance.client import Client
from binance.enums import *
import time
import pandas as pd
from ta.momentum import RSIIndicator
import csv

# Configuración de las credenciales de Binance
API_KEY = "TU_API_KEY"
API_SECRET = "TU_API_SECRET"

client = Client(API_KEY, API_SECRET)

# Configuración inicial
SYMBOL = "BTCUSDT"  # Par de trading
TIMEFRAME = "15m"  # Marco temporal (15 minutos)
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
DEFAULT_BUDGET = 50  # Presupuesto predeterminado en USD
CSV_FILE = "trading_history.csv"  # Archivo para guardar el historial de operaciones

def get_historical_data(symbol, interval, limit=100):
    """Obtiene datos históricos de velas (candlesticks)"""
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume', 
                                       'close_time', 'quote_asset_volume', 'number_of_trades', 
                                       'taker_buy_base', 'taker_buy_quote', 'ignore'])
    df['close'] = df['close'].astype(float)
    return df

def calculate_rsi(data, period):
    """Calcula el RSI usando la librería TA"""
    rsi = RSIIndicator(close=data['close'], window=period).rsi()
    return rsi

def place_order(symbol, side, quantity):
    """Coloca una orden de mercado"""
    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        print(f"Orden ejecutada: {side} {quantity} {symbol}")
        return order
    except Exception as e:
        print(f"Error al colocar la orden: {e}")
        return None

def write_to_csv(order):
    """Guarda el historial de operaciones en un archivo CSV"""
    try:
        with open(CSV_FILE, mode='a', newline='') as file:
            writer = csv.writer(file)
            if file.tell() == 0:  # Si el archivo está vacío, escribir los encabezados
                writer.writerow(["symbol", "side", "price", "quantity", "timestamp"])
            writer.writerow([
                order['symbol'],
                order['side'],
                order['fills'][0]['price'],  # Precio de ejecución
                order['executedQty'],  # Cantidad ejecutada
                order['transactTime']  # Tiempo de la transacción
            ])
    except Exception as e:
        print(f"Error al escribir en el archivo CSV: {e}")

def main(budget=DEFAULT_BUDGET):
    position = None  # Estado de la posición (None, "LONG", "SHORT")
    while True:
        # Obtener datos de mercado
        data = get_historical_data(SYMBOL, TIMEFRAME)
        data['RSI'] = calculate_rsi(data, RSI_PERIOD)

        # Último valor de RSI
        rsi = data['RSI'].iloc[-1]
        print(f"RSI actual: {rsi}")

        # Cantidad a operar basada en el presupuesto
        latest_price = data['close'].iloc[-1]
        trade_quantity = round(budget / latest_price, 6)  # Calcula la cantidad basada en el presupuesto

        # Estrategia de trading
        if rsi < RSI_OVERSOLD and position != "LONG":
            print("Señal de compra detectada.")
            order = place_order(SYMBOL, SIDE_BUY, trade_quantity)
            if order:
                position = "LONG"
                write_to_csv(order)

        elif rsi > RSI_OVERBOUGHT and position != "SHORT":
            print("Señal de venta detectada.")
            order = place_order(SYMBOL, SIDE_SELL, trade_quantity)
            if order:
                position = "SHORT"
                write_to_csv(order)

        # Esperar antes de la próxima iteración
        time.sleep(60)

if __name__ == "__main__":
    import sys
    # Leer el presupuesto del argumento de línea de comandos, si se proporciona
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BUDGET
    print(f"Presupuesto inicial: ${budget}")
    main(budget)
