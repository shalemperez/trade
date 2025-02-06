import asyncio
import time
from datetime import datetime, timedelta
from ta.trend import MACD
from ta.volatility import AverageTrueRange
from ta.momentum import StochasticOscillator

async def main():
    # Inicializar componentes
    risk_manager = RiskManager(initial_capital=1000)
    notifier = NotificationSystem(
        telegram_token="YOUR_TOKEN",
        telegram_chat_id="YOUR_CHAT_ID"
    )
    
    # Configurar pares de trading
    trading_pairs = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    trader = MultiPairTrader(trading_pairs, total_budget=1000)
    
    # Ejecutar backtesting primero
    backtester = Backtester(
        symbol="BTCUSDT",
        start_date=datetime.now() - timedelta(days=30),
        end_date=datetime.now()
    )
    
    # Iniciar trading en vivo
    while True:
        for pair in trading_pairs:
            data = get_historical_data(pair, "15m")
            data = add_technical_indicators(data)
            
            signals = analyze_signals(data)
            if signals['should_trade'] and risk_manager.can_trade(daily_pnl):
                position_size = risk_manager.calculate_position_size(
                    signals['entry_price'],
                    signals['stop_loss']
                )
                
                # Ejecutar trade
                if execute_trade(pair, position_size, signals):
                    await notifier.send_telegram(
                        f"Nueva operación en {pair}\n"
                        f"Entrada: {signals['entry_price']}\n"
                        f"Stop Loss: {signals['stop_loss']}"
                    )
        
        time.sleep(60)

if __name__ == "__main__":
    asyncio.run(main()) 