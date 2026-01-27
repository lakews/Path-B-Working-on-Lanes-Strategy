"""
Zero-Latency Telemetry Service for HFT
======================================

Architecture: Async Queue-Based Telemetry (Non-Blocking Hot Path)

Problem: Traditional logging adds ~5-10ms I/O latency to each trade decision.
Solution: Lock-free queue with background writer thread.

Performance Target:
- log_decision() latency: <0.01ms (just queue.put())
- Background writer handles disk I/O asynchronously
- Zero impact on HFT execution speed

Data Captured:
- High-precision timestamps (nanoseconds)
- Market state at decision time
- AI guidance parameters
- Execution details
- Inventory state

Output: hft_telemetry.csv for post-run analysis (Markout, Adverse Selection)

Author: APEX TRADER HFT Systems Team
Date: January 2026
"""

import os
import csv
import time
import logging
import threading
from queue import SimpleQueue, Empty
from dataclasses import dataclass, asdict
from typing import Dict, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Output directory for telemetry files
TELEMETRY_DIR = "/app/backend/data/telemetry"

# Queue batch size for efficient writes
BATCH_SIZE = 50

# Worker thread poll interval (seconds)
POLL_INTERVAL = 0.1

# Max queue size before warning (not blocking)
MAX_QUEUE_WARNING = 10000


# =============================================================================
# TELEMETRY DATA STRUCTURES
# =============================================================================

@dataclass
class HFTDecisionSnapshot:
    """
    High-resolution snapshot of HFT decision state.
    Captured at the exact moment of quote generation.
    """
    # Timing
    timestamp_ns: int           # Nanosecond precision timestamp
    timestamp_iso: str          # Human-readable ISO timestamp
    
    # Market State
    market_id: str
    market_mid_price: float     # Current mid-price from orderbook
    best_bid: float
    best_ask: float
    spread_bps: float           # Current spread in basis points
    
    # AI Guidance
    fair_value: float           # AI's estimated true price
    fair_value_skew: float      # fair_value - market_mid (positive = undervalued)
    bias: float                 # AI directional bias (-1 to +1)
    ai_confidence: float        # AI confidence level
    context_age_seconds: float  # How old is the AI guidance
    
    # Volatility State
    reference_volatility: float # Volatility at AI analysis time
    current_volatility: float   # Real-time volatility
    vol_multiplier: float       # current / reference (spread adjustment factor)
    
    # Quote Generation
    quoted_bid: float           # Our generated bid price
    quoted_ask: float           # Our generated ask price
    effective_spread_bps: int   # Our spread after vol adjustment
    
    # Position & Inventory
    inventory_value: float      # Current $ value in this market
    inventory_direction: str    # "LONG", "SHORT", "NEUTRAL"
    inventory_skew: float       # % skew from neutral (0 = balanced)
    hft_total_value: float      # Total HFT portfolio value
    
    # Decision Outcome
    decision: str               # "TRADE", "SKIP", "BLOCKED"
    decision_reason: str        # Why this decision was made
    trade_side: str             # "BUY", "SELL", "NONE"
    trade_size: float           # $ size of trade (0 if skipped)
    execution_price: float      # Actual execution price (0 if skipped)
    
    # Performance Metrics (filled post-execution)
    fill_latency_ms: float = 0.0      # Time to fill
    slippage_bps: float = 0.0         # Slippage from quoted price
    markout_1s: float = 0.0           # T+1s price movement (filled later)
    markout_5s: float = 0.0           # T+5s price movement (filled later)


@dataclass
class TelemetryStats:
    """Runtime statistics for the telemetry service."""
    total_logged: int = 0
    total_written: int = 0
    total_dropped: int = 0
    queue_size: int = 0
    avg_write_latency_ms: float = 0.0
    last_write_time: str = ""
    file_size_bytes: int = 0


# =============================================================================
# TELEMETRY SERVICE (SINGLETON)
# =============================================================================

