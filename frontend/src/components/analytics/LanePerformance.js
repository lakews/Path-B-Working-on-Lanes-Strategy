/**
 * LanePerformance Component - Compact Horizontal Cards
 * =====================================================
 * Displays Five-Lane Architecture analytics with unique visual design
 * 
 * @author APEX TRADER
 * @date February 2026
 */

import React from 'react';
import { Activity, Zap, Target, Sparkles, Newspaper, Trophy, TrendingUp, TrendingDown, RotateCcw } from 'lucide-react';

// Currency formatter - compact
const formatCurrency = (value) => {
  const absValue = Math.abs(value || 0);
  if (absValue >= 1000000) return `${value >= 0 ? '+' : '-'}$${(absValue / 1000000).toFixed(1)}M`;
  if (absValue >= 1000) return `${value >= 0 ? '+' : '-'}$${(absValue / 1000).toFixed(2)}K`;
  return `${value >= 0 ? '+' : ''}$${(value || 0).toFixed(2)}`;
};

// Lane configuration
const LANES = [
  { key: 'HFT', label: 'HFT', icon: Zap, color: 'cyan', bg: 'from-cyan-500/20 to-cyan-600/5', border: 'border-cyan-500/40', text: 'text-cyan-400', alloc: 35 },
  { key: 'ALPHA', label: 'ALPHA', icon: Target, color: 'amber', bg: 'from-amber-500/20 to-amber-600/5', border: 'border-amber-500/40', text: 'text-amber-400', alloc: 40 },
  { key: 'GAMMA', label: 'GAMMA', icon: Sparkles, color: 'purple', bg: 'from-purple-500/20 to-purple-600/5', border: 'border-purple-500/40', text: 'text-purple-400', alloc: 10 },
  { key: 'SPORTS', label: 'SPORTS', icon: Trophy, color: 'pink', bg: 'from-pink-500/20 to-pink-600/5', border: 'border-pink-500/40', text: 'text-pink-400', alloc: 10 },
  { key: 'NEWS', label: 'NEWS', icon: Newspaper, color: 'orange', bg: 'from-orange-500/20 to-orange-600/5', border: 'border-orange-500/40', text: 'text-orange-400', alloc: 5 },
];

/**
 * Compact Lane Chip Component
 */
const LaneChip = ({ lane, metrics }) => {
  const Icon = lane.icon;
  const pnl = metrics?.total_pnl || 0;
  const isProfitable = pnl >= 0;
  const winRate = metrics?.win_rate || 0;
  const trades = metrics?.total_trades || 0;
  const wins = metrics?.wins || 0;
  const losses = metrics?.losses || 0;
  const hasTrades = trades > 0;
  
  return (
    <div 
      className={`
        relative flex items-center gap-3 px-3 py-2 rounded-xl
        bg-gradient-to-r ${lane.bg}
        border ${lane.border}
        ${!hasTrades ? 'opacity-40' : ''}
        transition-all duration-200 hover:scale-[1.02]
      `}
      data-testid={`lane-chip-${lane.key.toLowerCase()}`}
    >
      {/* Icon */}
      <div className={`p-1.5 rounded-lg bg-black/20`}>
        <Icon className={`w-4 h-4 ${lane.text}`} />
      </div>
      
      {/* Lane Name & Allocation */}
      <div className="min-w-[60px]">
        <div className={`text-xs font-bold ${lane.text}`}>{lane.label}</div>
        <div className="text-[9px] text-white/30">{lane.alloc}%</div>
      </div>
      
      {/* Divider */}
      <div className="w-px h-8 bg-white/10"></div>
      
      {/* P&L */}
      <div className="min-w-[80px] text-right">
        <div className="flex items-center justify-end gap-1">
          {hasTrades && (isProfitable ? 
            <TrendingUp className="w-3 h-3 text-emerald-400" /> : 
            <TrendingDown className="w-3 h-3 text-red-400" />
          )}
          <span className={`text-sm font-bold tabular-nums ${
            !hasTrades ? 'text-white/30' : isProfitable ? 'text-emerald-400' : 'text-red-400'
          }`}>
            {hasTrades ? formatCurrency(pnl) : '$0.00'}
          </span>
        </div>
        <div className="text-[9px] text-white/30">P&L</div>
      </div>
      
      {/* Win Rate */}
      <div className="min-w-[45px] text-center">
        <div className={`text-sm font-semibold tabular-nums ${
          !hasTrades ? 'text-white/30' : winRate >= 50 ? 'text-emerald-400' : winRate > 0 ? 'text-amber-400' : 'text-red-400'
        }`}>
          {hasTrades ? `${winRate.toFixed(0)}%` : '-'}
        </div>
        <div className="text-[9px] text-white/30">Win</div>
      </div>
      
      {/* W/L */}
      <div className="min-w-[55px] text-center">
        <div className="flex items-center justify-center gap-0.5 text-xs">
          <span className="text-emerald-400 font-medium">{wins}</span>
          <span className="text-white/20">/</span>
          <span className="text-red-400 font-medium">{losses}</span>
        </div>
        <div className="text-[9px] text-white/30">{trades} trades</div>
      </div>
    </div>
  );
};

