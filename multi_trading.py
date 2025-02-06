class MultiPairTrader:
    def __init__(self, trading_pairs, total_budget):
        self.trading_pairs = trading_pairs
        self.budget_per_pair = total_budget / len(trading_pairs)
        self.active_trades = {}
        self.pair_metrics = {}
        
    def initialize_pairs(self):
        for pair in self.trading_pairs:
            self.pair_metrics[pair] = {
                'success_rate': 0,
                'avg_profit': 0,
                'total_trades': 0,
                'active_position': None
            }
    
    def allocate_budget(self):
        """Asignación dinámica de presupuesto basada en rendimiento"""
        total_success = sum(m['success_rate'] for m in self.pair_metrics.values())
        
        for pair in self.trading_pairs:
            if total_success > 0:
                performance_weight = self.pair_metrics[pair]['success_rate'] / total_success
                self.pair_metrics[pair]['current_budget'] = (
                    self.budget_per_pair * (0.5 + 0.5 * performance_weight)
                )
            else:
                self.pair_metrics[pair]['current_budget'] = self.budget_per_pair 