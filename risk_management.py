class RiskManager:
    def __init__(self, initial_capital, max_risk_per_trade=0.015, max_daily_risk=0.05):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_risk = max_daily_risk
        self.daily_losses = 0
        self.open_positions = {}
        
    def can_trade(self):
        """Verifica si es seguro realizar una nueva operación"""
        # Verificar pérdida diaria máxima
        if self.daily_losses >= (self.initial_capital * self.max_daily_risk):
            return False
            
        # Verificar capital mínimo
        if self.current_capital < (self.initial_capital * 0.5):  # 50% del capital inicial
            return False
            
        return True
    
    def calculate_position_size(self, entry_price, stop_loss_price):
        """Calcula el tamaño de la posición basado en el riesgo"""
        if not entry_price or not stop_loss_price or entry_price <= stop_loss_price:
            return 0
            
        # Calcular riesgo monetario máximo para esta operación
        risk_amount = self.current_capital * self.max_risk_per_trade
        
        # Calcular el tamaño de la posición
        price_risk = abs(entry_price - stop_loss_price)
        position_size = risk_amount / price_risk
        
        # Limitar el tamaño máximo de la posición
        max_position_size = self.current_capital * 0.8 / entry_price
        position_size = min(position_size, max_position_size)
        
        return position_size
    
    def update_capital(self, pnl):
        """Actualiza el capital después de una operación"""
        self.current_capital += pnl
        if pnl < 0:
            self.daily_losses += abs(pnl)
    
    def reset_daily_stats(self):
        """Resetea las estadísticas diarias"""
        self.daily_losses = 0
    
    def add_position(self, symbol, size, entry_price):
        """Registra una nueva posición"""
        self.open_positions[symbol] = {
            'size': size,
            'entry_price': entry_price
        }
    
    def remove_position(self, symbol):
        """Elimina una posición cerrada"""
        if symbol in self.open_positions:
            del self.open_positions[symbol]
    
    def get_total_exposure(self):
        """Calcula la exposición total actual"""
        return sum(pos['size'] * pos['entry_price'] for pos in self.open_positions.values()) 