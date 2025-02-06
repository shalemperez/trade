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
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.stop_loss = 0.015        # Reducido para minimizar pérdidas máximas
        self.take_profit = 0.03       # Ajustado en base al nuevo stop loss
        self.trailing_stop = 0.012    # Más ajustado para asegurar ganancias
        self.max_trades_per_day = 4   # Aumentado ligeramente
        self.min_profit_threshold = 0.01
        self.max_loss_per_day = 0.05  # Nuevo: límite de pérdida diaria
        
    def load_historical_data(self):
        """Carga datos históricos desde Binance"""
        try:
            since = int(self.start_date.timestamp() * 1000)
            
            # Obtener datos históricos
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe='15m',  # Timeframe de 15 minutos
                since=since,
                limit=2000  # Más datos
            )
            
            if not ohlcv:
                print("No se pudieron obtener datos históricos")
                return None
                
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Convertir timestamp a datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Verificar que tenemos suficientes datos
            print(f"Datos cargados: {len(df)} velas")
            
            return df
            
        except Exception as e:
            print(f"Error al cargar datos históricos: {e}")
            return None

    def add_indicators(self, df):
        # Indicadores básicos
        df['RSI'] = RSIIndicator(close=df['close'], window=self.rsi_period).rsi()
        df['SMA_20'] = SMAIndicator(close=df['close'], window=20).sma_indicator()
        df['SMA_50'] = SMAIndicator(close=df['close'], window=50).sma_indicator()
        
        # Bollinger Bands
        bollinger = BollingerBands(close=df['close'], window=20)
        df['BB_upper'] = bollinger.bollinger_hband()
        df['BB_middle'] = bollinger.bollinger_mavg()
        df['BB_lower'] = bollinger.bollinger_lband()
        
        # MACD
        macd = MACD(close=df['close'])
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        
        # Volumen y volatilidad
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        df['volatility'] = df['close'].pct_change().rolling(window=20).std()
        
        # Momentum y tendencia
        df['momentum'] = df['close'].pct_change(periods=10)
        df['trend'] = np.where(df['SMA_20'] > df['SMA_50'], 1, -1)
        
        return df

    def check_entry_conditions(self, row, prev_row):
        score = 0
        
        # Validación de tendencia más estricta
        if row['trend'] == 1:
            if row['close'] > row['SMA_20'] and row['SMA_20'] > row['SMA_50']:
                score += 3
            elif row['close'] > row['SMA_20']:
                score += 1
        
        # RSI con confirmación
        if row['RSI'] < self.rsi_oversold:
            if prev_row['RSI'] <= row['RSI']:  # RSI comenzando a subir
                score += 3
            else:
                score += 1
        
        # Volumen con más peso
        if row['volume'] > row['volume_ma20'] * 1.2:  # 20% sobre la media
            score += 2
        
        # Volatilidad más específica
        if 0.008 < row['volatility'] < 0.025:
            score += 2
        
        # MACD
        if row['MACD'] > row['MACD_signal'] and prev_row['MACD'] <= prev_row['MACD_signal']:
            score += 2
        
        # Bollinger Bands
        if row['close'] < row['BB_lower'] * 1.01:
            if row['close'] > prev_row['close']:  # Rebote confirmado
                score += 3
            else:
                score += 1
        
        return score >= 7  # Más exigente

    def check_exit_conditions(self, row, entry_price, position_time):
        profit_pct = (row['close'] - entry_price) / entry_price
        
        # Trailing stop dinámico
        trailing_stop = self.trailing_stop
        if profit_pct > self.take_profit * 0.7:
            trailing_stop = self.trailing_stop * 0.8  # Más ajustado cuando hay buenas ganancias
        
        trailing_stop_price = entry_price * (1 + profit_pct - trailing_stop)
        
        conditions = [
            # Stop loss dinámico
            row['close'] < trailing_stop_price and profit_pct > self.min_profit_threshold,
            
            # Take profit con múltiples confirmaciones
            profit_pct >= self.take_profit and (
                (row['RSI'] > self.rsi_overbought) or
                (row['close'] > row['BB_upper'] and row['volume'] < row['volume_ma20']) or
                (row['MACD'] < row['MACD_signal'] and row['close'] > row['SMA_20'])
            ),
            
            # Stop loss fijo
            profit_pct <= -self.stop_loss,
            
            # Tiempo máximo reducido
            (row['timestamp'] - position_time) > timedelta(hours=4)
        ]
        
        return any(conditions)

    def calculate_position_size(self, price, stop_loss_price):
        """Cálculo de posición mejorado con gestión de riesgo adaptativa"""
        # Riesgo base por operación
        risk_per_trade = self.balance * 0.015  # Reducido a 1.5%
        
        # Ajuste por volatilidad
        volatility_factor = 1.0
        if hasattr(self, 'current_volatility'):
            if self.current_volatility > 0.02:
                volatility_factor = 0.6
            elif self.current_volatility < 0.01:
                volatility_factor = 1.1
        
        # Ajuste por rendimiento reciente
        if hasattr(self, 'recent_trades'):
            recent_wins = sum(1 for t in self.recent_trades[-5:] if t > 0)
            performance_factor = 0.8 + (recent_wins * 0.08)  # 0.8 a 1.2
        else:
            performance_factor = 1.0
        
        position_size = (risk_per_trade * volatility_factor * performance_factor) / (price - stop_loss_price)
        max_position = self.balance * 0.8 / price  # Reducido a 80%
        
        return min(position_size, max_position)

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
            
            # Actualizar volatilidad actual
            self.current_volatility = current_row['volatility']
            
            # Resetear contador diario
            if last_trade_date != current_row['timestamp'].date():
                daily_trades = 0
                last_trade_date = current_row['timestamp'].date()
            
            if daily_trades >= self.max_trades_per_day:
                continue
                
            if not in_position:
                if self.check_entry_conditions(current_row, prev_row):
                    entry_price = current_row['close']
                    in_position = True
                    position_time = current_row['timestamp']
                    position_size = self.calculate_position_size(entry_price, current_row['BB_lower'])  # Nuevo cálculo
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

    def print_backtest_results(self, initial_balance, final_balance, trades):
        """Imprime los resultados del backtesting"""
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
        
        self.analyze_results(trades)

    def analyze_results(self, trades):
        """Analiza los resultados del backtesting"""
        if not trades:
            return
        
        profits = [t['profit'] for t in trades if 'profit' in t]
        win_trades = len([p for p in profits if p > 0])
        loss_trades = len([p for p in profits if p < 0])
        
        print("\nAnálisis Detallado:")
        print(f"Win Rate: {(win_trades / len(profits) * 100):.2f}%")
        if loss_trades > 0:  # Evitar división por cero
            profit_factor = abs(sum([p for p in profits if p > 0]) / sum([p for p in profits if p < 0]))
            print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Máxima Ganancia: ${max(profits):.2f}")
        print(f"Máxima Pérdida: ${min(profits):.2f}")
        if win_trades > 0:
            print(f"Promedio de Ganancia: ${np.mean([p for p in profits if p > 0]):.2f}")
        if loss_trades > 0:
            print(f"Promedio de Pérdida: ${np.mean([p for p in profits if p < 0]):.2f}")

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
        backtester.print_backtest_results(backtester.initial_balance, backtester.balance, trades) 