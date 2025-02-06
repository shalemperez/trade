import pandas as pd
import ccxt
from datetime import datetime, timedelta
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.volatility import BollingerBands
import numpy as np

class Backtester:
    def __init__(self, symbol, start_date, end_date, initial_balance=1000):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions = []
        self.exchange = ccxt.binance({'enableRateLimit': True})
        
        # Ajuste de parámetros optimizados
        self.rsi_period = 14
        self.rsi_oversold = 30        # Más conservador para entradas
        self.rsi_overbought = 70      # Más conservador para salidas
        self.stop_loss = 0.02         # Aumentado para dar más espacio
        self.take_profit = 0.04       # Aumentado para mejor ratio riesgo/beneficio
        self.max_trades_per_day = 3   # Reducido para ser más selectivo
        self.min_profit_threshold = 0.01  # Aumentado a 1%
        self.trailing_stop = 0.015    # Nuevo: trailing stop del 1.5%
        
    def load_historical_data(self):
        try:
            since = int(self.start_date.timestamp() * 1000)
            until = int(self.end_date.timestamp() * 1000)
            
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe='15m',
                since=since,
                limit=2000  # Aumentado para más datos
            )
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['returns'] = df['close'].pct_change()
            return df
            
        except Exception as e:
            print(f"Error al obtener datos históricos: {e}")
            return None

    def add_indicators(self, df):
        # Indicadores existentes mejorados
        df['RSI'] = RSIIndicator(close=df['close'], window=self.rsi_period).rsi()
        df['SMA_20'] = SMAIndicator(close=df['close'], window=20).sma_indicator()
        df['SMA_50'] = SMAIndicator(close=df['close'], window=50).sma_indicator()
        
        # Bollinger Bands
        bollinger = BollingerBands(close=df['close'], window=20)
        df['BB_upper'] = bollinger.bollinger_hband()
        df['BB_middle'] = bollinger.bollinger_mavg()
        df['BB_lower'] = bollinger.bollinger_lband()
        
        # Nuevos indicadores
        macd = MACD(close=df['close'])
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        
        # Volatilidad
        df['volatility'] = df['returns'].rolling(window=20).std()
        
        # Tendencia
        df['trend'] = np.where(df['SMA_20'] > df['SMA_50'], 1, -1)
        
        return df

    def check_entry_conditions(self, row, prev_row):
        # Sistema de puntuación mejorado
        score = 0
        
        # Condiciones de tendencia (peso mayor)
        if row['SMA_20'] > row['SMA_50']:
            score += 3
        if row['close'] > row['SMA_20']:
            score += 2
            
        # RSI con confirmación
        if row['RSI'] < self.rsi_oversold:
            score += 3
        elif row['RSI'] < 40 and row['RSI'] > prev_row['RSI']:
            score += 1
            
        # Bollinger Bands con confirmación de volumen
        if row['close'] < row['BB_lower']:
            if row['volume'] > prev_row['volume'] * 1.2:  # Confirmación de volumen
                score += 3
            else:
                score += 1
                
        # MACD
        if row['MACD'] > row['MACD_signal'] and prev_row['MACD'] <= prev_row['MACD_signal']:
            score += 2
            
        # Volatilidad favorable
        if row['volatility'] < 0.015:  # Baja volatilidad
            score += 1
            
        return score >= 8  # Más exigente con las entradas

    def check_exit_conditions(self, row, entry_price, position_time):
        profit_pct = (row['close'] - entry_price) / entry_price
        
        # Trailing stop
        trailing_stop_price = entry_price * (1 + profit_pct - self.trailing_stop)
        
        conditions = [
            # Stop loss dinámico
            row['close'] < trailing_stop_price and profit_pct > self.min_profit_threshold,
            
            # Take profit con confirmación
            profit_pct >= self.take_profit and (
                row['RSI'] > self.rsi_overbought or
                row['close'] > row['BB_upper']
            ),
            
            # Stop loss fijo
            profit_pct <= -self.stop_loss,
            
            # Señales técnicas de salida
            row['MACD'] < row['MACD_signal'] and profit_pct > self.min_profit_threshold,
            
            # Tiempo máximo en posición
            (row['timestamp'] - position_time) > timedelta(hours=6)
        ]
        
        return any(conditions)

    def calculate_position_size(self, price):
        """Calcula el tamaño de la posición basado en gestión de riesgo"""
        risk_per_trade = self.balance * 0.02  # 2% riesgo por operación
        position_size = risk_per_trade / (price * self.stop_loss)
        return min(position_size, self.balance * 0.95 / price)  # Máximo 95% del balance

    def run_backtest(self, df):
        in_position = False
        entry_price = 0
        trades = []
        daily_trades = 0
        last_trade_date = None
        position_time = None
        
        for i in range(1, len(df)):
            current_row = df.iloc[i]
            prev_row = df.iloc[i-1]
            current_date = current_row['timestamp'].date()
            
            # Resetear contador diario
            if last_trade_date != current_date:
                daily_trades = 0
                last_trade_date = current_date
            
            if daily_trades >= self.max_trades_per_day:
                continue
                
            if not in_position:
                if self.check_entry_conditions(current_row, prev_row):
                    entry_price = current_row['close']
                    in_position = True
                    position_time = current_row['timestamp']
                    position_size = self.calculate_position_size(entry_price)  # Nuevo cálculo
                    daily_trades += 1
                    
                    trades.append({
                        'type': 'BUY',
                        'price': entry_price,
                        'timestamp': current_row['timestamp'],
                        'balance': self.balance,
                        'position_size': position_size
                    })
            else:
                if self.check_exit_conditions(current_row, entry_price, position_time):
                    in_position = False
                    trade_profit = position_size * (current_row['close'] - entry_price)
                    self.balance += trade_profit
                    
                    trades.append({
                        'type': 'SELL',
                        'price': current_row['close'],
                        'timestamp': current_row['timestamp'],
                        'balance': self.balance,
                        'profit': trade_profit
                    })
        
        return trades

