from ta.trend import MACD
from ta.volatility import AverageTrueRange
from ta.momentum import StochasticOscillator

def add_technical_indicators(df):
    """Añade múltiples indicadores técnicos al DataFrame"""
    
    # MACD
    macd = MACD(close=df['close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    
    # ATR
    df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], 
                                close=df['close']).average_true_range()
    
    # Stochastic
    stoch = StochasticOscillator(high=df['high'], low=df['low'], close=df['close'])
    df['Stoch_k'] = stoch.stoch()
    df['Stoch_d'] = stoch.stoch_signal()
    
    return df 