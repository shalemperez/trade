import pandas as pd
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator
from ta.volatility import BollingerBands

class Backtester:
    def __init__(self, symbol, start_date, end_date, initial_balance=1000):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions = []
        
    def load_historical_data(self, client):
        # Obtener datos históricos de Binance
        klines = client.get_historical_klines(
            self.symbol,
            Client.KLINE_INTERVAL_15MINUTE,
            self.start_date.strftime("%d %b %Y %H:%M:%S"),
            self.end_date.strftime("%d %b %Y %H:%M:%S")
        )
        
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                         'close_time', 'quote_volume', 'trades', 'taker_base',
                                         'taker_quote', 'ignored'])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close'] = df['close'].astype(float)
        return df
    
    def add_indicators(self, df):
        # RSI
        df['RSI'] = RSIIndicator(close=df['close']).rsi()
        
        # SMA
        df['SMA_20'] = SMAIndicator(close=df['close'], window=20).sma_indicator()
        df['SMA_50'] = SMAIndicator(close=df['close'], window=50).sma_indicator()
        
        # EMA
        df['EMA_12'] = EMAIndicator(close=df['close'], window=12).ema_indicator()
        df['EMA_26'] = EMAIndicator(close=df['close'], window=26).ema_indicator()
        
        # Bollinger Bands
        bollinger = BollingerBands(close=df['close'])
        df['BB_upper'] = bollinger.bollinger_hband()
        df['BB_lower'] = bollinger.bollinger_lband()
        
        return df
    
    def run_backtest(self, df):
        position = None
        entry_price = 0
        trades = []
        
        for index, row in df.iterrows():
            if position is None:
                # Señales de entrada
                if (row['RSI'] < 30 and 
                    row['close'] < row['BB_lower'] and 
                    row['EMA_12'] > row['EMA_26']):
                    position = 'LONG'
                    entry_price = row['close']
                    trades.append({
                        'type': 'ENTRY',
                        'position': 'LONG',
                        'price': row['close'],
                        'timestamp': index
                    })
            else:
                # Señales de salida
                if position == 'LONG':
                    if (row['RSI'] > 70 or 
                        row['close'] < entry_price * 0.98):  # Stop loss 2%
                        profit = (row['close'] - entry_price) / entry_price
                        self.balance *= (1 + profit)
                        position = None
                        trades.append({
                            'type': 'EXIT',
                            'position': 'LONG',
                            'price': row['close'],
                            'timestamp': index,
                            'profit': profit
                        })
        
        return trades 