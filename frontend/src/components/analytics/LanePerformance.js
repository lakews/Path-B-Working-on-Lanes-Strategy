/**
 * LanePerformance Component - Premium Design
 * ==========================================
 * Displays Five-Lane Architecture analytics (HFT, ALPHA, GAMMA, SPORTS, NEWS)
 * 
 * Features:
 * - Premium glass-morphism card design
 * - Consistent 5-card grid layout
 * - Professional currency formatting
 * - Animated hover states with glow effects
 * - Responsive design for all screen sizes
 * 
 * @author APEX TRADER
 * @date February 2026
 */

import React from 'react';
import { TrendingUp, TrendingDown, Activity, Zap, Target, Sparkles, Newspaper, Trophy } from 'lucide-react';

// Currency formatter
const formatCurrency = (value) => {
  const absValue = Math.abs(value || 0);
  if (absValue >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  }
  if (absValue >= 1000) {
    return `$${(value / 1000).toFixed(2)}K`;
  }
  return new Intl.NumberFormat('en-US', { 
    style: 'currency', 
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value || 0);
};

// Compact volume formatter
const formatVolume = (value) => {
  if (!value) return '$0';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

// Lane configuration with premium colors (5-Lane Architecture)
const LANE_CONFIG = {
  HFT: {
    label: 'HFT',
    sublabel: 'HIGH FREQUENCY',
    allocation: '35%',
    icon: Zap,
    gradient: 'from-cyan-600/20 via-cyan-500/10 to-transparent',
    borderGradient: 'from-cyan-400 to-cyan-600',
    iconBg: 'bg-cyan-500/20',
    iconColor: 'text-cyan-400',
    textColor: 'text-cyan-400',
    glowColor: 'hover:shadow-cyan-500/30',
    ringColor: 'ring-cyan-500/30',
  },
  ALPHA: {
    label: 'ALPHA',
    sublabel: 'DIRECTIONAL',
    allocation: '40%',
    icon: Target,
    gradient: 'from-amber-600/20 via-amber-500/10 to-transparent',
    borderGradient: 'from-amber-400 to-amber-600',
    iconBg: 'bg-amber-500/20',
    iconColor: 'text-amber-400',
    textColor: 'text-amber-400',
    glowColor: 'hover:shadow-amber-500/30',
    ringColor: 'ring-amber-500/30',
  },
  GAMMA: {
    label: 'GAMMA',
    sublabel: 'MOONSHOTS',
    allocation: '10%',
    icon: Sparkles,
    gradient: 'from-purple-600/20 via-purple-500/10 to-transparent',
    borderGradient: 'from-purple-400 to-purple-600',
    iconBg: 'bg-purple-500/20',
    iconColor: 'text-purple-400',
    textColor: 'text-purple-400',
    glowColor: 'hover:shadow-purple-500/30',
    ringColor: 'ring-purple-500/30',
  },
  SPORTS: {
    label: 'SPORTS',
    sublabel: 'ARBITRAGE',
    allocation: '10%',
    icon: Trophy,
    gradient: 'from-pink-600/20 via-pink-500/10 to-transparent',
    borderGradient: 'from-pink-400 to-pink-600',
    iconBg: 'bg-pink-500/20',
    iconColor: 'text-pink-400',
    textColor: 'text-pink-400',
    glowColor: 'hover:shadow-pink-500/30',
    ringColor: 'ring-pink-500/30',
  },
  NEWS: {
    label: 'NEWS',
    sublabel: 'EVENT DRIVEN',
    allocation: '5%',
    icon: Newspaper,
    gradient: 'from-orange-600/20 via-orange-500/10 to-transparent',
    borderGradient: 'from-orange-400 to-orange-600',
    iconBg: 'bg-orange-500/20',
    iconColor: 'text-orange-400',
    textColor: 'text-orange-400',
    glowColor: 'hover:shadow-orange-500/30',
    ringColor: 'ring-orange-500/30',
  },
};

// Lane order for consistent display (5-Lane Architecture)
const LANE_ORDER = ['HFT', 'ALPHA', 'GAMMA', 'SPORTS', 'NEWS'];

/**
 * Premium Lane Card Component
 */
const LaneCard = ({ laneName, metrics, config }) => {
  const Icon = config.icon;
  const pnl = metrics?.total_pnl || 0;
  const isProfitable = pnl >= 0;
  const winRate = metrics?.win_rate || 0;
  const trades = metrics?.total_trades || 0;
  const wins = metrics?.wins || 0;
  const losses = metrics?.losses || 0;
  const avgPnl = metrics?.avg_pnl_per_trade || 0;
  const volume = metrics?.total_volume || 0;
  
  return (
    <div 
      className={`
        relative group overflow-hidden rounded-2xl 
        bg-gradient-to-br ${config.gradient}
        backdrop-blur-xl
        border border-white/[0.08]
        transition-all duration-500 ease-out
        hover:scale-[1.02] hover:shadow-2xl ${config.glowColor}
        hover:border-white/20
      `}
      data-testid={`lane-card-${laneName.toLowerCase()}`}
    >
      {/* Gradient Border Effect */}
      <div className={`absolute inset-0 rounded-2xl bg-gradient-to-br ${config.borderGradient} opacity-0 group-hover:opacity-10 transition-opacity duration-500`} />
      
      {/* Top Accent Line */}
      <div className={`absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r ${config.borderGradient} opacity-60`} />
      
      {/* Content */}
      <div className="relative p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`
              p-2.5 rounded-xl ${config.iconBg} 
              ring-1 ${config.ringColor}
              transition-transform duration-300 group-hover:scale-110
            `}>
              <Icon className={`w-5 h-5 ${config.iconColor}`} />
            </div>
            <div>
              <h3 className={`font-black text-base tracking-wide ${config.textColor}`}>
                {config.label}
              </h3>
              <span className="text-[10px] text-white/40 font-medium tracking-widest">
                {config.sublabel} • {config.allocation}
              </span>
            </div>
          </div>
          
          {/* Trade Count Badge */}
          <div className="bg-white/[0.06] backdrop-blur-sm px-2.5 py-1 rounded-lg border border-white/[0.08]">
            <span className="text-xs font-bold text-white/70">{trades}</span>
            <span className="text-[10px] text-white/40 ml-1">trades</span>
          </div>
        </div>
        
        {/* Main P&L Display */}
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-1">
            {isProfitable ? (
              <TrendingUp className="w-5 h-5 text-emerald-400" />
            ) : (
              <TrendingDown className="w-5 h-5 text-red-400" />
            )}
            <span className={`text-2xl font-black tracking-tight ${isProfitable ? 'text-emerald-400' : 'text-red-400'}`}>
              {isProfitable && pnl > 0 ? '+' : ''}{formatCurrency(pnl)}
            </span>
          </div>
        </div>
        
        {/* Win Rate Badge - Prominent */}
        <div className={`
          mb-4 p-3 rounded-xl 
          ${winRate >= 50 ? 'bg-emerald-500/10 border border-emerald-500/20' : 'bg-red-500/10 border border-red-500/20'}
        `}>
          <div className="flex items-center justify-between">
            <span className="text-xs text-white/50 font-medium">Win Rate</span>
            <span className={`text-xl font-black ${winRate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
              {winRate.toFixed(1)}%
            </span>
          </div>
        </div>
        
        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          <div className="bg-white/[0.04] rounded-lg p-2 text-center">
            <span className="text-[10px] text-white/40 block mb-0.5">Wins</span>
            <span className="text-sm font-bold text-emerald-400">{wins}</span>
          </div>
          <div className="bg-white/[0.04] rounded-lg p-2 text-center">
            <span className="text-[10px] text-white/40 block mb-0.5">Losses</span>
            <span className="text-sm font-bold text-red-400">{losses}</span>
          </div>
          <div className="bg-white/[0.04] rounded-lg p-2 text-center">
            <span className="text-[10px] text-white/40 block mb-0.5">Avg P&L</span>
            <span className={`text-sm font-bold ${avgPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatCurrency(avgPnl)}
            </span>
          </div>
        </div>
        
        {/* Volume Footer */}
        <div className="pt-2 border-t border-white/[0.06] text-center">
          <span className="text-[10px] text-white/30 font-medium">
            Volume: {formatVolume(volume)}
          </span>
        </div>
      </div>
    </div>
  );
};

/**
 * Empty Lane Card (for inactive lanes)
 */
const EmptyLaneCard = ({ laneName, config }) => {
  const Icon = config.icon;
  
  return (
    <div 
      className={`
        relative overflow-hidden rounded-2xl 
        bg-white/[0.02]
        border border-white/[0.06] border-dashed
        transition-all duration-300
        hover:bg-white/[0.04] hover:border-white/[0.1]
      `}
      data-testid={`lane-card-${laneName.toLowerCase()}-empty`}
    >
      {/* Content */}
      <div className="relative p-4 opacity-40">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl bg-white/[0.05]`}>
              <Icon className="w-5 h-5 text-white/30" />
            </div>
            <div>
              <h3 className="font-black text-base tracking-wide text-white/50">
                {config.label}
              </h3>
              <span className="text-[10px] text-white/30 font-medium tracking-widest">
                {config.sublabel} • {config.allocation}
              </span>
            </div>
          </div>
          <div className="bg-white/[0.04] px-2.5 py-1 rounded-lg">
            <span className="text-xs text-white/30">0 trades</span>
          </div>
        </div>
        
        {/* Placeholder */}
        <div className="text-center py-6">
          <span className="text-xs text-white/20">No trades yet</span>
        </div>
      </div>
    </div>
  );
};

/**
 * Loading Skeleton
 */
const LoadingSkeleton = () => (
  <div className="space-y-4">
    <div className="flex items-center justify-between">
      <div className="h-5 bg-white/10 rounded w-40 animate-pulse"></div>
      <div className="h-4 bg-white/10 rounded w-32 animate-pulse"></div>
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="animate-pulse rounded-2xl bg-white/[0.03] border border-white/[0.06] p-4 h-64">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-white/10 rounded-xl"></div>
            <div>
              <div className="h-4 bg-white/10 rounded w-16 mb-1"></div>
              <div className="h-2 bg-white/10 rounded w-24"></div>
            </div>
          </div>
          <div className="h-8 bg-white/10 rounded w-28 mb-4"></div>
          <div className="h-16 bg-white/10 rounded mb-3"></div>
          <div className="grid grid-cols-3 gap-2">
            <div className="h-12 bg-white/10 rounded"></div>
            <div className="h-12 bg-white/10 rounded"></div>
            <div className="h-12 bg-white/10 rounded"></div>
          </div>
        </div>
      ))}
    </div>
  </div>
);

