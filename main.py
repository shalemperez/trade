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
import signal
import sys

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
        order = exchange.create_order(
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

def get_historical_data(symbol, timeframe):
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
        
        # Obtener datos (método síncrono)
        ohlcv = exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            limit=100
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

class GracefulExit(SystemExit):
    pass

def signal_handler(signum, frame):
    raise GracefulExit()

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    print(f"\nRecibida señal de terminación {signal.name}...")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    
    print(f"Cancelando {len(tasks)} tareas pendientes")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    try:
        with open('config.yaml', 'r') as file:
            config = yaml.safe_load(file)
        
        # Inicializar exchange
        exchange = ccxt.binance({
            'apiKey': config['binance']['api_key'],
            'secret': config['binance']['api_secret'],
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
                'createMarketBuyOrderRequiresPrice': False
            }
        })
        
        # Verificar conexión con el exchange
        try:
            exchange.load_markets()
            print("Conexión exitosa con Binance")
        except Exception as e:
            print(f"Error conectando con Binance: {e}")
            return

        # Inicializar componentes
        risk_manager = RiskManager(
            initial_capital=config['trading']['initial_capital'],
            max_risk_per_trade=config['trading']['risk_per_trade'],
            max_daily_risk=config['trading']['daily_loss_limit']
        )
        
        notifier = NotificationSystem(
            telegram_token=config['telegram']['token'],
            telegram_chat_id=config['telegram']['chat_id']
        )
        
        # Enviar mensaje de inicio
        await notifier.send_telegram("🚀 Bot de trading iniciado")
        
        # Configurar pares de trading desde config.yaml
        trading_pairs = config['trading']['pairs']
        trader = MultiPairTrader(trading_pairs, total_budget=config['trading']['initial_capital'])
        
        print(f"Monitoreando pares: {trading_pairs}")
        
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
        
        # Variables para tracking
        trades = []
        total_profit = 0
        win_rate = 0
        daily_trades = {pair: 0 for pair in trading_pairs}
        last_trade_date = datetime.now().date()
        
        while True:
            try:
                current_date = datetime.now().date()
                
                for pair in trading_pairs:
                    try:
                        # Obtener precio actual
                        ticker = exchange.fetch_ticker(pair)
                        current_price = ticker['last']
                        print(f"Precio actual de {pair}: ${current_price:.2f}")
                        
                        if daily_trades[pair] >= backtester_params['max_trades_per_day']:
                            print(f"Límite diario alcanzado para {pair}")
                            continue
                        
                        data = get_historical_data(pair, "15m")
                        if data is None:
                            continue
                        
                        data = add_technical_indicators(data)
                        signals = analyze_signals(data, backtester_params)
                        
                        print(f"Análisis de {pair}:")
                        print(f"Score: {signals['score']}")
                        print(f"Should trade: {signals['should_trade']}")
                        
                        if signals['should_trade'] and risk_manager.can_trade():
                            print(f"¡Señal de trading detectada para {pair}!")
                            
                            position_size = risk_manager.calculate_position_size(
                                signals['entry_price'],
                                signals['stop_loss']
                            )
                            
                            print(f"Intentando ejecutar orden de compra:")
                            print(f"Tamaño: {position_size}")
                            print(f"Precio entrada: {signals['entry_price']}")
                            print(f"Stop loss: {signals['stop_loss']}")
                            print(f"Take profit: {signals['take_profit']}")
                            
                            success, order = await execute_trade(
                                pair, 
                                position_size, 
                                signals, 
                                exchange
                            )
                            
                            if success:
                                print(f"¡Orden ejecutada exitosamente!")
                                daily_trades[pair] += 1
                                trades.append(order)
                                
                                await notifier.send_trade_notification(
                                    "BUY",
                                    pair,
                                    signals['entry_price'],
                                    position_size,
                                    signals['stop_loss'],
                                    signals['take_profit']
                                )
                            else:
                                print(f"Error ejecutando la orden")
                        
                    except Exception as e:
                        error_msg = f"Error procesando {pair}: {str(e)}"
                        print(error_msg)
                        await notifier.send_error(error_msg)
                        continue
                
                print("\nEsperando 60 segundos antes del próximo ciclo...")
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                error_msg = f"Error en el ciclo principal: {str(e)}"
                print(error_msg)
                if 'notifier' in locals():
                    await notifier.send_error(error_msg)
                await asyncio.sleep(60)
    
    finally:
        # Cleanup
        print("\nGuardando estado y cerrando conexiones...")
        if 'notifier' in locals():
            await notifier.send_telegram("⚠️ Bot de trading finalizando...")
            await notifier.close()

if __name__ == "__main__":
    try:
        signal.signal(signal.SIGINT, signal_handler)
        asyncio.run(main())
    except GracefulExit:
        print("\nPrograma terminado correctamente")
    except Exception as e:
        print(f"\nError inesperado: {e}")
    finally:
        print("\n¡Hasta luego! 👋")
        sys.exit(0) 