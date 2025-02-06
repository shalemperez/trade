class RiskManager:
    def __init__(self, initial_capital):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_drawdown = 0
        self.trades_history = []
        self.max_position_size = 0.02  # 2% del capital por operación
        self.daily_loss_limit = 0.05   # 5% pérdida diaria máxima
        
    def calculate_position_size(self, price, stop_loss):
        risk_per_trade = self.current_capital * self.max_position_size
        stop_loss_points = abs(price - stop_loss)
        position_size = risk_per_trade / stop_loss_points
        return position_size
    
    def can_trade(self, daily_pnl):
        if abs(daily_pnl) > self.current_capital * self.daily_loss_limit:
            return False
        return True
    
    def update_metrics(self, trade_result):
        self.current_capital += trade_result
        drawdown = (self.initial_capital - self.current_capital) / self.initial_capital
        self.max_drawdown = max(self.max_drawdown, drawdown)
        self.trades_history.append(trade_result) 