/**
 * Main LanePerformance Component
 */
const LanePerformance = ({ data, isLoading = false, showHeader = true }) => {
  if (isLoading) {
    return <LoadingSkeleton />;
  }
  
  // Calculate totals
  const totals = LANE_ORDER.reduce((acc, lane) => {
    const metrics = data?.[lane] || {};
    return {
      pnl: acc.pnl + (metrics.total_pnl || 0),
      trades: acc.trades + (metrics.total_trades || 0),
      volume: acc.volume + (metrics.total_volume || 0),
    };
  }, { pnl: 0, trades: 0, volume: 0 });
  
  return (
    <div className="space-y-4" data-testid="lane-performance">
      {/* Header with Summary */}
      {showHeader && (
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-gradient-to-br from-cyan-500/20 to-purple-500/20 border border-white/[0.08]">
              <Activity className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Lane Performance</h2>
              <span className="text-xs text-white/40">(5-Lane Architecture)</span>
            </div>
          </div>
          
          <div className="flex items-center gap-6 bg-white/[0.03] rounded-xl px-4 py-2 border border-white/[0.06]">
            <div className="text-right">
              <span className="text-[10px] text-white/40 block">Total P&L</span>
              <span className={`text-lg font-black ${totals.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {totals.pnl >= 0 ? '+' : ''}{formatCurrency(totals.pnl)}
              </span>
            </div>
            <div className="w-px h-8 bg-white/10"></div>
            <div className="text-right">
              <span className="text-[10px] text-white/40 block">Total Trades</span>
              <span className="text-lg font-bold text-white">{totals.trades}</span>
            </div>
          </div>
        </div>
      )}
      
      {/* Lane Cards Grid - Always 5 columns on large screens */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {LANE_ORDER.map((laneName) => {
          const config = LANE_CONFIG[laneName];
          const metrics = data?.[laneName];
          const hasTrades = metrics && (metrics.total_trades > 0 || metrics.total_pnl !== 0);
          
          return hasTrades ? (
            <LaneCard
              key={laneName}
              laneName={laneName}
              metrics={metrics}
              config={config}
            />
          ) : (
            <EmptyLaneCard
              key={laneName}
              laneName={laneName}
              config={config}
            />
          );
        })}
      </div>
    </div>
  );
};

export default LanePerformance;