class TelemetryService:
    """
    Zero-latency telemetry service for HFT decision logging.
    
    Uses lock-free SimpleQueue for non-blocking writes.
    Background thread handles all disk I/O asynchronously.
    
    Usage:
        telemetry = get_telemetry_service()
        telemetry.log_decision(snapshot)  # Returns in <0.01ms
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Lock-free queue for zero-latency logging
        self._queue: SimpleQueue = SimpleQueue()
        
        # Background writer thread
        self._writer_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Statistics
        self._stats = TelemetryStats()
        self._stats_lock = threading.Lock()
        
        # File management
        self._current_file: Optional[str] = None
        self._csv_writer = None
        self._file_handle = None
        
        # Ensure output directory exists
        os.makedirs(TELEMETRY_DIR, exist_ok=True)
        
        self._initialized = True
        logger.info("📊 TelemetryService initialized (zero-latency mode)")
    
    # =========================================================================
    # PUBLIC API (NON-BLOCKING)
    # =========================================================================
    
    def log_decision(self, data: Dict) -> None:
        """
        Log an HFT decision snapshot.
        
        NON-BLOCKING: Simply puts data in queue and returns immediately.
        Target latency: <0.01ms
        
        Args:
            data: Dictionary with decision data (will be converted to HFTDecisionSnapshot)
        """
        try:
            # Add high-precision timestamp if not present
            if 'timestamp_ns' not in data:
                data['timestamp_ns'] = time.time_ns()
            if 'timestamp_iso' not in data:
                data['timestamp_iso'] = datetime.now(timezone.utc).isoformat()
            
            # Non-blocking put (never waits)
            self._queue.put(data)
            
            # Update stats (atomic increment)
            with self._stats_lock:
                self._stats.total_logged += 1
                self._stats.queue_size = self._queue.qsize()
                
                # Warn if queue is getting large (shouldn't happen)
                if self._stats.queue_size > MAX_QUEUE_WARNING:
                    logger.warning(f"[TELEMETRY] Queue size {self._stats.queue_size} exceeds warning threshold")
                    
        except Exception as e:
            # Never block or crash the hot path
            logger.debug(f"[TELEMETRY] Log error (ignored): {e}")
    
    def log_snapshot(self, snapshot: HFTDecisionSnapshot) -> None:
        """Log a typed snapshot (converts to dict internally)."""
        self.log_decision(asdict(snapshot))
    
    def start(self) -> None:
        """Start the background writer thread."""
        if self._running:
            return
        
        self._running = True
        self._open_file()
        
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="TelemetryWriter",
            daemon=True
        )
        self._writer_thread.start()
        logger.info(f"📊 Telemetry writer started → {self._current_file}")
    
    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background writer and flush remaining data."""
        if not self._running:
            return
        
        self._running = False
        
        if self._writer_thread:
            self._writer_thread.join(timeout=timeout)
        
        # Flush remaining items
        self._flush_queue()
        self._close_file()
        
        logger.info(f"📊 Telemetry writer stopped. Total logged: {self._stats.total_logged}, written: {self._stats.total_written}")
    
    def get_stats(self) -> Dict:
        """Get current telemetry statistics."""
        with self._stats_lock:
            return {
                "total_logged": self._stats.total_logged,
                "total_written": self._stats.total_written,
                "total_dropped": self._stats.total_dropped,
                "queue_size": self._queue.qsize(),
                "avg_write_latency_ms": self._stats.avg_write_latency_ms,
                "last_write_time": self._stats.last_write_time,
                "current_file": self._current_file,
                "file_size_bytes": self._stats.file_size_bytes,
                "running": self._running,
            }
    
    def get_current_file(self) -> Optional[str]:
        """Get path to current telemetry file."""
        return self._current_file
    
    # =========================================================================
    # BACKGROUND WRITER (ASYNC I/O)
    # =========================================================================
    
    def _writer_loop(self) -> None:
        """Background thread that writes queued data to disk."""
        batch = []
        
        while self._running or not self._queue.empty():
            try:
                # Non-blocking get with timeout
                try:
                    item = self._queue.get(timeout=POLL_INTERVAL)
                    batch.append(item)
                except Empty:
                    pass
                
                # Write batch when full or on timeout
                if len(batch) >= BATCH_SIZE or (batch and self._queue.empty()):
                    self._write_batch(batch)
                    batch = []
                    
            except Exception as e:
                logger.error(f"[TELEMETRY] Writer error: {e}")
                time.sleep(0.1)
        
        # Final flush
        if batch:
            self._write_batch(batch)
    
    def _write_batch(self, batch: List[Dict]) -> None:
        """Write a batch of records to CSV."""
        if not batch or not self._csv_writer:
            return
        
        start_time = time.time()
        
        try:
            for record in batch:
                # Ensure all fields are present
                row = self._normalize_record(record)
                self._csv_writer.writerow(row)
            
            self._file_handle.flush()
            
            # Update stats
            with self._stats_lock:
                self._stats.total_written += len(batch)
                self._stats.last_write_time = datetime.now(timezone.utc).isoformat()
                
                # Update file size
                if self._current_file and os.path.exists(self._current_file):
                    self._stats.file_size_bytes = os.path.getsize(self._current_file)
                
                # Running average of write latency
                write_time_ms = (time.time() - start_time) * 1000
                self._stats.avg_write_latency_ms = (
                    self._stats.avg_write_latency_ms * 0.9 + write_time_ms * 0.1
                )
                
        except Exception as e:
            logger.error(f"[TELEMETRY] Batch write error: {e}")
            with self._stats_lock:
                self._stats.total_dropped += len(batch)
    
    def _flush_queue(self) -> None:
        """Flush all remaining items in queue."""
        batch = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except Empty:
                break
        
        if batch:
            self._write_batch(batch)
    
    # =========================================================================
    # FILE MANAGEMENT
    # =========================================================================
    
    def _open_file(self) -> None:
        """Open a new telemetry file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._current_file = os.path.join(TELEMETRY_DIR, f"hft_telemetry_{timestamp}.csv")
        
        self._file_handle = open(self._current_file, 'w', newline='', buffering=1)
        self._csv_writer = csv.DictWriter(self._file_handle, fieldnames=self._get_fieldnames())
        self._csv_writer.writeheader()
    
    def _close_file(self) -> None:
        """Close the current telemetry file."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
            self._csv_writer = None
    
    def _get_fieldnames(self) -> List[str]:
        """Get CSV column names."""
        return [
            'timestamp_ns', 'timestamp_iso', 'market_id',
            'market_mid_price', 'best_bid', 'best_ask', 'spread_bps',
            'fair_value', 'fair_value_skew', 'bias', 'ai_confidence', 'context_age_seconds',
            'reference_volatility', 'current_volatility', 'vol_multiplier',
            'quoted_bid', 'quoted_ask', 'effective_spread_bps',
            'inventory_value', 'inventory_direction', 'inventory_skew', 'hft_total_value',
            'decision', 'decision_reason', 'trade_side', 'trade_size', 'execution_price',
            'fill_latency_ms', 'slippage_bps', 'markout_1s', 'markout_5s'
        ]
    
    def _normalize_record(self, record: Dict) -> Dict:
        """Ensure record has all required fields."""
        fieldnames = self._get_fieldnames()
        normalized = {}
        for field in fieldnames:
            normalized[field] = record.get(field, '')
        return normalized


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_telemetry_instance: Optional[TelemetryService] = None

