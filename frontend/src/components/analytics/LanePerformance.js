/**
 * LanePerformance Component - Compact Table Design
 * =================================================
 * Displays Five-Lane Architecture analytics (HFT, ALPHA, GAMMA, SPORTS, NEWS)
 * in a compact, space-efficient table format
 * 
 * @author APEX TRADER
 * @date February 2026
 */

import React from 'react';
import { Activity, Zap, Target, Sparkles, Newspaper, Trophy, TrendingUp, TrendingDown } from 'lucide-react';

// Currency formatter - compact
const formatCurrency = (value) => {
  const absValue = Math.abs(value || 0);
  if (absValue >= 1000000) return `${value >= 0 ? '+' : '-'}$${(absValue / 1000000).toFixed(1)}M`;
  if (absValue >= 1000) return `${value >= 0 ? '+' : '-'}$${(absValue / 1000).toFixed(2)}K`;
  return `${value >= 0 ? '+' : ''}$${(value || 0).toFixed(2)}`;
};

// Volume formatter
const formatVolume = (value) => {
  if (!value) return '$0';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

// Lane configuration (5-Lane Architecture)
const LANE_CONFIG = {
  HFT: { label: 'HFT', icon: Zap, color: 'cyan', alloc: '35%' },
  ALPHA: { label: 'Alpha', icon: Target, color: 'amber', alloc: '40%' },
  GAMMA: { label: 'Gamma', icon: Sparkles, color: 'purple', alloc: '10%' },
  SPORTS: { label: 'Sports', icon: Trophy, color: 'pink', alloc: '10%' },
  NEWS: { label: 'News', icon: Newspaper, color: 'orange', alloc: '5%' },
};

const LANE_ORDER = ['HFT', 'ALPHA', 'GAMMA', 'SPORTS', 'NEWS'];

// Color classes mapping
const getColorClasses = (color) => ({
  icon: `text-${color}-400`,
  bg: `bg-${color}-500/20`,
  border: `border-${color}-500/30`,
  ring: `ring-${color}-500/20`,
});

/**
 * Compact Lane Row Component
 */
const LaneRow = ({ laneName, metrics, config, isLast }) => {
  const Icon = config.icon;
  const colors = getColorClasses(config.color);
  const pnl = metrics?.total_pnl || 0;
  const isProfitable = pnl >= 0;
  const winRate = metrics?.win_rate || 0;
  const trades = metrics?.total_trades || 0;
  const wins = metrics?.wins || 0;
  const losses = metrics?.losses || 0;
  const avgPnl = metrics?.avg_pnl_per_trade || 0;
  const volume = metrics?.total_volume || 0;
  const hasTrades = trades > 0;
  
  return (
    <tr 
      className={`${!isLast ? 'border-b border-white/[0.06]' : ''} ${!hasTrades ? 'opacity-40' : ''} hover:bg-white/[0.02] transition-colors`}
      data-testid={`lane-row-${laneName.toLowerCase()}`}
    >
      {/* Lane Name */}
      <td className="py-2.5 px-3">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-lg ${colors.bg}`}>
            <Icon className={`w-3.5 h-3.5 ${colors.icon}`} />
          </div>
          <div>
            <span className={`text-sm font-bold ${colors.icon}`}>{config.label}</span>
            <span className="text-[10px] text-white/30 ml-1.5">{config.alloc}</span>
          </div>
        </div>
      </td>
      
      {/* P&L */}
      <td className="py-2.5 px-3 text-right">
        <div className="flex items-center justify-end gap-1">
          {hasTrades && (isProfitable ? 
            <TrendingUp className="w-3 h-3 text-emerald-400" /> : 
            <TrendingDown className="w-3 h-3 text-red-400" />
          )}
          <span className={`text-sm font-bold tabular-nums ${
            !hasTrades ? 'text-white/30' : isProfitable ? 'text-emerald-400' : 'text-red-400'
          }`}>
            {hasTrades ? formatCurrency(pnl) : '-'}
          </span>
        </div>
      </td>
      
      {/* Win Rate */}
      <td className="py-2.5 px-3 text-center">
        <span className={`text-sm font-semibold tabular-nums ${
          !hasTrades ? 'text-white/30' : winRate >= 50 ? 'text-emerald-400' : 'text-red-400'
        }`}>
          {hasTrades ? `${winRate.toFixed(1)}%` : '-'}
        </span>
      </td>
      
      {/* Trades (W/L) */}
      <td className="py-2.5 px-3 text-center">
        {hasTrades ? (
          <div className="flex items-center justify-center gap-1 text-xs">
            <span className="text-emerald-400 font-medium">{wins}</span>
            <span className="text-white/30">/</span>
            <span className="text-red-400 font-medium">{losses}</span>
            <span className="text-white/20 ml-1">({trades})</span>
          </div>
        ) : (
          <span className="text-white/30 text-sm">-</span>
        )}
      </td>
      
      {/* Avg P&L */}
      <td className="py-2.5 px-3 text-right hidden sm:table-cell">
        <span className={`text-xs font-medium tabular-nums ${
          !hasTrades ? 'text-white/30' : avgPnl >= 0 ? 'text-emerald-400/80' : 'text-red-400/80'
        }`}>
          {hasTrades ? formatCurrency(avgPnl) : '-'}
        </span>
      </td>
      
      {/* Volume */}
      <td className="py-2.5 px-3 text-right hidden md:table-cell">
        <span className="text-xs text-white/40 tabular-nums">
          {hasTrades ? formatVolume(volume) : '-'}
        </span>
      </td>
    </tr>
  );
};

/**
 * Main LanePerformance Component - Compact Table
 */
const LanePerformance = ({ data, isLoading = false }) => {
  // Calculate totals
  const totals = LANE_ORDER.reduce((acc, lane) => {
    const metrics = data?.[lane] || {};
    return {
      pnl: acc.pnl + (metrics.total_pnl || 0),
      trades: acc.trades + (metrics.total_trades || 0),
      wins: acc.wins + (metrics.wins || 0),
      losses: acc.losses + (metrics.losses || 0),
      volume: acc.volume + (metrics.total_volume || 0),
    };
  }, { pnl: 0, trades: 0, wins: 0, losses: 0, volume: 0 });
  
  const totalWinRate = totals.trades > 0 ? (totals.wins / totals.trades) * 100 : 0;
  
  if (isLoading) {
    return (
      <div className="rounded-xl bg-white/[0.02] border border-white/[0.06] p-4">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-white/10 rounded w-40"></div>
          <div className="h-32 bg-white/5 rounded"></div>
        </div>
      </div>
    );
  }
  
  return (
    <div 
      className="rounded-xl bg-gradient-to-br from-slate-900/40 to-slate-800/20 border border-white/[0.06] overflow-hidden"
      data-testid="lane-performance"
    >
      {/* Compact Header */}
      <div className="px-4 py-2.5 flex items-center justify-between border-b border-white/[0.06] bg-white/[0.02]">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <span className="text-sm font-semibold text-white">Lane Performance</span>
          <span className="text-[10px] text-white/30">(5-Lane)</span>
        </div>
        
        {/* Summary Stats */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-white/40">P&L:</span>
            <span className={`text-sm font-bold ${totals.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatCurrency(totals.pnl)}
            </span>
          </div>
          <div className="w-px h-4 bg-white/10"></div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-white/40">Trades:</span>
            <span className="text-sm font-bold text-white">{totals.trades}</span>
          </div>
        </div>
      </div>
      
      {/* Compact Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-[10px] text-white/40 uppercase tracking-wider border-b border-white/[0.04]">
              <th className="py-2 px-3 text-left font-medium">Lane</th>
              <th className="py-2 px-3 text-right font-medium">P&L</th>
              <th className="py-2 px-3 text-center font-medium">Win%</th>
              <th className="py-2 px-3 text-center font-medium">W/L</th>
              <th className="py-2 px-3 text-right font-medium hidden sm:table-cell">Avg</th>
              <th className="py-2 px-3 text-right font-medium hidden md:table-cell">Volume</th>
            </tr>
          </thead>
          <tbody>
            {LANE_ORDER.map((laneName, idx) => (
              <LaneRow
                key={laneName}
                laneName={laneName}
                metrics={data?.[laneName]}
                config={LANE_CONFIG[laneName]}
                isLast={idx === LANE_ORDER.length - 1}
              />
            ))}
          </tbody>
          {/* Totals Row */}
          <tfoot>
            <tr className="border-t border-white/[0.08] bg-white/[0.02]">
              <td className="py-2 px-3">
                <span className="text-xs font-bold text-white/60">TOTAL</span>
              </td>
              <td className="py-2 px-3 text-right">
                <span className={`text-sm font-bold ${totals.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatCurrency(totals.pnl)}
                </span>
              </td>
              <td className="py-2 px-3 text-center">
                <span className={`text-sm font-semibold ${totalWinRate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {totalWinRate.toFixed(1)}%
                </span>
              </td>
              <td className="py-2 px-3 text-center">
                <div className="flex items-center justify-center gap-1 text-xs">
                  <span className="text-emerald-400 font-medium">{totals.wins}</span>
                  <span className="text-white/30">/</span>
                  <span className="text-red-400 font-medium">{totals.losses}</span>
                </div>
              </td>
              <td className="py-2 px-3 text-right hidden sm:table-cell">
                <span className={`text-xs font-medium ${
                  totals.trades > 0 && (totals.pnl / totals.trades) >= 0 ? 'text-emerald-400/80' : 'text-red-400/80'
                }`}>
                  {totals.trades > 0 ? formatCurrency(totals.pnl / totals.trades) : '-'}
                </span>
              </td>
              <td className="py-2 px-3 text-right hidden md:table-cell">
                <span className="text-xs text-white/40">{formatVolume(totals.volume)}</span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
};

export default LanePerformance;
