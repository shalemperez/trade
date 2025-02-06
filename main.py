import asyncio
import time
from datetime import datetime, timedelta
import pandas as pd
from ta.trend import MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.momentum import StochasticOscillator, RSIIndicator
from backtesting import Backtester
from risk_management import RiskManager
from notifications import NotificationSystem
import numpy as np
import yaml
import ccxt

class MultiPairTrader:
    def __init__(self, trading_pairs, total_budget):
        self.trading_pairs = trading_pairs
        self.total_budget = total_budget
        self.pair_allocations = self._calculate_allocations()
        self.active_positions = {}
        
    def _calculate_allocations(self):
        """Distribuye el presupuesto entre los pares de trading"""
        base_allocation = self.total_budget / len(self.trading_pairs)
        return {pair: base_allocation for pair in self.trading_pairs}

def add_technical_indicators(df):
    """Añade indicadores técnicos consistentes con el backtester"""
    df['RSI'] = RSIIndicator(close=df['close'], window=14).rsi()
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

def analyze_signals(data, backtester_params):
    """Analiza señales usando los mismos criterios que el backtester"""
    current_row = data.iloc[-1]
    prev_row = data.iloc[-2]
    
    score = 0
    
    # Tendencia
    if current_row['trend'] == 1:  # Tendencia alcista
        score += 2
        if current_row['close'] > current_row['SMA_20']:
            score += 1
    
    # RSI
    if current_row['RSI'] < backtester_params['rsi_oversold']:
        score += 2
    elif current_row['RSI'] < 45:
        score += 1
    
    # Momentum
    if current_row['momentum'] > 0:
        score += 1
    
    # Volumen
    if current_row['volume'] > current_row['volume_ma20']:
        score += 1
    
    # Volatilidad favorable
    if 0.005 < current_row['volatility'] < 0.03:
        score += 1
    
    # Precio cerca de soporte
    if current_row['close'] < current_row['BB_lower'] * 1.01:
        score += 2
        
    should_trade = score >= 7
    
    return {
        'should_trade': should_trade,
        'entry_price': current_row['close'],
        'stop_loss': current_row['close'] * (1 - backtester_params['stop_loss']),
        'take_profit': current_row['close'] * (1 + backtester_params['take_profit']),
        'score': score
    }

async def execute_trade(pair, position_size, signals, exchange):
    """Ejecuta la operación con parámetros consistentes"""
    try:
        order = await exchange.create_order(
            symbol=pair,
            type='market',
            side='buy',
            amount=position_size,
            params={
                'stopLoss': {
                    'price': signals['stop_loss'],
                    'type': 'trailing',
                    'trailingPercent': 1.2  # 1.2%
                },
                'takeProfit': {
                    'price': signals['take_profit']
                }
            }
        )
        return True, order
    except Exception as e:
        print(f"Error al ejecutar trade: {e}")
        return False, None

async def get_historical_data(symbol, timeframe):
    """Obtiene datos históricos de Binance"""
    try:
        # Cargar configuración
        with open('config.yaml', 'r') as file:
            config = yaml.safe_load(file)
        
        # Configurar cliente de Binance
        exchange = ccxt.binance({
            'apiKey': config['binance']['api_key'],
            'secret': config['binance']['api_secret'],
            'enableRateLimit': True
        })
        
        # Obtener datos
        ohlcv = exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            limit=100  # Últimas 100 velas
        )
        
        if not ohlcv:
            return None
            
        # Convertir a DataFrame
        df = pd.DataFrame(
            ohlcv,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        
        # Convertir timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        return df
        
    except Exception as e:
        print(f"Error obteniendo datos históricos: {e}")
        return None

async def main():
    # Cargar configuración
    with open('config.yaml', 'r') as file:
        config = yaml.safe_load(file)
    
    # Inicializar componentes con parámetros consistentes
    risk_manager = RiskManager(
        initial_capital=config['trading']['initial_capital'],
        max_risk_per_trade=config['trading']['risk_per_trade'],
        max_daily_risk=config['trading']['daily_loss_limit']
    )
    
    # Inicializar notificaciones
    notifier = NotificationSystem(
        telegram_token=config['telegram']['token'],
        telegram_chat_id=config['telegram']['chat_id']
    )
    
    # Configurar pares de trading
    trading_pairs = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
    trader = MultiPairTrader(trading_pairs, total_budget=1000)
    
    # Parámetros consistentes con el backtester
    backtester_params = {
        'rsi_period': 14,
        'rsi_oversold': 30,
        'rsi_overbought': 70,
        'stop_loss': 0.015,
        'take_profit': 0.03,
        'trailing_stop': 0.012,
        'max_trades_per_day': 4,
        'min_profit_threshold': 0.01
    }
    
    # Ejecutar backtesting primero para validar estrategia
    backtester = Backtester(
        symbol="BTC/USDT",
        start_date=datetime.now() - timedelta(days=30),
        end_date=datetime.now(),
        initial_balance=1000
    )
    
    df = backtester.load_historical_data()
    if df is not None:
        df = backtester.add_indicators(df)
        trades = backtester.run_backtest(df)
        
        # Validar resultados antes de trading en vivo
        if len(trades) > 0:
            print("\nResultados del Backtesting más reciente:")
            # Imprimir resultados directamente desde el backtester
            backtester.print_backtest_results(
                backtester.initial_balance,
                backtester.balance,
                trades
            )
    
    # Iniciar trading en vivo
    daily_trades = {pair: 0 for pair in trading_pairs}
    last_trade_date = datetime.now().date()
    
    while True:
        current_date = datetime.now().date()
        
        # Resetear contadores diarios
        if current_date != last_trade_date:
            daily_trades = {pair: 0 for pair in trading_pairs}
            last_trade_date = current_date
        
        for pair in trading_pairs:
            # Verificar límite diario de operaciones
            if daily_trades[pair] >= backtester_params['max_trades_per_day']:
                continue
                
            data = await get_historical_data(pair, "15m")
            if data is None:
                continue
                
            data = add_technical_indicators(data)
            signals = analyze_signals(data, backtester_params)
            
            if signals['should_trade'] and risk_manager.can_trade():
                position_size = risk_manager.calculate_position_size(
                    signals['entry_price'],
                    signals['stop_loss']
                )
                
                success, order = await execute_trade(pair, position_size, signals, exchange)
                if success:
                    daily_trades[pair] += 1
                    await notifier.send_telegram(
                        f"🔵 Nueva operación en {pair}\n"
                        f"Entrada: ${signals['entry_price']:.2f}\n"
                        f"Stop Loss: ${signals['stop_loss']:.2f}\n"
                        f"Take Profit: ${signals['take_profit']:.2f}\n"
                        f"Score: {signals['score']}\n"
                        f"Posición: {position_size:.4f}"
                    )
        
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main()) 