def analyze_results(trades):
    if not trades:
        return
        
    profits = [t['profit'] for t in trades if 'profit' in t]
    win_trades = len([p for p in profits if p > 0])
    loss_trades = len([p for p in profits if p < 0])
    
    print("\nAnálisis Detallado:")
    print(f"Win Rate: {(win_trades / len(profits) * 100):.2f}%")
    print(f"Profit Factor: {abs(sum([p for p in profits if p > 0]) / sum([p for p in profits if p < 0])):.2f}")
    print(f"Máxima Ganancia: ${max(profits):.2f}")
    print(f"Máxima Pérdida: ${min(profits):.2f}")
    print(f"Promedio de Ganancia: ${np.mean([p for p in profits if p > 0]):.2f}")
    print(f"Promedio de Pérdida: ${np.mean([p for p in profits if p < 0]):.2f}")

def print_backtest_results(initial_balance, final_balance, trades):
    print("\nResultados del Backtesting:")
    print(f"Balance Inicial: ${initial_balance:.2f}")
    print(f"Balance Final: ${final_balance:.2f}")
    print(f"Retorno: {((final_balance - initial_balance) / initial_balance * 100):.2f}%")
    print(f"Número de operaciones: {len([t for t in trades if t['type'] == 'BUY'])}")
    
    if trades:
        print("\nÚltimas 10 operaciones:")
        for trade in trades[-10:]:
            print(f"Tipo: {trade['type']}, "
                  f"Precio: ${trade['price']:.2f}, "
                  f"Balance: ${trade['balance']:.2f}, "
                  f"Timestamp: {trade['timestamp']}")
    
    analyze_results(trades)

if __name__ == "__main__":
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    backtester = Backtester(
        symbol="BTC/USDT",
        start_date=start_date,
        end_date=end_date,
        initial_balance=1000
    )
    
    df = backtester.load_historical_data()
    
    if df is not None:
        df = backtester.add_indicators(df)
        trades = backtester.run_backtest(df)
        print_backtest_results(backtester.initial_balance, backtester.balance, trades) 