def get_telemetry_service() -> TelemetryService:
    """Get the global telemetry service singleton."""
    global _telemetry_instance
    if _telemetry_instance is None:
        _telemetry_instance = TelemetryService()
    return _telemetry_instance


# =============================================================================
# HELPER: CREATE SNAPSHOT FROM HFT DECISION
# =============================================================================

def create_decision_snapshot(
    market_id: str,
    market_data: Dict,
    hft_params: Optional[Dict],
    opportunity: Optional[Dict],
    decision: str,
    reason: str,
    hft_positions: Dict,
) -> Dict:
    """
    Create a telemetry snapshot from HFT decision components.
    
    Called from _evaluate_hft_scalp() to capture decision state.
    """
    # Market state
    best_bid = market_data.get('best_bid', 0)
    best_ask = market_data.get('best_ask', 0)
    mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else market_data.get('yes_price', 0)
    spread = best_ask - best_bid if best_bid and best_ask else 0
    spread_bps = int(spread / mid_price * 10000) if mid_price > 0 else 0
    
    # AI guidance
    fair_value = 0.0
    bias = 0.0
    ai_confidence = 0.0
    context_age = 0.0
    ref_vol = 0.0
    
    if hft_params:
        fair_value = hft_params.get('fair_value', 0.0)
        bias = hft_params.get('bias', 0.0)
        ai_confidence = hft_params.get('confidence', 0.0)
        context_age = hft_params.get('age_seconds', 0.0)
        ref_vol = hft_params.get('reference_volatility', 0.0)
    
    # Opportunity details
    current_vol = opportunity.get('vol_multiplier', 1.0) * ref_vol if opportunity and ref_vol else 0
    vol_multiplier = opportunity.get('vol_multiplier', 1.0) if opportunity else 1.0
    
    quoted_bid = 0.0
    quoted_ask = 0.0
    effective_spread_bps = 0
    trade_side = "NONE"
    trade_size = 0.0
    execution_price = 0.0
    
    if opportunity:
        quoted_bid = opportunity.get('quoted_bid', 0.0)
        quoted_ask = opportunity.get('quoted_ask', 0.0)
        effective_spread_bps = opportunity.get('effective_spread_bps', 0)
        trade_side = opportunity.get('side', 'NONE')
        trade_size = opportunity.get('size', 0.0)
        execution_price = opportunity.get('scalp_price', 0.0)
    
    # Inventory state
    position = hft_positions.get(market_id, {})
    inventory_value = position.get('size', 0.0)
    position_side = position.get('side', '').upper()
    inventory_direction = "LONG" if position_side in ['YES', 'BUY', 'LONG'] else "SHORT" if position_side in ['NO', 'SELL', 'SHORT'] else "NEUTRAL"
    
    # Total HFT value
    hft_total = sum(p.get('size', 0) for p in hft_positions.values())
    inventory_skew = inventory_value / hft_total if hft_total > 0 else 0
    
    return {
        'timestamp_ns': time.time_ns(),
        'timestamp_iso': datetime.now(timezone.utc).isoformat(),
        'market_id': market_id[:32],  # Truncate for CSV
        'market_mid_price': round(mid_price, 6),
        'best_bid': round(best_bid, 6),
        'best_ask': round(best_ask, 6),
        'spread_bps': spread_bps,
        'fair_value': round(fair_value, 6),
        'fair_value_skew': round(fair_value - mid_price, 6),
        'bias': round(bias, 4),
        'ai_confidence': round(ai_confidence, 4),
        'context_age_seconds': round(context_age, 2),
        'reference_volatility': round(ref_vol, 6),
        'current_volatility': round(current_vol, 6),
        'vol_multiplier': round(vol_multiplier, 3),
        'quoted_bid': round(quoted_bid, 6),
        'quoted_ask': round(quoted_ask, 6),
        'effective_spread_bps': effective_spread_bps,
        'inventory_value': round(inventory_value, 2),
        'inventory_direction': inventory_direction,
        'inventory_skew': round(inventory_skew, 4),
        'hft_total_value': round(hft_total, 2),
        'decision': decision,
        'decision_reason': reason,
        'trade_side': trade_side,
        'trade_size': round(trade_size, 2),
        'execution_price': round(execution_price, 6),
    }
