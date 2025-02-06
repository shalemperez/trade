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
import ccxt.async_support as ccxt
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

async def get_historical_data(exchange, symbol, timeframe):
    """Obtiene datos históricos de Binance de forma asíncrona"""
    try:
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                ohlcv = await exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=100
                )
                
                if not ohlcv:
                    print(f"No se obtuvieron datos para {symbol}")
                    return None
                    
                df = pd.DataFrame(
                    ohlcv,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                
                if df.empty:
                    print(f"DataFrame vacío para {symbol}")
                    return None
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df
                
            except ccxt.RateLimitExceeded:
                if attempt < max_retries - 1:
                    print(f"Rate limit alcanzado, reintentando en {retry_delay} segundos...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
            except Exception as e:
                print(f"Error en intento {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise
                    
    except Exception as e:
        print(f"Error obteniendo datos históricos para {symbol}: {str(e)}")
        return None

def add_technical_indicators(df):
    """Añade indicadores técnicos al DataFrame"""
    df['RSI'] = RSIIndicator(close=df['close'], window=14).rsi()
    df['SMA_20'] = SMAIndicator(close=df['close'], window=20).sma_indicator()
    df['SMA_50'] = SMAIndicator(close=df['close'], window=50).sma_indicator()
    
    bollinger = BollingerBands(close=df['close'], window=20)
    df['BB_upper'] = bollinger.bollinger_hband()
    df['BB_middle'] = bollinger.bollinger_mavg()
    df['BB_lower'] = bollinger.bollinger_lband()
    
    macd = MACD(close=df['close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    
    df['volume_ma20'] = df['volume'].rolling(window=20).mean()
    df['volatility'] = df['close'].pct_change().rolling(window=20).std()
    df['momentum'] = df['close'].pct_change(periods=10)
    df['trend'] = np.where(df['SMA_20'] > df['SMA_50'], 1, -1)
    
    return df

def analyze_signals(data, backtester_params):
    """Analiza señales de trading"""
    current_row = data.iloc[-1]
    prev_row = data.iloc[-2]
    
    score = 0
    signals_info = []
    
    # Análisis técnico
    if current_row['trend'] == 1:
        score += 1.5
        signals_info.append("Tendencia alcista: +1.5")
        if current_row['close'] > current_row['SMA_20']:
            score += 1
            signals_info.append("Precio sobre SMA20: +1")
    
    if 30 <= current_row['RSI'] <= 70:
        score += 1
        signals_info.append("RSI en rango saludable: +1")
    elif current_row['RSI'] < 30:
        score += 2
        signals_info.append("RSI en sobreventa: +2")
    
    if current_row['momentum'] > 0:
        score += 1
        signals_info.append("Momentum positivo: +1")
    
    if current_row['volume'] > current_row['volume_ma20'] * 1.2:
        score += 1.5
        signals_info.append("Volumen alto: +1.5")
    
    if 0.001 < current_row['volatility'] < 0.05:
        score += 1
        signals_info.append("Volatilidad favorable: +1")
    
    if current_row['close'] < current_row['BB_lower'] * 1.02:
        score += 2
        signals_info.append("Precio cerca del soporte: +2")
    
    if prev_row['SMA_20'] <= prev_row['SMA_50'] and current_row['SMA_20'] > current_row['SMA_50']:
        score += 1.5
        signals_info.append("Cruce alcista de medias: +1.5")
    
    should_trade = score >= 5
    
    print("\nAnálisis detallado de señales:")
    for signal in signals_info:
        print(f"• {signal}")
    print(f"Score total: {score:.1f}")
    
    return {
        'should_trade': should_trade,
        'entry_price': current_row['close'],
        'stop_loss': current_row['close'] * (1 - backtester_params['stop_loss']),
        'take_profit': current_row['close'] * (1 + backtester_params['take_profit']),
        'score': score,
        'signals': signals_info
    }

async def execute_trade(pair, position_size, signals, exchange):
    """Ejecuta operaciones de trading"""
    try:
        # Verificar balance
        balance = await exchange.fetch_balance()
        quote_currency = pair.split('/')[-1]  # BTCUSDT -> USDT
        
        if quote_currency not in balance or 'free' not in balance[quote_currency]:
            print(f"No se pudo obtener el balance de {quote_currency}")
            return False, None
            
        available_balance = float(balance[quote_currency]['free'])
        required_amount = position_size * signals['entry_price']
        
        # Formatear números para mejor legibilidad
        formatted_required = f"{required_amount:.2f}"
        formatted_available = f"{available_balance:.2f}"
        
        print("\nVerificación de balance:")
        print(f"Balance disponible en {quote_currency}: ${formatted_available}")
        print(f"Cantidad requerida: ${formatted_required}")
        
        if required_amount > available_balance:
            print(f"\n❌ Balance insuficiente:")
            print(f"• Necesario: ${formatted_required} {quote_currency}")
            print(f"• Disponible: ${formatted_available} {quote_currency}")
            print(f"• Faltante: ${(required_amount - available_balance):.2f} {quote_currency}")
            return False, None
            
        # Obtener información del mercado
        markets = exchange.markets
        if pair not in markets:
            print(f"Par {pair} no encontrado en el mercado")
            return False, None
            
        market = markets[pair]
        
        # Obtener precisión del mercado
        amount_precision = market['precision']['amount'] if 'amount' in market['precision'] else 8
        price_precision = market['precision']['price'] if 'price' in market['precision'] else 8
        
        # Aplicar límites del mercado
        min_amount = float(market['limits']['amount']['min']) if 'amount' in market['limits'] else 0
        if position_size < min_amount:
            print(f"\n❌ Tamaño de posición muy pequeño:")
            print(f"• Tamaño calculado: {position_size}")
            print(f"• Mínimo permitido: {min_amount}")
            return False, None
        
        # Redondear cantidades
        position_size = round(position_size, amount_precision)
        stop_loss_price = round(signals['stop_loss'], price_precision)
        take_profit_price = round(signals['take_profit'], price_precision)
        
        print(f"\n📊 Detalles de la orden:")
        print(f"• Par: {pair}")
        print(f"• Tamaño: {position_size}")
        print(f"• Precio estimado: ${signals['entry_price']:.2f}")
        print(f"• Stop loss: ${stop_loss_price:.2f}")
        print(f"• Take profit: ${take_profit_price:.2f}")
        
        try:
            # Crear orden de mercado
            order = await exchange.create_order(
                symbol=pair,
                type='market',
                side='buy',
                amount=position_size
            )
            
            print("Orden de mercado creada:", order['id'])
            
            # Esperar a que se llene la orden
            filled = False
            max_wait = 10  # segundos máximos de espera
            start_time = time.time()
            
            while not filled and time.time() - start_time < max_wait:
                try:
                    filled_order = await exchange.fetch_order(order['id'], pair)
                    if filled_order['status'] == 'closed':
                        filled = True
                        break
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"Error verificando orden: {e}")
                    await asyncio.sleep(1)
            
            if not filled:
                print("Tiempo de espera agotado para la orden principal")
                return False, None
            
            # Crear órdenes OCO (One-Cancels-the-Other) si está disponible
            try:
                oco_order = await exchange.create_order(
                    symbol=pair,
                    type='oco',
                    side='sell',
                    amount=position_size,
                    price=take_profit_price,
                    stopPrice=stop_loss_price,
                    stopLimitPrice=stop_loss_price
                )
                print("Orden OCO creada exitosamente")
                return True, {
                    'main_order': order,
                    'oco_order': oco_order
                }
            except Exception as e:
                print(f"Error creando orden OCO, intentando crear órdenes separadas: {e}")
                
                # Crear órdenes separadas si OCO falla
                stop_loss_order = await exchange.create_order(
                    symbol=pair,
                    type='stop_loss_limit',
                    side='sell',
                    amount=position_size,
                    price=stop_loss_price,
                    params={
                        'stopPrice': stop_loss_price
                    }
                )
                
                take_profit_order = await exchange.create_order(
                    symbol=pair,
                    type='limit',
                    side='sell',
                    amount=position_size,
                    price=take_profit_price
                )
                
                print("Órdenes creadas exitosamente:")
                print(f"Orden principal: {order['id']}")
                print(f"Stop Loss: {stop_loss_order['id']}")
                print(f"Take Profit: {take_profit_order['id']}")
                
                return True, {
                    'main_order': order,
                    'stop_loss': stop_loss_order,
                    'take_profit': take_profit_order
                }
                
        except Exception as e:
            print(f"Error creando órdenes: {str(e)}")
            return False, None
            
    except Exception as e:
        print(f"Error al ejecutar trade: {str(e)}")
        return False, None

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
    exchange = None
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
                'createMarketBuyOrderRequiresPrice': False,
                'warnOnFetchOHLCVLimitArgument': False,
                'recvWindow': 60000
            }
        })
        
        # Cargar mercados
        await exchange.load_markets()
        print("Conexión exitosa con Binance")
        
        # Verificar balance inicial
        balance = await exchange.fetch_balance()
        print("\n💰 Balance inicial:")
        for currency in ['USDT', 'BTC', 'ETH', 'BNB']:
            if currency in balance and 'free' in balance[currency]:
                free_amount = float(balance[currency]['free'])
                used_amount = float(balance[currency]['used'])
                total_amount = float(balance[currency]['total'])
                print(f"• {currency}:")
                print(f"  - Disponible: {free_amount:.8f}")
                print(f"  - En uso: {used_amount:.8f}")
                print(f"  - Total: {total_amount:.8f}")
        
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
        
        await notifier.send_telegram("🚀 Bot de trading iniciado")
        
        trading_pairs = config['trading']['pairs']
        trader = MultiPairTrader(trading_pairs, config['trading']['initial_capital'])
        
        print(f"Monitoreando pares: {trading_pairs}")
        
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
        
        trades = []
        daily_trades = {pair: 0 for pair in trading_pairs}
        
        while True:
            for pair in trading_pairs:
                try:
                    ticker = await exchange.fetch_ticker(pair)
                    if not ticker or 'last' not in ticker:
                        print(f"Datos de ticker inválidos para {pair}")
                        continue
                        
                    current_price = ticker['last']
                    print(f"Precio actual de {pair}: ${current_price:.2f}")
                    
                    if daily_trades[pair] >= backtester_params['max_trades_per_day']:
                        print(f"Límite diario alcanzado para {pair}")
                        continue
                    
                    data = await get_historical_data(exchange, pair, "15m")
                    if data is None:
                        continue
                    
                    data = add_technical_indicators(data)
                    signals = analyze_signals(data, backtester_params)
                    
                    if signals['should_trade'] and risk_manager.can_trade():
                        print(f"¡Señal de trading detectada para {pair}!")
                        
                        position_size = risk_manager.calculate_position_size(
                            signals['entry_price'],
                            signals['stop_loss']
                        )
                        
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
                    
                except Exception as e:
                    error_msg = f"Error procesando {pair}: {str(e)}"
                    print(error_msg)
                    await notifier.send_error(error_msg)
                    continue
            
            print("\nEsperando 60 segundos antes del próximo ciclo...")
            await asyncio.sleep(60)
            
    except Exception as e:
        print(f"Error en el ciclo principal: {str(e)}")
        if 'notifier' in locals():
            await notifier.send_error(str(e))
    
    finally:
        print("\nCerrando conexiones...")
        if 'notifier' in locals():
            await notifier.send_telegram("⚠️ Bot de trading finalizando...")
            await notifier.close()
        if exchange:
            await exchange.close()

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