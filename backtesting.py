import pandas as pd
import ccxt  # Para obtener datos históricos sin API key
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
        self.exchange = ccxt.binance({'enableRateLimit': True})  # No requiere API keys
        
    def load_historical_data(self):
        """Obtiene datos históricos usando ccxt sin necesidad de API keys"""
        try:
            # Convertir fechas a timestamps
            since = int(self.start_date.timestamp() * 1000)
            until = int(self.end_date.timestamp() * 1000)
            
            # Obtener datos históricos
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe='15m',
                since=since,
                limit=1000  # Ajustar según necesidad
            )
            
            # Crear DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
        except Exception as e:
            print(f"Error al obtener datos históricos: {e}")
            return None
    
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

# Ejemplo de uso
if __name__ == "__main__":
    # Definir período de backtesting
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # Últimos 30 días
    
    # Crear instancia de Backtester
    backtester = Backtester(
        symbol="BTC/USDT",
        start_date=start_date,
        end_date=end_date,
        initial_balance=1000
    )
    
    # Cargar datos históricos
    historical_data = backtester.load_historical_data()
    
    if historical_data is not None:
        # Añadir indicadores
        historical_data = backtester.add_indicators(historical_data)
        
        # Ejecutar backtest
        results = backtester.run_backtest(historical_data)
        
        # Mostrar resultados
        print("\nResultados del Backtesting:")
        print(f"Balance Final: ${backtester.balance:.2f}")
        print(f"Retorno: {((backtester.balance - backtester.initial_balance) / backtester.initial_balance * 100):.2f}%")
        print(f"Número de operaciones: {len(results)}") 