/**
 * Main LanePerformance Component
 */
const LanePerformance = ({ data, isLoading = false, onReset }) => {
  // Calculate totals
  const totals = LANES.reduce((acc, lane) => {
    const metrics = data?.[lane.key] || {};
    return {
      pnl: acc.pnl + (metrics.total_pnl || 0),
      trades: acc.trades + (metrics.total_trades || 0),
      wins: acc.wins + (metrics.wins || 0),
      losses: acc.losses + (metrics.losses || 0),
    };
  }, { pnl: 0, trades: 0, wins: 0, losses: 0 });
  
  const totalWinRate = totals.trades > 0 ? (totals.wins / totals.trades) * 100 : 0;
  const activeLanes = LANES.filter(lane => (data?.[lane.key]?.total_trades || 0) > 0).length;
  
  if (isLoading) {
    return (
      <div className="rounded-xl bg-white/[0.02] border border-white/[0.06] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-white/10 rounded w-40"></div>
          <div className="flex gap-2">
            {[1,2,3,4,5].map(i => <div key={i} className="h-16 bg-white/5 rounded-xl flex-1"></div>)}
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div 
      className="rounded-xl bg-gradient-to-br from-slate-900/60 to-slate-800/30 border border-white/[0.08] overflow-hidden"
      data-testid="lane-performance"
    >
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between border-b border-white/[0.06]">
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded-lg bg-gradient-to-br from-cyan-500/20 to-purple-500/20">
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-white">5-Lane Architecture</span>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                {activeLanes}/5 ACTIVE
              </span>
            </div>
            <span className="text-[10px] text-white/40">HFT • Alpha • Gamma • Sports • News</span>
          </div>
        </div>
        
        {/* Summary + Reset */}
        <div className="flex items-center gap-3">
          {/* Quick Stats */}
          <div className="flex items-center gap-4 px-3 py-1.5 rounded-lg bg-black/20 border border-white/[0.06]">
            <div className="text-center">
              <div className={`text-sm font-bold ${totals.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {formatCurrency(totals.pnl)}
              </div>
              <div className="text-[9px] text-white/30">Total P&L</div>
            </div>
            <div className="w-px h-6 bg-white/10"></div>
            <div className="text-center">
              <div className={`text-sm font-bold ${totalWinRate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {totalWinRate.toFixed(1)}%
              </div>
              <div className="text-[9px] text-white/30">Win Rate</div>
            </div>
            <div className="w-px h-6 bg-white/10"></div>
            <div className="text-center">
              <div className="text-sm font-bold text-white">{totals.trades}</div>
              <div className="text-[9px] text-white/30">Trades</div>
            </div>
          </div>
          
          {/* Reset Button */}
          {onReset && (
            <button
              onClick={onReset}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] hover:border-white/[0.15] text-white/60 hover:text-white transition-all duration-200"
              data-testid="reset-lane-stats"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span className="text-xs font-medium">Reset</span>
            </button>
          )}
        </div>
      </div>
      
      {/* Lane Chips - Horizontal Scrollable */}
      <div className="p-3">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {LANES.map(lane => (
            <LaneChip
              key={lane.key}
              lane={lane}
              metrics={data?.[lane.key]}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default LanePerformance;
