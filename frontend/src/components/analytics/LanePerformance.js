/**
 * LanePerformance Component
 * =========================
 * Displays Three-Speed Architecture lane analytics (HFT, ALPHA, GAMMA)
 * 
 * Features:
 * - Professional currency formatting via Intl.NumberFormat
 * - Dark mode compatible (uses dark: classes)
 * - Dynamic lane colors with fallback
 * - Loading skeleton state
 * - Responsive grid layout
 * 
 * @author APEX TRADER
 * @date January 2026
 */

import React from 'react';
import { TrendingUp, TrendingDown, Activity, Zap, Target, Sparkles } from 'lucide-react';

// Currency formatter
const formatCurrency = (value) => 
  new Intl.NumberFormat('en-US', { 
    style: 'currency', 
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value || 0);

// Compact currency for large values
const formatCompactCurrency = (value) => {
  if (Math.abs(value) >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1000) {
    return `$${(value / 1000).toFixed(1)}K`;
  }
  return formatCurrency(value);
};

// Lane configuration with colors and icons
const LANE_CONFIG = {
  HFT: {
    label: 'HFT',
    sublabel: 'High Frequency',
    allocation: '35%',
    icon: Zap,
    borderColor: 'border-cyan-500',
    bgColor: 'bg-cyan-500/10',
    textColor: 'text-cyan-400',
    accentColor: 'text-cyan-300',
    glowColor: 'shadow-cyan-500/20',
  },
  ALPHA: {
    label: 'ALPHA',
    sublabel: 'Directional',
    allocation: '55%',
    icon: Target,
    borderColor: 'border-amber-500',
    bgColor: 'bg-amber-500/10',
    textColor: 'text-amber-400',
    accentColor: 'text-amber-300',
    glowColor: 'shadow-amber-500/20',
  },
  GAMMA: {
    label: 'GAMMA',
    sublabel: 'Moonshots',
    allocation: '10%',
    icon: Sparkles,
    borderColor: 'border-purple-500',
    bgColor: 'bg-purple-500/10',
    textColor: 'text-purple-400',
    accentColor: 'text-purple-300',
    glowColor: 'shadow-purple-500/20',
  },
  DEFAULT: {
    label: 'UNKNOWN',
    sublabel: 'Strategy',
    allocation: '0%',
    icon: Activity,
    borderColor: 'border-gray-500',
    bgColor: 'bg-gray-500/10',
    textColor: 'text-gray-400',
    accentColor: 'text-gray-300',
    glowColor: 'shadow-gray-500/20',
  }
};

// Lane order for consistent display
const LANE_ORDER = ['HFT', 'ALPHA', 'GAMMA'];

/**
 * Single Lane Card Component
 */
const LaneCard = ({ laneName, metrics, config }) => {
  const Icon = config.icon;
  const isProfitable = (metrics?.total_pnl || 0) >= 0;
  const pnlColor = isProfitable ? 'text-emerald-400' : 'text-red-400';
  const PnlIcon = isProfitable ? TrendingUp : TrendingDown;
  
  return (
    <div className={`
      relative overflow-hidden rounded-xl 
      border-l-4 ${config.borderColor}
      ${config.bgColor}
      backdrop-blur-sm
      p-4 
      transition-all duration-300
      hover:scale-[1.02] hover:shadow-lg ${config.glowColor}
    `}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-lg ${config.bgColor}`}>
            <Icon className={`w-4 h-4 ${config.textColor}`} />
          </div>
          <div>
            <h3 className={`font-bold text-sm tracking-wide ${config.textColor}`}>
              {config.label}
            </h3>
            <span className="text-[10px] text-white/40 uppercase tracking-wider">
              {config.sublabel} • {config.allocation}
            </span>
          </div>
        </div>
        <span className="text-xs font-mono text-white/50 bg-white/5 px-2 py-0.5 rounded">
          {metrics?.total_trades || 0} trades
        </span>
      </div>
      
      {/* Main PnL */}
      <div className="flex items-end justify-between">
        <div className="flex items-baseline gap-2">
          <PnlIcon className={`w-5 h-5 ${pnlColor}`} />
          <span className={`text-2xl font-bold ${pnlColor}`}>
            {formatCurrency(metrics?.total_pnl || 0)}
          </span>
        </div>
        
        {/* Win Rate Badge */}
        <div className={`
          px-2 py-1 rounded-lg text-right
          ${(metrics?.win_rate || 0) >= 50 ? 'bg-emerald-500/20' : 'bg-red-500/20'}
        `}>
          <span className={`text-lg font-bold ${(metrics?.win_rate || 0) >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
            {(metrics?.win_rate || 0).toFixed(1)}%
          </span>
          <span className="text-[10px] text-white/40 block">Win Rate</span>
        </div>
      </div>
      
      {/* Stats Row */}
      <div className="mt-3 pt-3 border-t border-white/10 grid grid-cols-3 gap-2 text-center">
        <div>
          <span className="text-xs text-white/40 block">Wins</span>
          <span className="text-sm font-semibold text-emerald-400">{metrics?.wins || 0}</span>
        </div>
        <div>
          <span className="text-xs text-white/40 block">Losses</span>
          <span className="text-sm font-semibold text-red-400">{metrics?.losses || 0}</span>
        </div>
        <div>
          <span className="text-xs text-white/40 block">Avg P&L</span>
          <span className={`text-sm font-semibold ${(metrics?.avg_pnl_per_trade || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatCurrency(metrics?.avg_pnl_per_trade || 0)}
          </span>
        </div>
      </div>
      
      {/* Volume Footer */}
      <div className="mt-2 text-center">
        <span className="text-[10px] text-white/30">
          Volume: {formatCompactCurrency(metrics?.total_volume || 0)}
        </span>
      </div>
    </div>
  );
};

/**
 * Loading Skeleton
 */
const LoadingSkeleton = () => (
  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
    {[1, 2, 3].map((i) => (
      <div key={i} className="animate-pulse rounded-xl bg-white/5 border border-white/10 p-4 h-40">
        <div className="h-4 bg-white/10 rounded w-24 mb-3"></div>
        <div className="h-8 bg-white/10 rounded w-32 mb-2"></div>
        <div className="h-4 bg-white/10 rounded w-20"></div>
      </div>
    ))}
  </div>
);

/**
 * Main LanePerformance Component
 */
const LanePerformance = ({ data, isLoading = false, showHeader = true }) => {
  if (isLoading) {
    return <LoadingSkeleton />;
  }
  
  // If no data, show placeholder
  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6 text-center">
        <Activity className="w-8 h-8 text-white/20 mx-auto mb-2" />
        <p className="text-white/40 text-sm">No lane performance data yet</p>
        <p className="text-white/20 text-xs mt-1">Start trading to see HFT/Alpha/Gamma breakdown</p>
      </div>
    );
  }
  
  // Sort lanes in preferred order
  const sortedLanes = LANE_ORDER
    .filter(lane => data[lane])
    .map(lane => [lane, data[lane]]);
  
  // Add any unknown lanes at the end
  Object.keys(data).forEach(lane => {
    if (!LANE_ORDER.includes(lane)) {
      sortedLanes.push([lane, data[lane]]);
    }
  });
  
  // Calculate totals for summary
  const totals = sortedLanes.reduce((acc, [_, metrics]) => ({
    pnl: acc.pnl + (metrics?.total_pnl || 0),
    trades: acc.trades + (metrics?.total_trades || 0),
    volume: acc.volume + (metrics?.total_volume || 0),
  }), { pnl: 0, trades: 0, volume: 0 });
  
  return (
    <div className="space-y-4">
      {/* Header with Summary */}
      {showHeader && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            <span className="text-sm font-medium text-white/80">Lane Performance</span>
            <span className="text-xs text-white/40">(Three-Speed Architecture)</span>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <span className={`font-mono ${totals.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              Total: {formatCurrency(totals.pnl)}
            </span>
            <span className="text-white/40">
              {totals.trades} trades
            </span>
          </div>
        </div>
      )}
      
      {/* Lane Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {sortedLanes.map(([laneName, metrics]) => (
          <LaneCard
            key={laneName}
            laneName={laneName}
            metrics={metrics}
            config={LANE_CONFIG[laneName] || LANE_CONFIG.DEFAULT}
          />
        ))}
      </div>
    </div>
  );
};

export default LanePerformance;
