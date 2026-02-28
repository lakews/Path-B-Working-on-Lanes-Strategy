"""
RISK MANAGER SERVICE
====================

The centralized enforcer for the 5-Lane Trading Architecture.
Loads configuration from the SSOT (risk_config.json) and validates all orders.

Features:
- Hot-reloading: update_config() without restart
- Order validation: check_order() before execution
- Audit logging: All blocks/trims are logged as WARNINGs
"""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

logger = logging.getLogger(__name__)

# Path to the SSOT config file
CONFIG_PATH = Path(__file__).parent.parent / "config" / "risk_config.json"


@dataclass
class OrderCheckResult:
    """Result of a risk check on an order"""
    approved: bool
    adjusted_amount: float
    original_amount: float
    reason: str
    lane: str
    warnings: list
    
    def to_dict(self) -> Dict:
        return {
            'approved': self.approved,
            'adjusted_amount': self.adjusted_amount,
            'original_amount': self.original_amount,
            'reason': self.reason,
            'lane': self.lane,
            'warnings': self.warnings
        }


class RiskManager:
    """
    Centralized Risk Management Service.
    
    The single enforcer for all risk parameters across all 5 lanes.
    Configuration is loaded from risk_config.json (SSOT).
    
    Usage:
        risk_manager = get_risk_manager()
        result = risk_manager.check_order('HFT', 100.0, capital=10000)
        if result.approved:
            execute_order(result.adjusted_amount)
    """
    
    def __init__(self):
        self._config: Dict = {}
        self._lock = Lock()
        self._last_loaded: Optional[datetime] = None
        self._load_config()
    
    def _load_config(self) -> bool:
        """Load configuration from the SSOT JSON file"""
        try:
            if not CONFIG_PATH.exists():
                logger.error(f"[RISK MANAGER] Config file not found: {CONFIG_PATH}")
                return False
            
            with open(CONFIG_PATH, 'r') as f:
                self._config = json.load(f)
            
            self._last_loaded = datetime.now(timezone.utc)
            logger.info(f"[RISK MANAGER] Config loaded from {CONFIG_PATH}")
            logger.info(f"[RISK MANAGER] Version: {self._config.get('_metadata', {}).get('version', 'unknown')}")
            
            # Log key parameters
            global_cfg = self._config.get('global', {})
            logger.info(f"[RISK MANAGER] Global: max_drawdown={global_cfg.get('max_drawdown_pct', 0)*100:.0f}%, "
                       f"max_deployment={global_cfg.get('max_deployment_pct', 0)*100:.0f}%")
            
            for lane_name, lane_cfg in self._config.get('lanes', {}).items():
                logger.info(f"[RISK MANAGER] {lane_name}: alloc={lane_cfg.get('alloc_pct', 0)*100:.0f}%, "
                           f"max_pos=${lane_cfg.get('max_pos_usd', 0):.0f}, "
                           f"max_pos_pct={lane_cfg.get('max_pos_pct', 0)*100:.1f}%")
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"[RISK MANAGER] Invalid JSON in config: {e}")
            return False
        except Exception as e:
            logger.error(f"[RISK MANAGER] Error loading config: {e}")
            return False
    
    def reload_config(self) -> Tuple[bool, str]:
        """
        Hot-reload configuration from disk.
        
        Returns:
            (success: bool, message: str)
        """
        with self._lock:
            old_version = self._config.get('_metadata', {}).get('version', 'unknown')
            
            if self._load_config():
                new_version = self._config.get('_metadata', {}).get('version', 'unknown')
                msg = f"Config reloaded: v{old_version} → v{new_version}"
                logger.info(f"[RISK MANAGER] {msg}")
                return True, msg
            else:
                return False, "Failed to reload config"
    
    def update_config(self, new_config: Dict) -> Tuple[bool, str]:
        """
        Update configuration and save to disk.
        
        Args:
            new_config: New configuration dict (will be merged with existing)
            
        Returns:
            (success: bool, message: str)
        """
        with self._lock:
            try:
                # Merge new config with existing
                merged = self._deep_merge(self._config.copy(), new_config)
                
                # Update metadata
                if '_metadata' not in merged:
                    merged['_metadata'] = {}
                merged['_metadata']['last_updated'] = datetime.now(timezone.utc).isoformat()
                
                # Validate before saving
                validation_result = self._validate_config(merged)
                if not validation_result[0]:
                    return validation_result
                
                # Save to disk
                with open(CONFIG_PATH, 'w') as f:
                    json.dump(merged, f, indent=2)
                
                # Reload
                self._config = merged
                self._last_loaded = datetime.now(timezone.utc)
                
                logger.info("[RISK MANAGER] Config updated and saved to disk")
                return True, "Configuration updated successfully"
                
            except Exception as e:
                logger.error(f"[RISK MANAGER] Error updating config: {e}")
                return False, f"Error updating config: {str(e)}"
    
    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _validate_config(self, config: Dict) -> Tuple[bool, str]:
        """Validate configuration structure and values"""
        try:
            # Check required sections
            required_sections = ['global', 'lanes', 'kelly', 'exit_strategies']
            for section in required_sections:
                if section not in config:
                    return False, f"Missing required section: {section}"
            
            # Validate global limits
            global_cfg = config.get('global', {})
            if global_cfg.get('max_drawdown_pct', 0) > 0.20:
                return False, "max_drawdown_pct cannot exceed 20%"
            if global_cfg.get('max_deployment_pct', 0) > 1.0:
                return False, "max_deployment_pct cannot exceed 100%"
            
            # Validate lane allocations sum (excluding overlays)
            lanes = config.get('lanes', {})
            core_alloc = sum(
                lane.get('alloc_pct', 0) 
                for lane in lanes.values() 
                if not lane.get('is_overlay', False)
            )
            if core_alloc > 1.0:
                return False, f"Core lane allocations sum to {core_alloc*100:.0f}% (max 100%)"
            
            return True, "Validation passed"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def get_config(self) -> Dict:
        """Get the current configuration (read-only copy)"""
        with self._lock:
            return self._config.copy()
    
    def get_lane_config(self, lane: str) -> Dict:
        """Get configuration for a specific lane"""
        with self._lock:
            return self._config.get('lanes', {}).get(lane.upper(), {}).copy()
    
    def get_global_config(self) -> Dict:
        """Get global configuration"""
        with self._lock:
            return self._config.get('global', {}).copy()
    
    def get_kelly_config(self) -> Dict:
        """Get Kelly sizing configuration"""
        with self._lock:
            return self._config.get('kelly', {}).copy()
    
    def get_exit_config(self, strategy: str) -> Dict:
        """Get exit configuration for a specific strategy"""
        with self._lock:
            return self._config.get('exit_strategies', {}).get(strategy, {}).copy()
    
    def get_asset_modifier(self, asset_class: str) -> Dict:
        """Get asset modifier for a specific asset class"""
        with self._lock:
            modifiers = self._config.get('asset_modifiers', {})
            return modifiers.get(asset_class.lower(), modifiers.get('default', {})).copy()
    
    def get_sector_cap(self, sector: str) -> float:
        """Get sector cap for a specific sector"""
        with self._lock:
            caps = self._config.get('sector_caps', {})
            return caps.get(sector.lower(), caps.get('unknown', 0.15))
    
    def check_order(
        self,
        lane: str,
        amount: float,
        capital: float,
        current_utilization: float = 0.0,
        sector: Optional[str] = None,
        sector_exposure: float = 0.0,
        market_price: float = 0.5
    ) -> OrderCheckResult:
        """
        Check if an order is allowed under current risk limits.
        
        Args:
            lane: Lane name (HFT, ALPHA, GAMMA, SPORTS, NEWS)
            amount: Proposed order amount in USD
            capital: Total deployed capital
            current_utilization: Current capital utilization (0-1)
            sector: Market sector (for sector cap check)
            sector_exposure: Current exposure to this sector
            market_price: Current market price (for zone detection)
            
        Returns:
            OrderCheckResult with approval status and adjusted amount
        """
        warnings = []
        lane_upper = lane.upper()
        
        with self._lock:
            # Get configurations
            global_cfg = self._config.get('global', {})
            lane_cfg = self._config.get('lanes', {}).get(lane_upper, {})
            
            if not lane_cfg:
                return OrderCheckResult(
                    approved=False,
                    adjusted_amount=0.0,
                    original_amount=amount,
                    reason=f"Unknown lane: {lane}",
                    lane=lane_upper,
                    warnings=warnings
                )
            
            adjusted_amount = amount
            
            # ========================================
            # CHECK 1: Global Utilization
            # ========================================
            max_deployment = global_cfg.get('max_deployment_pct', 0.80)
            if current_utilization >= max_deployment:
                logger.warning(f"[RISK MANAGER] BLOCKED: Utilization {current_utilization*100:.1f}% >= max {max_deployment*100:.0f}%")
                return OrderCheckResult(
                    approved=False,
                    adjusted_amount=0.0,
                    original_amount=amount,
                    reason=f"Max deployment reached ({current_utilization*100:.0f}%)",
                    lane=lane_upper,
                    warnings=warnings
                )
            
            # ========================================
            # CHECK 2: Lane Allocation
            # ========================================
            lane_alloc = lane_cfg.get('alloc_pct', 0)
            # NOTE: lane_capital calculation reserved for future lane-specific allocation checks
            # lane_capital = capital * lane_alloc
            # For overlay lanes (SPORTS, NEWS), they draw from the main pool
            _ = lane_alloc  # Acknowledge for future use
            
            # ========================================
            # CHECK 3: Max Position USD
            # ========================================
            max_pos_usd = lane_cfg.get('max_pos_usd', 100.0)
            if adjusted_amount > max_pos_usd:
                logger.warning(f"[RISK MANAGER] TRIMMED: ${amount:.2f} → ${max_pos_usd:.2f} (max_pos_usd for {lane_upper})")
                warnings.append(f"Trimmed to max_pos_usd: ${max_pos_usd:.0f}")
                adjusted_amount = max_pos_usd
            
            # ========================================
            # CHECK 4: Max Position % of Capital
            # ========================================
            max_pos_pct = lane_cfg.get('max_pos_pct', 0.03)
            max_by_pct = capital * max_pos_pct
            if adjusted_amount > max_by_pct:
                logger.warning(f"[RISK MANAGER] TRIMMED: ${adjusted_amount:.2f} → ${max_by_pct:.2f} (max_pos_pct {max_pos_pct*100:.1f}% for {lane_upper})")
                warnings.append(f"Trimmed to {max_pos_pct*100:.1f}% of capital: ${max_by_pct:.0f}")
                adjusted_amount = max_by_pct
            
            # ========================================
            # CHECK 5: Sector Cap (if sector provided)
            # ========================================
            if sector:
                sector_cap = self._config.get('sector_caps', {}).get(sector.lower(), 0.15)
                max_sector_exposure = capital * sector_cap
                if sector_exposure + adjusted_amount > max_sector_exposure:
                    allowed = max(0, max_sector_exposure - sector_exposure)
                    if allowed < global_cfg.get('min_trade_amount', 2.0):
                        logger.warning(f"[RISK MANAGER] BLOCKED: Sector cap reached for {sector} ({sector_cap*100:.0f}%)")
                        return OrderCheckResult(
                            approved=False,
                            adjusted_amount=0.0,
                            original_amount=amount,
                            reason=f"Sector cap reached: {sector} ({sector_cap*100:.0f}%)",
                            lane=lane_upper,
                            warnings=warnings
                        )
                    logger.warning(f"[RISK MANAGER] TRIMMED: ${adjusted_amount:.2f} → ${allowed:.2f} (sector cap for {sector})")
                    warnings.append(f"Trimmed for sector cap: ${allowed:.0f}")
                    adjusted_amount = allowed
            
            # ========================================
            # CHECK 6: Minimum Trade Amount
            # ========================================
            min_amount = global_cfg.get('min_trade_amount', 2.0)
            if adjusted_amount < min_amount:
                logger.warning(f"[RISK MANAGER] BLOCKED: ${adjusted_amount:.2f} < min ${min_amount:.2f}")
                return OrderCheckResult(
                    approved=False,
                    adjusted_amount=0.0,
                    original_amount=amount,
                    reason=f"Below minimum trade amount: ${min_amount:.0f}",
                    lane=lane_upper,
                    warnings=warnings
                )
            
            # ========================================
            # CHECK 7: Zone-specific limits (for GAMMA)
            # ========================================
            if lane_upper == 'GAMMA':
                whale_ceiling = lane_cfg.get('whale_price_ceiling', 0.10)
                if market_price >= whale_ceiling:
                    logger.warning(f"[RISK MANAGER] BLOCKED: GAMMA only for prices < ${whale_ceiling}")
                    return OrderCheckResult(
                        approved=False,
                        adjusted_amount=0.0,
                        original_amount=amount,
                        reason=f"GAMMA requires price < ${whale_ceiling}",
                        lane=lane_upper,
                        warnings=warnings
                    )
            
            # ========================================
            # APPROVED
            # ========================================
            if adjusted_amount < amount:
                reason = f"Approved (trimmed from ${amount:.2f})"
            else:
                reason = "Approved"
            
            return OrderCheckResult(
                approved=True,
                adjusted_amount=adjusted_amount,
                original_amount=amount,
                reason=reason,
                lane=lane_upper,
                warnings=warnings
            )
    
    def get_status(self) -> Dict:
        """Get current risk manager status"""
        with self._lock:
            return {
                'config_loaded': self._last_loaded is not None,
                'last_loaded': self._last_loaded.isoformat() if self._last_loaded else None,
                'version': self._config.get('_metadata', {}).get('version', 'unknown'),
                'config_path': str(CONFIG_PATH),
                'lanes': list(self._config.get('lanes', {}).keys()),
                'global_max_drawdown': self._config.get('global', {}).get('max_drawdown_pct', 0),
                'global_max_deployment': self._config.get('global', {}).get('max_deployment_pct', 0),
            }


# Singleton instance
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """Get or create the RiskManager singleton"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


def reload_risk_config() -> Tuple[bool, str]:
    """Convenience function to reload the risk config"""
    return get_risk_manager().reload_config()
