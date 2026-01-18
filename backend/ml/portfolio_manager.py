"""
Portfolio Manager for Continuous Position Sizing

Tracks portfolio state for the new Polymarket Position Sizing Engine:
- Total Equity = Cash + Sum(Position * Current Market Price)
- Deployed Capital = Sum(Position Cost Basis)
- Utilization = Deployed / Equity
- Sector Exposure = Capital allocated to each market category

This is a stateless calculator - it computes values from current positions.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Calculates portfolio state for position sizing decisions.
    
    Key Metrics:
    - equity: Total portfolio value (cash + positions at current market prices)
    - deployed_capital: Sum of cost basis for all open positions
    - utilization: deployed_capital / equity
    - sector_exposure: Dict mapping category -> USD deployed
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.realized_pnl = 0.0
        
    def calculate_portfolio_state(
        self,
        cash_balance: float,
        open_positions: List[Dict],
        current_prices: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        Calculate comprehensive portfolio state.
        
        Args:
            cash_balance: Available cash (initial - deployed + realized)
            open_positions: List of open position dicts with:
                - market_id: Market identifier
                - side: 'YES' or 'NO'
                - size: USD amount invested (cost basis)
                - entry_price: Price at entry
                - category: Market category for sector tracking
                - current_price: Optional current price (if not in current_prices dict)
            current_prices: Optional dict mapping market_id -> current_yes_price
            
        Returns:
            Dict with equity, deployed, utilization, sector_exposure, etc.
        """
        current_prices = current_prices or {}
        
        # Calculate deployed capital (cost basis)
        deployed_capital = sum(p.get('size', 0) for p in open_positions)
        
        # Calculate position values at current market prices
        position_values = []
        unrealized_pnl = 0.0
        
        for pos in open_positions:
            market_id = pos.get('market_id', '')
            size = pos.get('size', 0)
            entry_price = pos.get('entry_price', 0.5)
            side = pos.get('side', 'YES')
            
            # Get current price
            current_price = current_prices.get(market_id, pos.get('current_price', entry_price))
            
            # Calculate current value
            # For YES: shares = size / entry_price, value = shares * current_price
            # For NO: shares = size / (1 - entry_price), value = shares * (1 - current_price)
            if side == 'YES':
                if entry_price > 0:
                    shares = size / entry_price
                    current_value = shares * current_price
                else:
                    current_value = size
            else:  # NO
                no_entry = 1 - entry_price
                if no_entry > 0:
                    shares = size / no_entry
                    current_value = shares * (1 - current_price)
                else:
                    current_value = size
            
            position_values.append({
                'market_id': market_id,
                'cost_basis': size,
                'current_value': current_value,
                'unrealized_pnl': current_value - size
            })
            
            unrealized_pnl += (current_value - size)
        
        # Total Equity = Cash + Sum of Position Values
        total_position_value = sum(p['current_value'] for p in position_values)
        equity = cash_balance + total_position_value
        
        # Utilization = Deployed / Equity
        utilization = deployed_capital / equity if equity > 0 else 0.0
        
        # Sector Exposure
        sector_exposure = self._calculate_sector_exposure(open_positions)
        
        # Calculate sector utilization (for UI display)
        sector_utilization = {}
        for sector, exposure in sector_exposure.items():
            sector_utilization[sector] = exposure / equity if equity > 0 else 0.0
        
        return {
            'equity': equity,
            'cash_balance': cash_balance,
            'deployed_capital': deployed_capital,
            'utilization': utilization,
            'unrealized_pnl': unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'total_pnl': self.realized_pnl + unrealized_pnl,
            'position_count': len(open_positions),
            'sector_exposure': sector_exposure,
            'sector_utilization': sector_utilization,
            'position_values': position_values,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _calculate_sector_exposure(self, open_positions: List[Dict]) -> Dict[str, float]:
        """
        Calculate USD exposure per market category.
        
        Returns:
            Dict mapping category -> USD deployed in that category
        """
        exposure = {}
        
        for pos in open_positions:
            category = pos.get('category', pos.get('asset_class', 'unknown'))
            if category:
                category = category.lower()
            else:
                category = 'unknown'
            
            size = pos.get('size', 0)
            exposure[category] = exposure.get(category, 0) + size
        
        return exposure
    
    def get_available_sector_capacity(
        self,
        equity: float,
        sector_exposure: Dict[str, float],
        sector_caps: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate remaining capacity for each sector.
        
        Args:
            equity: Total portfolio equity
            sector_exposure: Current exposure by sector
            sector_caps: Maximum allocation percentages by sector
            
        Returns:
            Dict mapping sector -> remaining USD capacity
        """
        capacity = {}
        
        for sector, cap_pct in sector_caps.items():
            max_allocation = equity * cap_pct
            current_exposure = sector_exposure.get(sector, 0)
            remaining = max(0, max_allocation - current_exposure)
            capacity[sector] = remaining
        
        return capacity
    
    def update_realized_pnl(self, pnl: float):
        """Add to realized P&L from closed trade."""
        self.realized_pnl += pnl
    
    def reset(self, initial_capital: float = None):
        """Reset portfolio manager for new session."""
        if initial_capital is not None:
            self.initial_capital = initial_capital
        self.realized_pnl = 0.0


def create_position_context(
    position: Dict,
    category: str = None,
    tags: List[str] = None
) -> Dict:
    """
    Create position context dict for correlation checking.
    
    Args:
        position: Position dict from paper_positions
        category: Market category
        tags: Market tags
        
    Returns:
        Dict suitable for correlation dampener
    """
    return {
        'market_id': position.get('market_id', ''),
        'category': category or position.get('category', position.get('asset_class', 'unknown')),
        'tags': tags or position.get('tags', []),
        'side': position.get('side', 'YES'),
        'size': position.get('size', 0),
    }
