import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { 
  Play, Square, TrendingUp, TrendingDown, Activity, DollarSign, Target, 
  BarChart3, Clock, Zap, Shield, Award, Percent, ChevronRight, Database,
  RefreshCw, AlertTriangle, CheckCircle, XCircle, History, Brain, Download,
  Layers, Settings, Sparkles, Crosshair, Scale, Timer, Wallet, ArrowUpRight,
  ArrowDownRight, Eye, FileText, PieChart, LineChart as LineChartIcon,
  Wifi, WifiOff, RotateCcw, List
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar, Cell, PieChart as RePieChart, Pie, Legend } from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Helper function to format duration in seconds to human readable string
const formatDuration = (seconds) => {
  if (!seconds || seconds <= 0) return '-';
  
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  
  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
};

// Basic Auth credentials for protected endpoints
const AUTH_CONFIG = {
  auth: {
    username: 'admin',
    password: 'apex2026!'
  }
};

const STRATEGY_INFO = {
  delta_neutral: { name: 'Delta-Neutral', color: '#06b6d4', icon: Scale },
  volatility_exploitation: { name: 'Volatility', color: '#8b5cf6', icon: Zap },
  alpha_directional: { name: 'Alpha', color: '#f59e0b', icon: Target },
  arbitrage: { name: 'Arbitrage', color: '#10b981', icon: Layers }
};

const ASSET_CLASS_COLORS = {
  finance: '#ef4444',
  politics: '#f59e0b', 
  crypto: '#10b981',
  entertainment: '#06b6d4',
  science: '#8b5cf6',
  sports: '#ec4899'
};

// Confirmation Modal Component
const ConfirmModal = ({ isOpen, title, message, onConfirm, onCancel }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-white/20 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle className="w-6 h-6 text-amber-400" />
          <h3 className="text-lg font-bold text-white">{title}</h3>
        </div>
        <p className="text-white/70 mb-6">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="px-4 py-2 rounded-lg bg-white/10 text-white hover:bg-white/20 transition">
            Cancel
          </button>
          <button onClick={onConfirm} className="px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600 transition">
            Confirm Reset
          </button>
        </div>
      </div>
    </div>
  );
};

// Session Trades Modal
const SessionTradesModal = ({ isOpen, session, trades, onClose }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-white/20 rounded-xl max-w-5xl w-full mx-4 shadow-2xl max-h-[80vh] flex flex-col">
        <div className="p-4 border-b border-white/10 flex items-center justify-between">
          <h3 className="text-lg font-bold text-white">Session Trades: {session?.session_id}</h3>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 text-white/60 hover:text-white">✕</button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          <table className="w-full text-sm">
            <thead className="bg-white/5 sticky top-0">
              <tr>
                <th className="py-2 px-3 text-left text-xs text-white/60">Market</th>
                <th className="py-2 px-3 text-left text-xs text-white/60">Strategy</th>
                <th className="py-2 px-3 text-left text-xs text-white/60">Side</th>
                <th className="py-2 px-3 text-right text-xs text-white/60">Entry Price</th>
                <th className="py-2 px-3 text-right text-xs text-white/60">Exit Price</th>
                <th className="py-2 px-3 text-right text-xs text-white/60">P&L ($)</th>
                <th className="py-2 px-3 text-right text-xs text-white/60">P&L (%)</th>
                <th className="py-2 px-3 text-right text-xs text-white/60">Duration</th>
              </tr>
            </thead>
            <tbody>
              {trades?.map((trade, idx) => {
                const pnlPct = trade.pnl_pct != null ? (trade.pnl_pct * 100) : 0;  // Use API value, convert from decimal
                const duration = trade.hold_time_seconds ? `${Math.floor(trade.hold_time_seconds / 60)}m ${trade.hold_time_seconds % 60}s` : '-';
                return (
                  <tr key={idx} className="border-b border-white/5 hover:bg-white/5">
                    <td className="py-2 px-3 text-white/80 max-w-xs truncate">{trade.market_question || trade.market_id?.substring(0, 30)}</td>
                    <td className="py-2 px-3 text-white/60">{STRATEGY_INFO[trade.strategy]?.name || trade.strategy}</td>
                    <td className="py-2 px-3"><span className={`px-2 py-0.5 rounded text-xs ${trade.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{trade.side}</span></td>
                    <td className="py-2 px-3 text-right text-white/80">${trade.entry_price?.toFixed(4)}</td>
                    <td className="py-2 px-3 text-right text-white/80">${trade.exit_price?.toFixed(4)}</td>
                    <td className={`py-2 px-3 text-right font-bold ${(trade.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(trade.pnl || 0) >= 0 ? '+' : ''}${(trade.pnl || 0).toFixed(2)}
                    </td>
                    <td className={`py-2 px-3 text-right ${pnlPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                    </td>
                    <td className="py-2 px-3 text-right text-white/60">{duration}</td>
                  </tr>
                );
              })}
              {(!trades || trades.length === 0) && (
                <tr><td colSpan={8} className="py-8 text-center text-white/40">No trades in this session</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// Sentiment Breakdown Modal - Shows detailed sentiment analysis for a trade
const SentimentModal = ({ isOpen, trade, onClose }) => {
  if (!isOpen || !trade) return null;
  
  const sentiment = trade.sentiment || {};
  const layers = sentiment.layers || {};
  const weights = sentiment.weights || {};
  const components = sentiment.components || {};
  const enhanced = sentiment.enhanced_data || {};
  
  const SentimentBar = ({ value, label, color = "cyan" }) => (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-white/60">{label}</span>
        <span className={`text-${color}-400 font-mono`}>{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-white/10 rounded-full overflow-hidden">
        <div 
          className={`h-full bg-gradient-to-r from-${color}-500 to-${color}-400 transition-all`}
          style={{ width: `${Math.min(100, value * 100)}%` }}
        />
      </div>
    </div>
  );
  
  const getBiasColor = (val) => val > 0.55 ? 'green' : val < 0.45 ? 'red' : 'yellow';
  const biasColor = getBiasColor(sentiment.final || 0.5);
  
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-white/20 rounded-xl max-w-2xl w-full mx-4 shadow-2xl max-h-[85vh] flex flex-col">
        <div className="p-4 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Brain className="w-5 h-5 text-purple-400" />
            <h3 className="text-lg font-bold text-white">Sentiment Analysis</h3>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 text-white/60 hover:text-white">✕</button>
        </div>
        
        <div className="flex-1 overflow-auto p-4 space-y-6">
          {/* Market Info */}
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-white/80 text-sm">{trade.market_question}</p>
            <div className="flex gap-4 mt-2 text-xs text-white/50">
              <span>Strategy: <span className="text-white/80">{STRATEGY_INFO[trade.strategy]?.name}</span></span>
              <span>Side: <span className={trade.side === 'YES' ? 'text-green-400' : 'text-red-400'}>{trade.side}</span></span>
              <span>Price: <span className="text-white/80">${trade.price?.toFixed(4)}</span></span>
            </div>
          </div>
          
          {/* Final Sentiment */}
          <div className={`bg-${biasColor}-500/10 border border-${biasColor}-500/30 rounded-xl p-4`}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-white/50 uppercase tracking-wider">Final Sentiment</p>
                <p className={`text-3xl font-bold text-${biasColor}-400`}>
                  {((sentiment.final || 0.5) * 100).toFixed(1)}%
                </p>
                <p className="text-xs text-white/50 mt-1">
                  {sentiment.final > 0.6 ? '🟢 Bullish' : sentiment.final < 0.4 ? '🔴 Bearish' : '🟡 Neutral'}
                  {' • '}Strength: {((sentiment.strength || 0) * 100).toFixed(0)}%
                </p>
              </div>
              <div className="w-20 h-20 rounded-full border-4 border-white/10 flex items-center justify-center relative">
                <div 
                  className={`absolute inset-1 rounded-full bg-gradient-to-t from-${biasColor}-500/40 to-transparent`}
                  style={{ clipPath: `inset(${100 - (sentiment.final || 0.5) * 100}% 0 0 0)` }}
                />
                <span className="text-lg font-bold text-white">{((sentiment.final || 0.5) * 100).toFixed(0)}</span>
              </div>
            </div>
          </div>
          
          {/* Sentiment Layers */}
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-white/80 flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              Sentiment Layers
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/5 rounded-lg p-3 space-y-3">
                <p className="text-xs font-semibold text-cyan-400 uppercase">Market Microstructure</p>
                <SentimentBar value={layers.market_microstructure || 0.5} label="Combined" color="cyan" />
                <div className="text-xs text-white/40">Weight: {((weights.market_weight || 0.4) * 100).toFixed(0)}%</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 space-y-3">
                <p className="text-xs font-semibold text-purple-400 uppercase">LLM Analysis (GPT-4o)</p>
                <SentimentBar value={layers.llm_sentiment || 0.5} label="Probability" color="purple" />
                <div className="text-xs text-white/40">
                  Confidence: {((layers.llm_confidence || 0) * 100).toFixed(0)}% • 
                  Weight: {((weights.llm_weight || 0) * 100).toFixed(0)}%
                </div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 space-y-3">
                <p className="text-xs font-semibold text-amber-400 uppercase">Cross-Market Correlation</p>
                <SentimentBar value={layers.correlation_sentiment || 0.5} label="Related Markets" color="amber" />
                <div className="text-xs text-white/40">
                  Strength: {((layers.correlation_strength || 0) * 100).toFixed(0)}% • 
                  Weight: {((weights.correlation_weight || 0) * 100).toFixed(0)}%
                </div>
              </div>
              <div className="bg-white/5 rounded-lg p-3 space-y-3">
                <p className="text-xs font-semibold text-emerald-400 uppercase">External News/Social</p>
                <SentimentBar value={layers.external_data || 0.5} label="News Sentiment" color="emerald" />
                <div className="text-xs text-white/40">
                  Confidence: {((layers.external_confidence || 0) * 100).toFixed(0)}% • 
                  Weight: {((weights.external_weight || 0) * 100).toFixed(0)}%
                </div>
              </div>
            </div>
          </div>
          
          {/* Market Components */}
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-white/80 flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              Market Components
            </h4>
            <div className="grid grid-cols-3 gap-3">
              {[
                { key: 'price', label: 'Price', color: 'blue' },
                { key: 'momentum', label: 'Momentum', color: 'green' },
                { key: 'volume_intensity', label: 'Volume', color: 'amber' },
                { key: 'liquidity', label: 'Liquidity', color: 'cyan' },
                { key: 'whale', label: 'Whale Activity', color: 'purple' },
                { key: 'maturity_weight', label: 'Maturity', color: 'slate' }
              ].map(({ key, label, color }) => (
                <div key={key} className="bg-white/5 rounded-lg p-2 text-center">
                  <p className="text-xs text-white/50">{label}</p>
                  <p className={`text-lg font-bold text-${color}-400`}>
                    {((components[key] || 0.5) * 100).toFixed(0)}%
                  </p>
                </div>
              ))}
            </div>
          </div>
          
          {/* LLM Reasoning */}
          {enhanced.llm_reasoning && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                <Brain className="w-4 h-4 text-purple-400" />
                LLM Reasoning
              </h4>
              <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-3">
                <p className="text-sm text-white/70 italic">"{enhanced.llm_reasoning}"</p>
              </div>
            </div>
          )}
          
          {/* Related Market Groups */}
          {enhanced.related_groups && enhanced.related_groups.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-white/80">Related Market Groups</h4>
              <div className="flex flex-wrap gap-2">
                {enhanced.related_groups.map((group, idx) => (
                  <span key={idx} className="px-2 py-1 bg-amber-500/20 text-amber-400 rounded text-xs">
                    {group}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Reset Button Component
const ResetButton = ({ onClick, label = "Reset" }) => (
  <button
    onClick={onClick}
    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 hover:bg-rose-500/20 transition text-xs font-medium"
    data-testid="reset-btn"
  >
    <RotateCcw className="w-3 h-3" />
    {label}
  </button>
);

// Metric Card Component
const MetricCard = ({ title, value, subtitle, icon: Icon, trend, color = "cyan" }) => (
  <div className={`rounded-xl bg-gradient-to-br from-${color}-500/10 to-${color}-600/5 border border-${color}-500/20 p-4`}>
    <div className="flex items-center justify-between mb-2">
      <span className="text-xs text-white/60 uppercase tracking-wider">{title}</span>
      {Icon && <Icon className={`w-4 h-4 text-${color}-400`} />}
    </div>
    <div className="flex items-end gap-2">
      <span className="text-2xl font-bold text-white">{value}</span>
      {trend !== undefined && (
        <span className={`text-sm flex items-center ${trend >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {trend >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {Math.abs(trend).toFixed(1)}%
        </span>
      )}
    </div>
    {subtitle && <p className="text-xs text-white/40 mt-1">{subtitle}</p>}
  </div>
);

// Asset Class Equity Breakdown - Shows P&L by asset class starting at $0
const AssetClassEquityCard = ({ equityData, initialCapital = 10000 }) => {
  if (!equityData || Object.keys(equityData).length === 0) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-4">
        <h4 className="text-sm font-semibold text-white/60 mb-3 flex items-center gap-2">
          <PieChart className="w-4 h-4 text-orange-400" />
          Asset Class Equity (starts at $0)
        </h4>
        <p className="text-xs text-white/40">No trades yet</p>
      </div>
    );
  }

  const entries = Object.entries(equityData).sort((a, b) => b[1] - a[1]);
  const total = Object.values(equityData).reduce((sum, val) => sum + val, 0);

  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-white flex items-center gap-2">
          <PieChart className="w-4 h-4 text-orange-400" />
          Asset Class Equity
          <span className="text-[10px] text-white/40 font-normal">(starts at $0)</span>
        </h4>
        <span className={`text-sm font-bold ${total >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {total >= 0 ? '+' : ''}${total.toFixed(2)}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {entries.map(([assetClass, pnl]) => {
          const isPositive = pnl >= 0;
          const color = ASSET_CLASS_COLORS[assetClass] || '#94a3b8';
          return (
            <div key={assetClass} className="bg-white/5 rounded-lg p-2 text-center">
              <div className="flex items-center justify-center gap-1 mb-1">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-[10px] text-white/60 uppercase tracking-wider">{assetClass}</span>
              </div>
              <span className={`text-sm font-bold ${isPositive ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-white/40'}`}>
                {pnl === 0 ? '$0' : (isPositive ? '+' : '') + '$' + pnl.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// Position Card Component with Expiry Indicator
// Sizing Breakdown Modal - Shows detailed position sizing calculation
const SizingBreakdownModal = ({ isOpen, position, onClose }) => {
  if (!isOpen || !position) return null;
  
  const breakdown = position.sizing_breakdown || {};
  const hasSizerData = breakdown.kelly_base !== undefined;
  
  // Format multiplier impact
  const formatMultiplier = (value, label) => {
    if (value === undefined || value === null) return null;
    const impact = value < 1 ? 'reduces' : value > 1 ? 'increases' : 'no change';
    const color = value < 0.7 ? 'text-red-400' : value < 0.9 ? 'text-amber-400' : value <= 1.1 ? 'text-green-400' : 'text-cyan-400';
    return { value, label, impact, color };
  };
  
  // Calculate waterfall values
  const kellyBase = breakdown.kelly_base || 0;
  const afterUtil = kellyBase * (breakdown.utilization_mult || 1);
  const afterTime = afterUtil * (breakdown.time_penalty || 1);
  const afterOracle = afterTime * (breakdown.oracle_mult || 1);
  const afterCorr = afterOracle * (breakdown.correlation_mult || 1);
  const finalSize = breakdown.final_size || position.size || 0;
  
  // Multiplier data for visualization
  const multipliers = [
    formatMultiplier(breakdown.utilization_mult, 'Utilization Brake'),
    formatMultiplier(breakdown.time_penalty, 'Time Penalty'),
    formatMultiplier(breakdown.oracle_mult, 'Oracle Risk'),
    formatMultiplier(breakdown.correlation_mult, 'Correlation'),
  ].filter(Boolean);
  
  // Caps data
  const caps = [
    { label: 'Liquidity Cap', value: breakdown.liquidity_cap, applied: breakdown.kelly_adjusted > breakdown.liquidity_cap },
    { label: 'Sector Cap', value: breakdown.sector_cap, applied: breakdown.size_before_sector > breakdown.sector_cap },
    { label: 'Max Position', value: breakdown.max_single_position, applied: breakdown.size_after_sector > breakdown.max_single_position },
  ];
  
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-white/20 rounded-xl max-w-3xl w-full mx-4 shadow-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-500 flex items-center justify-center">
              <Scale className="w-4 h-4 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Position Sizing Breakdown</h3>
              <p className="text-xs text-white/50">Polymarket Dynamic Sizer v2.0</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/10 text-white/60 hover:text-white">✕</button>
        </div>
        
        <div className="flex-1 overflow-auto p-4 space-y-5">
          {/* Market Info */}
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-white/80 text-sm font-medium">{position.market_question}</p>
            <div className="flex gap-4 mt-2 text-xs">
              <span className="text-white/50">Side: <span className={position.side === 'YES' ? 'text-green-400' : 'text-red-400'}>{position.side}</span></span>
              <span className="text-white/50">Strategy: <span className="text-white/80">{position.strategy}</span></span>
              <span className="text-white/50">Category: <span className="text-cyan-400 capitalize">{breakdown.category || 'unknown'}</span></span>
            </div>
          </div>
          
          {!hasSizerData ? (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-center">
              <p className="text-amber-400">Sizing breakdown not available for this position (legacy mode)</p>
            </div>
          ) : (
            <>
              {/* Edge Calculation Box */}
              <div className="bg-gradient-to-br from-emerald-500/10 to-cyan-500/10 border border-emerald-500/30 rounded-xl p-4">
                <h4 className="text-sm font-semibold text-emerald-400 mb-3 flex items-center gap-2">
                  <Target className="w-4 h-4" /> Edge Calculation
                </h4>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center">
                    <p className="text-xs text-white/50">Model Probability</p>
                    <p className="text-2xl font-bold text-cyan-400">{((breakdown.model_probability || 0) * 100).toFixed(1)}%</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-white/50">Effective Price</p>
                    <p className="text-2xl font-bold text-amber-400">{((breakdown.effective_price || 0) * 100).toFixed(2)}%</p>
                    <p className="text-[10px] text-white/30">Ask: {((breakdown.ask_price || 0) * 100).toFixed(2)}% + 2% fee</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-white/50">Trade Edge</p>
                    <p className={`text-2xl font-bold ${(breakdown.edge || 0) > 0.03 ? 'text-green-400' : 'text-yellow-400'}`}>
                      +{((breakdown.edge || 0) * 100).toFixed(2)}%
                    </p>
                  </div>
                </div>
              </div>
              
              {/* Probability Model Diagnostics Panel - NEW */}
              {breakdown.probability_diagnostics && (
                <div className="bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/30 rounded-xl p-4">
                  <h4 className="text-sm font-semibold text-indigo-400 mb-3 flex items-center gap-2">
                    <Brain className="w-4 h-4" /> Probability Model Diagnostics
                    <span className="text-[10px] px-2 py-0.5 bg-indigo-500/20 rounded-full text-indigo-300 ml-auto">
                      WEIGHTED ENSEMBLE
                    </span>
                  </h4>
                  
                  {/* Component Probabilities */}
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div className="bg-white/5 rounded-lg p-3 text-center">
                      <p className="text-[10px] text-white/50 uppercase tracking-wider">P<sub>market</sub></p>
                      <p className="text-xl font-bold text-blue-400">
                        {((breakdown.probability_diagnostics.components?.p_market || 0) * 100).toFixed(1)}%
                      </p>
                      <p className="text-[10px] text-white/30">Market price</p>
                    </div>
                    <div className="bg-white/5 rounded-lg p-3 text-center">
                      <p className="text-[10px] text-white/50 uppercase tracking-wider">P<sub>sentiment</sub></p>
                      <p className="text-xl font-bold text-amber-400">
                        {((breakdown.probability_diagnostics.components?.p_sentiment || 0) * 100).toFixed(1)}%
                      </p>
                      <p className="text-[10px] text-white/30">AI sentiment</p>
                    </div>
                    <div className="bg-white/5 rounded-lg p-3 text-center">
                      <p className="text-[10px] text-white/50 uppercase tracking-wider">P<sub>RL</sub></p>
                      <p className="text-xl font-bold text-green-400">
                        {((breakdown.probability_diagnostics.components?.p_rl || 0) * 100).toFixed(1)}%
                      </p>
                      <p className="text-[10px] text-white/30">DQN implied</p>
                    </div>
                  </div>
                  
                  {/* Weights Visualization */}
                  <div className="mb-4">
                    <p className="text-[10px] text-white/50 uppercase tracking-wider mb-2">Signal Weights (sum to 1.0)</p>
                    <div className="flex h-6 rounded-full overflow-hidden bg-white/5">
                      <div 
                        className="bg-blue-500 flex items-center justify-center text-[10px] text-white font-bold"
                        style={{ width: `${(breakdown.probability_diagnostics.weights?.w_market || 0.5) * 100}%` }}
                      >
                        {((breakdown.probability_diagnostics.weights?.w_market || 0.5) * 100).toFixed(0)}%
                      </div>
                      <div 
                        className="bg-amber-500 flex items-center justify-center text-[10px] text-white font-bold"
                        style={{ width: `${(breakdown.probability_diagnostics.weights?.w_sentiment || 0.25) * 100}%` }}
                      >
                        {((breakdown.probability_diagnostics.weights?.w_sentiment || 0.25) * 100).toFixed(0)}%
                      </div>
                      <div 
                        className="bg-green-500 flex items-center justify-center text-[10px] text-white font-bold"
                        style={{ width: `${(breakdown.probability_diagnostics.weights?.w_rl || 0.25) * 100}%` }}
                      >
                        {((breakdown.probability_diagnostics.weights?.w_rl || 0.25) * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div className="flex justify-between text-[10px] text-white/40 mt-1">
                      <span className="flex items-center gap-1"><span className="w-2 h-2 bg-blue-500 rounded-full"></span>Market</span>
                      <span className="flex items-center gap-1"><span className="w-2 h-2 bg-amber-500 rounded-full"></span>Sentiment</span>
                      <span className="flex items-center gap-1"><span className="w-2 h-2 bg-green-500 rounded-full"></span>RL</span>
                    </div>
                  </div>
                  
                  {/* Contribution Breakdown */}
                  <div className="bg-white/5 rounded-lg p-3 mb-3">
                    <p className="text-[10px] text-white/50 uppercase tracking-wider mb-2">Weighted Contributions</p>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-blue-400">w×P<sub>market</sub></span>
                        <div className="flex-1 mx-3 h-2 bg-white/10 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-blue-500"
                            style={{ width: `${Math.min(100, (breakdown.probability_diagnostics.contributions?.market_contribution || 0) * 100 * 2)}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-white/80">{((breakdown.probability_diagnostics.contributions?.market_contribution || 0) * 100).toFixed(2)}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-amber-400">w×P<sub>sent</sub></span>
                        <div className="flex-1 mx-3 h-2 bg-white/10 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-amber-500"
                            style={{ width: `${Math.min(100, (breakdown.probability_diagnostics.contributions?.sentiment_contribution || 0) * 100 * 2)}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-white/80">{((breakdown.probability_diagnostics.contributions?.sentiment_contribution || 0) * 100).toFixed(2)}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-green-400">w×P<sub>RL</sub></span>
                        <div className="flex-1 mx-3 h-2 bg-white/10 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-green-500"
                            style={{ width: `${Math.min(100, (breakdown.probability_diagnostics.contributions?.rl_contribution || 0) * 100 * 2)}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-white/80">{((breakdown.probability_diagnostics.contributions?.rl_contribution || 0) * 100).toFixed(2)}%</span>
                      </div>
                      <div className="flex items-center justify-between pt-2 border-t border-white/10">
                        <span className="text-xs text-indigo-400 font-semibold">P<sub>final</sub> = Σ</span>
                        <span className="text-lg font-bold text-indigo-400">{((breakdown.probability_diagnostics.final_probability || 0) * 100).toFixed(2)}%</span>
                      </div>
                    </div>
                  </div>
                  
                  {/* RL Details */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-white/5 rounded-lg p-2">
                      <p className="text-[10px] text-white/50">RL Action</p>
                      <p className={`text-sm font-bold ${breakdown.probability_diagnostics.rl_details?.direction === 'bullish' ? 'text-green-400' : breakdown.probability_diagnostics.rl_details?.direction === 'bearish' ? 'text-red-400' : 'text-white/60'}`}>
                        {breakdown.probability_diagnostics.rl_details?.action || 'HOLD'}
                      </p>
                      <p className="text-[10px] text-white/30">
                        Deviation: {breakdown.probability_diagnostics.rl_details?.deviation ? `±${(breakdown.probability_diagnostics.rl_details.deviation * 100).toFixed(1)}%` : '0%'}
                      </p>
                    </div>
                    <div className="bg-white/5 rounded-lg p-2">
                      <p className="text-[10px] text-white/50">Signal Agreement</p>
                      <p className={`text-sm font-bold ${breakdown.probability_diagnostics.signal_agreement?.sentiment_agrees_rl ? 'text-green-400' : breakdown.probability_diagnostics.signal_agreement?.sentiment_disagrees_rl ? 'text-red-400' : 'text-white/60'}`}>
                        {breakdown.probability_diagnostics.signal_agreement?.sentiment_agrees_rl ? '✓ ALIGNED' : 
                         breakdown.probability_diagnostics.signal_agreement?.sentiment_disagrees_rl ? '✗ CONFLICT' : '— NEUTRAL'}
                      </p>
                      <p className="text-[10px] text-white/30">
                        {breakdown.probability_diagnostics.signal_agreement?.sentiment_agrees_rl ? 'Market weight reduced' : 
                         breakdown.probability_diagnostics.signal_agreement?.sentiment_disagrees_rl ? 'Market weight boosted' : 'Weights balanced'}
                      </p>
                    </div>
                  </div>
                  
                  {/* Formula */}
                  <div className="mt-3 pt-3 border-t border-white/10">
                    <p className="text-[10px] text-white/30 font-mono text-center">
                      P<sub>final</sub> = w<sub>m</sub>×P<sub>m</sub> + w<sub>s</sub>×P<sub>s</sub> + w<sub>rl</sub>×P<sub>rl</sub> → clamp(0.01, 0.99)
                    </p>
                  </div>
                </div>
              )}
              
              {/* Kelly Base */}
              <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4">
                <h4 className="text-sm font-semibold text-purple-400 mb-3 flex items-center gap-2">
                  <Percent className="w-4 h-4" /> Binary Kelly Criterion
                </h4>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-white/50">Kelly Fraction (raw)</p>
                    <p className="text-lg font-bold text-white">{((breakdown.kelly_fraction || 0) * 100).toFixed(2)}%</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-white/50">Kelly Base (0.25× multiplier)</p>
                    <p className="text-2xl font-bold text-purple-400">${(breakdown.kelly_base || 0).toFixed(2)}</p>
                  </div>
                </div>
                <p className="text-[10px] text-white/30 mt-2">Formula: edge / (1 - effective_price) × equity × 0.25</p>
              </div>
              
              {/* Multipliers Waterfall */}
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <h4 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-cyan-400" /> Size Multipliers (Waterfall)
                </h4>
                
                {/* Visual waterfall */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between py-2 border-b border-white/10">
                    <span className="text-sm text-white">Kelly Base</span>
                    <span className="text-lg font-bold text-purple-400">${kellyBase.toFixed(2)}</span>
                  </div>
                  
                  {/* Utilization */}
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-white/60">Utilization Brake</span>
                        <span className={`text-xs font-mono ${(breakdown.utilization_mult || 1) < 0.5 ? 'text-red-400' : 'text-green-400'}`}>
                          ×{(breakdown.utilization_mult || 1).toFixed(3)}
                        </span>
                      </div>
                      <div className="h-2 bg-white/10 rounded-full overflow-hidden mt-1">
                        <div 
                          className="h-full bg-gradient-to-r from-red-500 via-yellow-500 to-green-500"
                          style={{ width: `${(breakdown.utilization_mult || 1) * 100}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-white/30 mt-1">Portfolio: {((breakdown.utilization || 0) * 100).toFixed(1)}% deployed → ${afterUtil.toFixed(2)}</p>
                    </div>
                  </div>
                  
                  {/* Time Penalty */}
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-white/60">Time/Duration Penalty</span>
                        <span className={`text-xs font-mono ${(breakdown.time_penalty || 1) < 0.7 ? 'text-amber-400' : 'text-green-400'}`}>
                          ×{(breakdown.time_penalty || 1).toFixed(3)}
                        </span>
                      </div>
                      <div className="h-2 bg-white/10 rounded-full overflow-hidden mt-1">
                        <div 
                          className="h-full bg-gradient-to-r from-amber-500 to-green-500"
                          style={{ width: `${(breakdown.time_penalty || 1) * 100}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-white/30 mt-1">{(breakdown.days_to_expiry || 0).toFixed(1)} days to expiry → ${afterTime.toFixed(2)}</p>
                    </div>
                  </div>
                  
                  {/* Oracle Risk */}
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-white/60">Oracle/Ambiguity Risk</span>
                        <span className={`text-xs font-mono ${(breakdown.oracle_mult || 1) < 0.6 ? 'text-red-400' : (breakdown.oracle_mult || 1) < 0.8 ? 'text-amber-400' : 'text-green-400'}`}>
                          ×{(breakdown.oracle_mult || 1).toFixed(2)}
                        </span>
                      </div>
                      <div className="h-2 bg-white/10 rounded-full overflow-hidden mt-1">
                        <div 
                          className={`h-full ${(breakdown.oracle_mult || 1) < 0.5 ? 'bg-red-500' : (breakdown.oracle_mult || 1) < 0.8 ? 'bg-amber-500' : 'bg-green-500'}`}
                          style={{ width: `${(breakdown.oracle_mult || 1) * 100}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-white/30 mt-1">{breakdown.category_reasoning || 'Standard risk'} → ${afterOracle.toFixed(2)}</p>
                    </div>
                  </div>
                  
                  {/* Correlation */}
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-white/60">Correlation Dampener</span>
                        <span className={`text-xs font-mono ${(breakdown.correlation_mult || 1) < 0.5 ? 'text-amber-400' : 'text-green-400'}`}>
                          ×{(breakdown.correlation_mult || 1).toFixed(2)}
                        </span>
                      </div>
                      <div className="h-2 bg-white/10 rounded-full overflow-hidden mt-1">
                        <div 
                          className="h-full bg-cyan-500"
                          style={{ width: `${(breakdown.correlation_mult || 1) * 100}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-white/30 mt-1">{breakdown.n_correlated_positions || 0} correlated positions → ${afterCorr.toFixed(2)}</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-between pt-3 border-t border-white/10">
                    <span className="text-sm text-white font-medium">Adjusted Size</span>
                    <span className="text-lg font-bold text-cyan-400">${(breakdown.kelly_adjusted || 0).toFixed(2)}</span>
                  </div>
                </div>
              </div>
              
              {/* Caps Applied */}
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-amber-400" /> Size Caps
                </h4>
                <div className="grid grid-cols-3 gap-3">
                  {caps.map((cap, idx) => (
                    <div key={idx} className={`rounded-lg p-3 text-center ${cap.applied ? 'bg-amber-500/20 border border-amber-500/30' : 'bg-white/5'}`}>
                      <p className="text-[10px] text-white/50 uppercase tracking-wider">{cap.label}</p>
                      <p className={`text-lg font-bold ${cap.applied ? 'text-amber-400' : 'text-white/60'}`}>
                        ${(cap.value || 0).toFixed(0)}
                      </p>
                      {cap.applied && <p className="text-[10px] text-amber-400">APPLIED</p>}
                    </div>
                  ))}
                </div>
              </div>
              
              {/* Final Result */}
              <div className="bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border-2 border-cyan-500/40 rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-white/50">FINAL POSITION SIZE</p>
                    <p className="text-3xl font-black text-cyan-400">${finalSize.toFixed(2)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-white/50">Portfolio Context</p>
                    <p className="text-sm text-white/70">Equity: ${(breakdown.equity || 0).toFixed(0)}</p>
                    <p className="text-sm text-white/70">Deployed: ${(breakdown.deployed || 0).toFixed(0)}</p>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-white/10 flex items-center justify-between text-xs">
                  <span className="text-white/40">
                    Size reduction: {kellyBase > 0 ? ((1 - finalSize / kellyBase) * 100).toFixed(0) : 0}% from Kelly base
                  </span>
                  <span className={`px-2 py-0.5 rounded ${breakdown.sizer_mode === 'polymarket' ? 'bg-cyan-500/20 text-cyan-400' : 'bg-gray-500/20 text-gray-400'}`}>
                    {breakdown.sizer_mode === 'polymarket' ? 'DYNAMIC SIZER' : 'LEGACY'}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// Sizing Analytics Dashboard Component
const SizingAnalyticsDashboard = ({ positions, trades }) => {
  // Combine positions and trades for full analysis
  const allItems = [
    ...positions.map(p => ({ ...p, type: 'position' })),
    ...trades.filter(t => t.sizing_breakdown).map(t => ({ ...t, type: 'trade' }))
  ];
  
  if (allItems.length === 0) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-purple-400" />Sizing Analytics
        </h3>
        <p className="text-white/40 text-center py-4">No sizing data available yet. Start trading to see analytics.</p>
      </div>
    );
  }
  
  // Calculate analytics
  const analytics = {
    byCategory: {},
    byOracleRange: { high: [], medium: [], low: [] },
    sizingEfficiency: []
  };
  
  allItems.forEach(item => {
    const breakdown = item.sizing_breakdown || {};
    const category = breakdown.category || item.category || 'unknown';
    const edge = breakdown.edge || 0;
    const oracleMult = breakdown.oracle_mult || 1;
    const kellyBase = breakdown.kelly_base || 0;
    const finalSize = breakdown.final_size || item.size || 0;
    const pnl = item.type === 'trade' ? (item.pnl || 0) : (item.unrealized_pnl || 0);
    const pnlPct = item.type === 'trade' ? (item.return_pct || 0) : (item.unrealized_pnl_pct || 0);
    
    // By Category
    if (!analytics.byCategory[category]) {
      analytics.byCategory[category] = { count: 0, totalEdge: 0, totalPnl: 0, wins: 0 };
    }
    analytics.byCategory[category].count++;
    analytics.byCategory[category].totalEdge += edge;
    analytics.byCategory[category].totalPnl += pnl;
    if (pnl > 0) analytics.byCategory[category].wins++;
    
    // By Oracle Range
    if (oracleMult >= 0.9) {
      analytics.byOracleRange.high.push({ pnlPct, pnl });
    } else if (oracleMult >= 0.6) {
      analytics.byOracleRange.medium.push({ pnlPct, pnl });
    } else {
      analytics.byOracleRange.low.push({ pnlPct, pnl });
    }
    
    // Sizing Efficiency
    if (kellyBase > 0) {
      analytics.sizingEfficiency.push({
        efficiency: finalSize / kellyBase,
        pnlPct,
        oracleMult,
        category
      });
    }
  });
  
  // Calculate averages
  const categoryStats = Object.entries(analytics.byCategory).map(([cat, data]) => ({
    category: cat,
    count: data.count,
    avgEdge: data.count > 0 ? (data.totalEdge / data.count) * 100 : 0,
    totalPnl: data.totalPnl,
    winRate: data.count > 0 ? (data.wins / data.count) * 100 : 0
  })).sort((a, b) => b.count - a.count);
  
  const oracleStats = {
    high: {
      count: analytics.byOracleRange.high.length,
      avgPnl: analytics.byOracleRange.high.length > 0 
        ? analytics.byOracleRange.high.reduce((s, x) => s + x.pnl, 0) / analytics.byOracleRange.high.length 
        : 0,
      winRate: analytics.byOracleRange.high.length > 0
        ? (analytics.byOracleRange.high.filter(x => x.pnl > 0).length / analytics.byOracleRange.high.length) * 100
        : 0
    },
    medium: {
      count: analytics.byOracleRange.medium.length,
      avgPnl: analytics.byOracleRange.medium.length > 0 
        ? analytics.byOracleRange.medium.reduce((s, x) => s + x.pnl, 0) / analytics.byOracleRange.medium.length 
        : 0,
      winRate: analytics.byOracleRange.medium.length > 0
        ? (analytics.byOracleRange.medium.filter(x => x.pnl > 0).length / analytics.byOracleRange.medium.length) * 100
        : 0
    },
    low: {
      count: analytics.byOracleRange.low.length,
      avgPnl: analytics.byOracleRange.low.length > 0 
        ? analytics.byOracleRange.low.reduce((s, x) => s + x.pnl, 0) / analytics.byOracleRange.low.length 
        : 0,
      winRate: analytics.byOracleRange.low.length > 0
        ? (analytics.byOracleRange.low.filter(x => x.pnl > 0).length / analytics.byOracleRange.low.length) * 100
        : 0
    }
  };
  
  const avgEfficiency = analytics.sizingEfficiency.length > 0
    ? analytics.sizingEfficiency.reduce((s, x) => s + x.efficiency, 0) / analytics.sizingEfficiency.length
    : 1;
  
  return (
    <div className="rounded-xl bg-gradient-to-br from-purple-500/10 to-cyan-500/10 border border-purple-500/20 p-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-purple-400" />Sizing Analytics Dashboard
        <span className="text-xs text-white/40 ml-auto">{allItems.length} positions analyzed</span>
      </h3>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Edge by Category */}
        <div className="bg-white/5 rounded-lg p-4">
          <h4 className="text-sm font-medium text-white/80 mb-3 flex items-center gap-2">
            <Target className="w-4 h-4 text-cyan-400" />Avg Edge by Category
          </h4>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {categoryStats.slice(0, 6).map(stat => (
              <div key={stat.category} className="flex items-center justify-between">
                <span className="text-xs text-white/60 capitalize">{stat.category}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-white/40">({stat.count})</span>
                  <span className={`text-sm font-bold ${stat.avgEdge > 3 ? 'text-green-400' : 'text-yellow-400'}`}>
                    +{stat.avgEdge.toFixed(1)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        {/* Win Rate by Oracle Range */}
        <div className="bg-white/5 rounded-lg p-4">
          <h4 className="text-sm font-medium text-white/80 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />Win Rate by Oracle Risk
          </h4>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-green-500" />
                <span className="text-xs text-white/60">High Trust (≥0.9)</span>
              </div>
              <div className="text-right">
                <span className="text-sm font-bold text-white">{oracleStats.high.winRate.toFixed(0)}%</span>
                <span className="text-xs text-white/40 ml-2">({oracleStats.high.count})</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-yellow-500" />
                <span className="text-xs text-white/60">Medium (0.6-0.9)</span>
              </div>
              <div className="text-right">
                <span className="text-sm font-bold text-white">{oracleStats.medium.winRate.toFixed(0)}%</span>
                <span className="text-xs text-white/40 ml-2">({oracleStats.medium.count})</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <span className="text-xs text-white/60">Low Trust (&lt;0.6)</span>
              </div>
              <div className="text-right">
                <span className="text-sm font-bold text-white">{oracleStats.low.winRate.toFixed(0)}%</span>
                <span className="text-xs text-white/40 ml-2">({oracleStats.low.count})</span>
              </div>
            </div>
          </div>
        </div>
        
        {/* Sizing Efficiency */}
        <div className="bg-white/5 rounded-lg p-4">
          <h4 className="text-sm font-medium text-white/80 mb-3 flex items-center gap-2">
            <Scale className="w-4 h-4 text-purple-400" />Sizing Efficiency
          </h4>
          <div className="text-center py-2">
            <p className="text-3xl font-black text-purple-400">{(avgEfficiency * 100).toFixed(0)}%</p>
            <p className="text-xs text-white/50 mt-1">Actual vs Kelly Base</p>
          </div>
          <div className="mt-3 space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-white/40">Avg reduction from caps</span>
              <span className="text-white/60">{((1 - avgEfficiency) * 100).toFixed(0)}%</span>
            </div>
            <div className="h-2 bg-white/10 rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-purple-500 to-cyan-500"
                style={{ width: `${avgEfficiency * 100}%` }}
              />
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-white/10">
            <p className="text-[10px] text-white/30">
              Higher = more aggressive (fewer caps applied).<br/>
              Lower = more conservative (caps protecting capital).
            </p>
          </div>
        </div>
      </div>
      
      {/* Category P&L Summary */}
      <div className="mt-4 bg-white/5 rounded-lg p-4">
        <h4 className="text-sm font-medium text-white/80 mb-3">P&L by Category</h4>
        <div className="flex flex-wrap gap-2">
          {categoryStats.map(stat => (
            <div 
              key={stat.category}
              className={`px-3 py-1.5 rounded-lg text-xs ${stat.totalPnl >= 0 ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}
            >
              <span className="text-white/60 capitalize">{stat.category}</span>
              <span className={`ml-2 font-bold ${stat.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stat.totalPnl >= 0 ? '+' : ''}{stat.totalPnl.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// Historical Analytics Chart Component
const HistoricalAnalyticsChart = () => {
  const [historyData, setHistoryData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeChart, setActiveChart] = useState('efficiency');
  
  useEffect(() => {
    fetchHistory();
  }, []);
  
  const fetchHistory = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API}/paper/analytics/history?limit=20`);
      setHistoryData(response.data);
    } catch (error) {
      console.error('Error fetching analytics history:', error);
    } finally {
      setLoading(false);
    }
  };
  
  if (loading) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <LineChartIcon className="w-5 h-5 text-cyan-400" />Historical Analytics
        </h3>
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-6 h-6 text-white/40 animate-spin" />
        </div>
      </div>
    );
  }
  
  const chartData = historyData?.chart_data || {};
  const sessionsCount = historyData?.sessions_count || 0;
  
  if (sessionsCount === 0) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <LineChartIcon className="w-5 h-5 text-cyan-400" />Historical Analytics
        </h3>
        <p className="text-white/40 text-center py-4">
          No historical data yet. Complete a few trading sessions to see trends over time.
        </p>
      </div>
    );
  }
  
  // Prepare efficiency data
  const efficiencyData = chartData.efficiency_trend || [];
  
  // Prepare oracle win rate data (combined)
  const oracleData = (chartData.oracle_win_rates?.high || []).map((item, idx) => ({
    label: item.label,
    'High Trust': item.win_rate,
    'Medium': chartData.oracle_win_rates?.medium?.[idx]?.win_rate || 0,
    'Low Trust': chartData.oracle_win_rates?.low?.[idx]?.win_rate || 0,
  }));
  
  // Session overview data
  const sessionData = (chartData.sessions || []).map(s => ({
    label: s.label,
    pnl: s.total_pnl,
    trades: s.total_trades,
    winRate: s.win_rate
  }));
  
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <LineChartIcon className="w-5 h-5 text-cyan-400" />Historical Analytics
          <span className="text-xs text-white/40 ml-2">({sessionsCount} sessions)</span>
        </h3>
        <button 
          onClick={fetchHistory}
          className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-white/60 hover:text-white transition"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
      
      {/* Chart Type Tabs */}
      <div className="flex gap-2 mb-4">
        {[
          { id: 'efficiency', label: 'Sizing Efficiency', icon: Scale },
          { id: 'oracle', label: 'Win Rate by Oracle', icon: AlertTriangle },
          { id: 'sessions', label: 'Session P&L', icon: TrendingUp }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveChart(tab.id)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              activeChart === tab.id 
                ? 'bg-cyan-500 text-white' 
                : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white'
            }`}
          >
            <tab.icon className="w-3 h-3" />{tab.label}
          </button>
        ))}
      </div>
      
      {/* Sizing Efficiency Chart */}
      {activeChart === 'efficiency' && (
        <div>
          <p className="text-xs text-white/50 mb-3">
            Shows what % of Kelly-calculated size was actually used (lower = more conservative caps applied)
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={efficiencyData}>
              <defs>
                <linearGradient id="efficiencyGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis dataKey="label" tick={{ fill: '#ffffff60', fontSize: 10 }} />
              <YAxis tick={{ fill: '#ffffff60', fontSize: 10 }} domain={[0, 100]} unit="%" />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #ffffff20', borderRadius: '8px' }}
                labelStyle={{ color: '#ffffff' }}
                formatter={(value) => [`${value.toFixed(1)}%`, 'Efficiency']}
              />
              <Area 
                type="monotone" 
                dataKey="efficiency" 
                stroke="#8b5cf6" 
                strokeWidth={2}
                fill="url(#efficiencyGradient)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      
      {/* Oracle Win Rate Chart */}
      {activeChart === 'oracle' && (
        <div>
          <p className="text-xs text-white/50 mb-3">
            Win rates by oracle trust level: High (≥0.9), Medium (0.6-0.9), Low (&lt;0.6)
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={oracleData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis dataKey="label" tick={{ fill: '#ffffff60', fontSize: 10 }} />
              <YAxis tick={{ fill: '#ffffff60', fontSize: 10 }} domain={[0, 100]} unit="%" />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #ffffff20', borderRadius: '8px' }}
                labelStyle={{ color: '#ffffff' }}
                formatter={(value) => [`${value.toFixed(1)}%`]}
              />
              <Legend wrapperStyle={{ fontSize: '10px' }} />
              <Line type="monotone" dataKey="High Trust" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Medium" stroke="#eab308" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Low Trust" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      
      {/* Session P&L Chart */}
      {activeChart === 'sessions' && (
        <div>
          <p className="text-xs text-white/50 mb-3">
            Total P&L and trade count per session
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={sessionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis dataKey="label" tick={{ fill: '#ffffff60', fontSize: 10 }} />
              <YAxis tick={{ fill: '#ffffff60', fontSize: 10 }} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #ffffff20', borderRadius: '8px' }}
                labelStyle={{ color: '#ffffff' }}
                formatter={(value, name) => [
                  name === 'pnl' ? `$${value.toFixed(2)}` : value,
                  name === 'pnl' ? 'P&L' : name === 'trades' ? 'Trades' : 'Win Rate'
                ]}
              />
              <Bar dataKey="pnl" name="P&L">
                {sessionData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      
      {/* Summary Stats */}
      <div className="mt-4 pt-4 border-t border-white/10 grid grid-cols-3 gap-4">
        <div className="text-center">
          <p className="text-xs text-white/40">Avg Efficiency</p>
          <p className="text-lg font-bold text-purple-400">
            {efficiencyData.length > 0 
              ? (efficiencyData.reduce((s, d) => s + d.efficiency, 0) / efficiencyData.length).toFixed(0)
              : 0}%
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-white/40">Best Session P&L</p>
          <p className="text-lg font-bold text-green-400">
            ${sessionData.length > 0 ? Math.max(...sessionData.map(s => s.pnl)).toFixed(2) : '0.00'}
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-white/40">Total Trades</p>
          <p className="text-lg font-bold text-cyan-400">
            {sessionData.reduce((s, d) => s + d.trades, 0)}
          </p>
        </div>
      </div>
    </div>
  );
};

const PositionCard = ({ position, onViewSizing }) => {
  const pnlPct = position.unrealized_pnl_pct || 0;
  const isProfit = pnlPct >= 0;
  
  // Extract sizing breakdown for quick view
  const breakdown = position.sizing_breakdown || {};
  const hasSizerData = breakdown.kelly_base !== undefined;
  
  // Extract expiry info
  const expiryInfo = position.expiry_info || {};
  const hoursToExpiry = expiryInfo.hours_to_expiry;
  const urgency = expiryInfo.urgency || 'normal';
  
  // Extract dynamic exit params
  const exitParams = position.dynamic_exit_params || {};
  const isDynamic = exitParams.is_dynamic !== false;
  const exitMode = exitParams.exit_mode || 'standard';
  const tp = exitParams.tp;
  const sl = exitParams.sl;
  const maxGain = exitParams.max_gain;
  const zone = exitParams.zone || 'unknown';
  
  // Calculate progress to TP/SL
  const getTPProgress = () => {
    if (tp === null || tp === undefined) return null; // Hold to resolution mode
    if (tp === 0) return 100;
    return Math.min(100, Math.max(0, (pnlPct / tp) * 100));
  };
  
  const getSLProgress = () => {
    if (sl === null || sl === undefined) return null; // No SL mode
    if (sl === 0) return 0;
    return Math.min(100, Math.max(0, (pnlPct / sl) * 100));
  };
  
  const tpProgress = getTPProgress();
  const slProgress = getSLProgress();
  
  // Format expiry display
  const getExpiryDisplay = () => {
    if (!hoursToExpiry && hoursToExpiry !== 0) return null;
    if (hoursToExpiry <= 0) return { text: 'Expired', color: 'text-red-500', bg: 'bg-red-500/20' };
    if (hoursToExpiry <= 6) return { text: `${hoursToExpiry.toFixed(1)}h`, color: 'text-red-400', bg: 'bg-red-500/20' };
    if (hoursToExpiry <= 24) return { text: `${hoursToExpiry.toFixed(0)}h`, color: 'text-orange-400', bg: 'bg-orange-500/20' };
    const days = hoursToExpiry / 24;
    if (days <= 7) return { text: `${days.toFixed(0)}d`, color: 'text-yellow-400', bg: 'bg-yellow-500/20' };
    return { text: `${days.toFixed(0)}d`, color: 'text-green-400', bg: 'bg-green-500/20' };
  };
  
  // Get exit mode badge
  const getExitModeBadge = () => {
    const modes = {
      'resolution': { text: 'HOLD→RES', color: 'text-purple-400', bg: 'bg-purple-500/20', desc: 'Holding to resolution' },
      'hold_protected': { text: 'HOLD+SL', color: 'text-blue-400', bg: 'bg-blue-500/20', desc: 'Holding with SL protection' },
      'active': { text: 'ACTIVE', color: 'text-cyan-400', bg: 'bg-cyan-500/20', desc: 'Active TP/SL' },
      'quick_trade': { text: 'QUICK', color: 'text-yellow-400', bg: 'bg-yellow-500/20', desc: 'Quick exit (24h)' },
      'standard': { text: 'STD', color: 'text-white/60', bg: 'bg-white/10', desc: 'Standard exit' },
      'simple': { text: 'SIMPLE', color: 'text-gray-400', bg: 'bg-gray-500/20', desc: 'Simple configurable' }
    };
    return modes[exitMode] || modes['standard'];
  };
  
  const expiryDisplay = getExpiryDisplay();
  const exitModeBadge = getExitModeBadge();
  
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4 hover:bg-white/10 transition-colors">
      {/* Header: Market question and P&L */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white font-medium truncate">{position.market_question}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className={`text-xs px-2 py-0.5 rounded ${position.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{position.side}</span>
            <span className="text-xs text-white/40">{position.strategy}</span>
            {expiryDisplay && (
              <span className={`text-xs px-2 py-0.5 rounded ${expiryDisplay.bg} ${expiryDisplay.color} font-medium`}>
                ⏱️ {expiryDisplay.text}
              </span>
            )}
            {/* Exit Mode Badge */}
            <span className={`text-xs px-2 py-0.5 rounded ${exitModeBadge.bg} ${exitModeBadge.color} font-medium`} title={exitModeBadge.desc}>
              {exitModeBadge.text}
            </span>
          </div>
        </div>
        <div className={`text-right ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
          <p className="text-sm font-bold">{isProfit ? '+' : ''}{(pnlPct * 100).toFixed(2)}%</p>
          {maxGain !== null && maxGain !== undefined && (
            <p className="text-xs text-white/40">Max: {(maxGain * 100).toFixed(0)}%</p>
          )}
        </div>
      </div>
      
      {/* Compact Sizing Breakdown - NEW */}
      {hasSizerData && (
        <div className="mb-3 p-2 bg-gradient-to-r from-cyan-500/10 to-purple-500/10 rounded-lg border border-cyan-500/20">
          <div className="flex items-center justify-between text-[10px] mb-1">
            <span className="text-white/50">SIZING ENGINE</span>
            <button 
              onClick={() => onViewSizing && onViewSizing(position)}
              className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
              data-testid="view-sizing-btn"
            >
              <Eye className="w-3 h-3" /> Details
            </button>
          </div>
          <div className="grid grid-cols-4 gap-2 text-center">
            <div>
              <p className="text-[9px] text-white/40">EDGE</p>
              <p className={`text-xs font-bold ${(breakdown.edge || 0) > 0.03 ? 'text-green-400' : 'text-yellow-400'}`}>
                +{((breakdown.edge || 0) * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-[9px] text-white/40">KELLY</p>
              <p className="text-xs font-bold text-purple-400">${(breakdown.kelly_base || 0).toFixed(0)}</p>
            </div>
            <div>
              <p className="text-[9px] text-white/40">ORACLE</p>
              <p className={`text-xs font-bold ${(breakdown.oracle_mult || 1) < 0.6 ? 'text-red-400' : 'text-green-400'}`}>
                ×{(breakdown.oracle_mult || 1).toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-[9px] text-white/40">FINAL</p>
              <p className="text-xs font-bold text-cyan-400">${(breakdown.final_size || position.size || 0).toFixed(0)}</p>
            </div>
          </div>
        </div>
      )}
      
      {/* Dynamic Exit Progress Bars */}
      {isDynamic && (tp !== null || sl !== null) && (
        <div className="mb-3 space-y-2">
          {/* TP Progress */}
          {tp !== null && tp !== undefined && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-green-400 w-8">TP</span>
              <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-green-500 transition-all duration-300"
                  style={{ width: `${Math.max(0, tpProgress)}%` }}
                />
              </div>
              <span className="text-xs text-white/60 w-12 text-right">{(tp * 100).toFixed(1)}%</span>
            </div>
          )}
          {/* SL Progress */}
          {sl !== null && sl !== undefined && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-red-400 w-8">SL</span>
              <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-red-500 transition-all duration-300"
                  style={{ width: `${Math.max(0, slProgress)}%` }}
                />
              </div>
              <span className="text-xs text-white/60 w-12 text-right">{(sl * 100).toFixed(1)}%</span>
            </div>
          )}
        </div>
      )}
      
      {/* Hold to Resolution indicator */}
      {exitMode === 'resolution' && (
        <div className="mb-3 px-3 py-2 bg-purple-500/10 rounded border border-purple-500/30">
          <p className="text-xs text-purple-300 text-center">🎯 Holding to market resolution</p>
        </div>
      )}
      
      {/* Position Details */}
      <div className="flex items-center justify-between text-xs text-white/40">
        <span>Entry: ${position.entry_price?.toFixed(4)}</span>
        <span>Size: ${position.size?.toFixed(2)}</span>
        <span>RL: {((position.rl_confidence || 0) * 100).toFixed(0)}%</span>
      </div>
      
      {/* Zone indicator */}
      {zone && zone !== 'unknown' && (
        <div className="mt-2 flex items-center justify-between text-xs">
          <span className="text-white/30">Zone: <span className="text-white/50 capitalize">{zone}</span></span>
          {exitParams.max_hours && (
            <span className="text-white/30">Max Hold: <span className="text-white/50">{exitParams.max_hours}h</span></span>
          )}
        </div>
      )}
    </div>
  );
};

// Trade Row Component - Shows both open (ENTRY) and completed trades
const TradeRow = ({ trade, onViewSentiment }) => {
  const isEntry = trade.type === 'entry';
  const isComplete = trade.type === 'exit';
  
  const entryPrice = isEntry ? (trade.price || 0) : (trade.entry_price || 0);
  const exitPrice = isComplete ? (trade.exit_price || trade.price || 0) : null;
  const pnl = trade.pnl || 0;
  const isProfit = pnl > 0;
  
  // Calculate return percentage based on actual P&L vs position size
  // This correctly handles YES/NO sides since P&L already accounts for direction
  const returnPct = isComplete && trade.size > 0 ? (pnl / trade.size * 100) : 0;
  
  // Check if trade has sentiment data
  const hasSentiment = trade.sentiment && (trade.sentiment.final !== undefined || trade.sentiment.layers);
  
  // Extract expiry info for display
  const expiryInfo = trade.expiry_info || {};
  const hoursToExpiry = expiryInfo.hours_to_expiry;
  
  // Format expiry badge
  const getExpiryBadge = () => {
    if (!hoursToExpiry && hoursToExpiry !== 0) return null;
    if (hoursToExpiry <= 0) return { text: 'EXP', color: 'text-red-500', bg: 'bg-red-500/20' };
    if (hoursToExpiry <= 6) return { text: `${hoursToExpiry.toFixed(0)}h`, color: 'text-red-400', bg: 'bg-red-500/20' };
    if (hoursToExpiry <= 24) return { text: `${hoursToExpiry.toFixed(0)}h`, color: 'text-orange-400', bg: 'bg-orange-500/20' };
    const days = hoursToExpiry / 24;
    if (days <= 7) return { text: `${days.toFixed(0)}d`, color: 'text-yellow-400', bg: 'bg-yellow-500/20' };
    return { text: `${days.toFixed(0)}d`, color: 'text-green-400', bg: 'bg-green-500/20' };
  };
  
  const expiryBadge = getExpiryBadge();
  
  // Format exit reason for display
  const getExitReasonBadge = (reason) => {
    if (!reason) return null;
    const reasonMap = {
      'take_profit': { text: 'TP', color: 'text-green-400', bg: 'bg-green-500/20', title: 'Take Profit Hit' },
      'stop_loss': { text: 'SL', color: 'text-red-400', bg: 'bg-red-500/20', title: 'Stop Loss Hit' },
      'time_limit': { text: '⏱️', color: 'text-yellow-400', bg: 'bg-yellow-500/20', title: 'Max Hold Time' },
      'rl_signal_reversal': { text: 'RL', color: 'text-purple-400', bg: 'bg-purple-500/20', title: 'RL Signal Reversal' },
      'session_end': { text: 'END', color: 'text-slate-400', bg: 'bg-slate-500/20', title: 'Session Ended' },
    };
    if (reason.startsWith('expiry_safety_exit')) {
      return { text: '⚠️EXP', color: 'text-orange-400', bg: 'bg-orange-500/20', title: 'Auto-Exit: Approaching Expiry' };
    }
    return reasonMap[reason] || { text: reason.slice(0, 4).toUpperCase(), color: 'text-white/60', bg: 'bg-white/10', title: reason };
  };
  
  const exitReasonBadge = isComplete ? getExitReasonBadge(trade.exit_reason) : null;
  
  // Determine status badge based on P&L outcome
  const getStatusBadge = () => {
    if (isEntry) {
      return { text: 'OPEN', color: 'text-blue-400', bg: 'bg-blue-500/20' };
    }
    // For closed trades, show TP/SL/FLAT based on actual P&L
    if (pnl > 0) {
      return { text: 'TP', color: 'text-green-400', bg: 'bg-green-500/20', title: 'Take Profit' };
    } else if (pnl < 0) {
      return { text: 'SL', color: 'text-red-400', bg: 'bg-red-500/20', title: 'Stop Loss' };
    } else {
      return { text: 'FLAT', color: 'text-white/60', bg: 'bg-white/10', title: 'Break Even' };
    }
  };
  
  const statusBadge = getStatusBadge();
  
  return (
    <tr className="border-b border-white/5 hover:bg-white/5">
      <td className="py-3 px-4">
        <div className="flex items-center gap-1">
          <span 
            className={`text-xs px-2 py-1 rounded font-medium ${statusBadge.bg} ${statusBadge.color}`}
            title={statusBadge.title}
          >
            {statusBadge.text}
          </span>
          {isEntry && expiryBadge && (
            <span className={`text-xs px-1.5 py-0.5 rounded ${expiryBadge.bg} ${expiryBadge.color}`} title={`Expires in ${expiryBadge.text}`}>
              ⏱️{expiryBadge.text}
            </span>
          )}
        </div>
      </td>
      <td className="py-3 px-4 text-sm text-white/80 max-w-xs truncate" title={trade.market_question || trade.market_id}>
        {trade.market_question || trade.market_id?.substring(0, 30) + '...'}
      </td>
      <td className="py-3 px-4 text-sm text-white/60">{STRATEGY_INFO[trade.strategy]?.name || trade.strategy}</td>
      <td className="py-3 px-4">
        <span className={`text-xs px-2 py-0.5 rounded ${trade.side === 'YES' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
          {trade.side}
        </span>
      </td>
      <td className="py-3 px-4 text-sm text-white/80">${trade.size?.toFixed(2)}</td>
      <td className="py-3 px-4 text-sm">
        {isEntry ? (
          <span className="text-cyan-400">${entryPrice.toFixed(4)}</span>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-cyan-400">${entryPrice.toFixed(4)}</span>
            <span className="text-white/30">→</span>
            <span className="text-amber-400">${exitPrice?.toFixed(4)}</span>
          </div>
        )}
      </td>
      <td className={`py-3 px-4 text-sm font-bold ${isEntry ? 'text-white/40' : isProfit ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-white/40'}`}>
        {isEntry ? '-' : (isProfit ? '+' : '') + pnl.toFixed(2)}
      </td>
      <td className={`py-3 px-4 text-sm font-medium ${isEntry ? 'text-white/40' : returnPct > 0 ? 'text-green-400' : returnPct < 0 ? 'text-red-400' : 'text-white/40'}`}>
        {isEntry ? '-' : (returnPct > 0 ? '+' : '') + returnPct.toFixed(2) + '%'}
      </td>
      <td className="py-3 px-4 text-xs text-white/40">{new Date(trade.timestamp).toLocaleTimeString()}</td>
      <td className="py-3 px-4">
        {hasSentiment && onViewSentiment && (
          <button
            onClick={() => onViewSentiment(trade)}
            className="p-1.5 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition"
            title="View Sentiment Analysis"
          >
            <Brain className="w-3.5 h-3.5" />
          </button>
        )}
      </td>
    </tr>
  );
};

// Sortable Table Header Component
const SortableHeader = ({ label, sortKey, currentSort, onSort }) => {
  const isActive = currentSort.key === sortKey;
  const isAsc = currentSort.direction === 'asc';
  
  return (
    <th 
      className="py-3 px-4 text-xs text-white/60 uppercase cursor-pointer hover:text-white hover:bg-white/5 transition select-none"
      onClick={() => onSort(sortKey)}
    >
      <div className="flex items-center gap-1">
        {label}
        <span className={`text-[10px] ${isActive ? 'text-cyan-400' : 'text-white/30'}`}>
          {isActive ? (isAsc ? '▲' : '▼') : '⇅'}
        </span>
      </div>
    </th>
  );
};

// Performance Table with Totals Component
const PerformanceTable = ({ title, icon: Icon, iconColor, data, dataType, showLiveBadge, initialCapital = 10000 }) => {
  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
        <div className="p-4 border-b border-white/10">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Icon className={`w-5 h-5 text-${iconColor}-400`} />{title}
          </h3>
        </div>
        <div className="p-8 text-center text-white/40">No data yet - start paper trading</div>
      </div>
    );
  }

  // Normalize data to handle both cumulative (total_pnl) and live (pnl) formats
  const normalizedData = Object.fromEntries(
    Object.entries(data).map(([key, d]) => [
      key,
      {
        total_pnl: d.total_pnl ?? d.pnl ?? 0,
        total_trades: d.total_trades ?? d.trades ?? 0,
        total_wins: d.total_wins ?? d.wins ?? 0,
        win_rate: d.win_rate ?? 0,
        sessions: d.sessions ?? 0
      }
    ])
  );

  const entries = Object.entries(normalizedData).sort((a, b) => b[1].total_pnl - a[1].total_pnl);
  
  // Calculate totals
  const totals = entries.reduce((acc, [_, d]) => ({
    total_pnl: acc.total_pnl + (d.total_pnl || 0),
    total_trades: acc.total_trades + (d.total_trades || 0),
    total_wins: acc.total_wins + (d.total_wins || 0),
    sessions: acc.sessions + (d.sessions || 0)
  }), { total_pnl: 0, total_trades: 0, total_wins: 0, sessions: 0 });
  
  totals.win_rate = totals.total_trades > 0 ? totals.total_wins / totals.total_trades : 0;
  const totalReturnPct = (totals.total_pnl / initialCapital) * 100;
  
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
      <div className="p-4 border-b border-white/10 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <Icon className={`w-5 h-5 text-${iconColor}-400`} />{title}
        </h3>
        {showLiveBadge && (
          <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-[10px] flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></div>LIVE
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-white/5 text-left">
              <th className="py-2 px-3 text-xs text-white/60 uppercase">{dataType === 'strategy' ? 'Strategy' : 'Asset Class'}</th>
              <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">P&L</th>
              <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">% Return</th>
              <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Trades</th>
              <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Win Rate</th>
              <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Wins</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, rowData]) => {
              const isPositive = rowData.total_pnl >= 0;
              const returnPct = (rowData.total_pnl / initialCapital) * 100;
              const info = dataType === 'strategy' ? STRATEGY_INFO[key] : null;
              return (
                <tr key={key} className="border-b border-white/5 hover:bg-white/5">
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-2">
                      {dataType === 'strategy' && <div className="w-2 h-2 rounded-full" style={{ backgroundColor: info?.color }} />}
                      <span className="text-sm text-white capitalize">{info?.name || key}</span>
                    </div>
                  </td>
                  <td className={`py-2 px-3 text-right text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                    {isPositive ? '+' : ''}${rowData.total_pnl?.toFixed(2)}
                  </td>
                  <td className={`py-2 px-3 text-right text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                    {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
                  </td>
                  <td className="py-2 px-3 text-right text-sm text-white font-bold">{rowData.total_trades}</td>
                  <td className={`py-2 px-3 text-right text-sm ${rowData.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                    {(rowData.win_rate * 100).toFixed(1)}%
                  </td>
                  <td className="py-2 px-3 text-right text-sm text-white/60">{rowData.total_wins}</td>
                </tr>
              );
            })}
            {/* Totals Row */}
            <tr className="bg-white/10 font-bold border-t-2 border-white/20">
              <td className="py-3 px-3 text-white">TOTAL</td>
              <td className={`py-3 px-3 text-right text-lg ${totals.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {totals.total_pnl >= 0 ? '+' : ''}${totals.total_pnl.toFixed(2)}
              </td>
              <td className={`py-3 px-3 text-right ${totalReturnPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {totalReturnPct >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}%
              </td>
              <td className="py-3 px-3 text-right text-white text-lg">{totals.total_trades}</td>
              <td className={`py-3 px-3 text-right ${totals.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                {(totals.win_rate * 100).toFixed(1)}%
              </td>
              <td className="py-3 px-3 text-right text-white">{totals.total_wins}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};

// P&L Distribution Chart Component
const PnLDistributionChart = ({ data, title = "P&L Distribution" }) => {
  if (!data?.bins || data.bins.length === 0) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-purple-400" />{title}
        </h3>
        <div className="h-56 flex items-center justify-center text-white/40">
          No trade data yet - start paper trading to see distribution
        </div>
      </div>
    );
  }

  const filteredBins = data.bins.filter(b => b.count > 0);
  
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-purple-400" />{title}
          <span className="text-xs text-white/40 ml-2">({filteredBins.length} bins)</span>
        </h3>
        {data.stats && (
          <div className="flex items-center gap-4 text-xs">
            <span className="text-white/50">Mean: <span className={data.stats.mean >= 0 ? 'text-green-400' : 'text-red-400'}>{data.stats.mean?.toFixed(2)}%</span></span>
            <span className="text-white/50">Median: <span className="text-cyan-400">{data.stats.median?.toFixed(2)}%</span></span>
            <span className="text-white/50">Std Dev: <span className="text-purple-400">{data.stats.std?.toFixed(2)}%</span></span>
          </div>
        )}
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={filteredBins} margin={{ top: 10, right: 30, left: 0, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis 
              dataKey="label" 
              stroke="rgba(255,255,255,0.5)" 
              tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.6)' }}
              angle={-45}
              textAnchor="end"
              interval={0}
              height={60}
            />
            <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.6)' }} />
            <Tooltip 
              contentStyle={{
                backgroundColor: 'rgba(15,23,42,0.98)', 
                border: '1px solid rgba(255,255,255,0.2)', 
                borderRadius: '8px',
                padding: '12px 16px',
                boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
              }}
              labelStyle={{ color: '#e2e8f0', fontWeight: 'bold', fontSize: '13px', marginBottom: '4px' }}
              itemStyle={{ color: '#94a3b8', fontSize: '12px' }}
              formatter={(value, name) => [<span style={{color: '#22d3ee', fontWeight: 'bold'}}>{value} trades</span>, 'Count']}
              labelFormatter={(label) => <span style={{color: '#f1f5f9'}}>Return Range: {label}</span>}
              cursor={{ fill: 'rgba(255,255,255,0.1)' }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {filteredBins.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.min >= 0 ? '#10b981' : '#ef4444'} fillOpacity={0.8} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {data.stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-white/10">
          <div className="text-center">
            <p className="text-xs text-white/50">Positive</p>
            <p className="text-lg font-bold text-green-400">{data.stats.positive_returns || 0}</p>
          </div>
          <div className="text-center">
            <p className="text-xs text-white/50">Negative</p>
            <p className="text-lg font-bold text-red-400">{data.stats.negative_returns || 0}</p>
          </div>
          <div className="text-center">
            <p className="text-xs text-white/50">Skewness</p>
            <p className={`text-lg font-bold ${(data.stats.skewness || 0) > 0 ? 'text-green-400' : 'text-yellow-400'}`}>
              {data.stats.skewness?.toFixed(2) || '0.00'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs text-white/50">Kurtosis</p>
            <p className="text-lg font-bold text-purple-400">{data.stats.kurtosis?.toFixed(2) || '0.00'}</p>
          </div>
        </div>
      )}
    </div>
  );
};

const PaperTrading = () => {
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState(null);
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [optimizerParams, setOptimizerParams] = useState(null);
  const [rlStats, setRlStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('live');
  const [selectedSession, setSelectedSession] = useState(null);
  const [continuousMode, setContinuousMode] = useState(false);
  const [aiStats, setAiStats] = useState(null);
  const [showStopOptions, setShowStopOptions] = useState(false);
  const [cumulativeStats, setCumulativeStats] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [savedConfig, setSavedConfig] = useState(null);
  const [liveSessionDuration, setLiveSessionDuration] = useState(0);  // Live timer in seconds
  
  // Modal states
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null });
  const [sessionTradesModal, setSessionTradesModal] = useState({ isOpen: false, session: null, trades: [] });
  const [sentimentModal, setSentimentModal] = useState({ isOpen: false, trade: null });
  const [sizingModal, setSizingModal] = useState({ isOpen: false, position: null });
  
  // Exit mode state (Dynamic vs Simple)
  const [useDynamicExit, setUseDynamicExit] = useState(true);
  const [dynamicExitConfig, setDynamicExitConfig] = useState(null);
  
  // Sorting state for trades table
  const [tradeSort, setTradeSort] = useState({ key: 'timestamp', direction: 'desc' });

  // Sort handler
  const handleTradeSort = (key) => {
    setTradeSort(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  // Sort trades based on current sort state
  const sortedTrades = [...trades].sort((a, b) => {
    const dir = tradeSort.direction === 'asc' ? 1 : -1;
    const key = tradeSort.key;
    
    // Handle different sort keys
    switch (key) {
      case 'type':
        return dir * (a.type || '').localeCompare(b.type || '');
      case 'market':
        return dir * ((a.market_question || a.market_id || '').localeCompare(b.market_question || b.market_id || ''));
      case 'strategy':
        return dir * (a.strategy || '').localeCompare(b.strategy || '');
      case 'side':
        return dir * (a.side || '').localeCompare(b.side || '');
      case 'size':
        return dir * ((a.size || 0) - (b.size || 0));
      case 'entry':
        const aEntry = a.type === 'entry' ? (a.price || 0) : (a.entry_price || 0);
        const bEntry = b.type === 'entry' ? (b.price || 0) : (b.entry_price || 0);
        return dir * (aEntry - bEntry);
      case 'pnl':
        return dir * ((a.pnl || 0) - (b.pnl || 0));
      case 'return':
        // Calculate return % based on P&L / size (not price difference)
        const aReturn = a.type === 'exit' && a.size > 0 ? ((a.pnl || 0) / a.size * 100) : 0;
        const bReturn = b.type === 'exit' && b.size > 0 ? ((b.pnl || 0) / b.size * 100) : 0;
        return dir * (aReturn - bReturn);
      case 'timestamp':
      default:
        return dir * (new Date(a.timestamp || 0) - new Date(b.timestamp || 0));
    }
  });

  // Fetch saved config
  const fetchSavedConfig = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/config`);
      setSavedConfig(response.data);
    } catch (e) {
      console.error('Error fetching saved config:', e);
    }
  }, []);

  // WebSocket connection
  useEffect(() => {
    let ws = null;
    let reconnectTimeout = null;
    const connectWs = () => {
      try {
        const wsUrl = BACKEND_URL.replace('https', 'wss').replace('http', 'ws') + '/ws';
        ws = new WebSocket(wsUrl);
        ws.onopen = () => { setWsConnected(true); };
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'paper_trade') {
              setTrades(prev => [data.trade, ...prev].slice(0, 50));
              fetchData();
            } else if (data.type === 'paper_position_update') {
              setPositions(data.positions || []);
            } else if (data.type === 'paper_status_update') {
              setStatus(data.status);
              setRunning(data.status?.running || false);
            }
          } catch (e) { console.error('WS parse error:', e); }
        };
        ws.onclose = () => { setWsConnected(false); reconnectTimeout = setTimeout(connectWs, 5000); };
        ws.onerror = () => { setWsConnected(false); };
      } catch (e) { setWsConnected(false); }
    };
    connectWs();
    return () => { if (ws) ws.close(); if (reconnectTimeout) clearTimeout(reconnectTimeout); };
  }, []);

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        axios.get(`${API}/paper/status`),
        axios.get(`${API}/paper/positions`),
        axios.get(`${API}/paper/trades?limit=50`),
        axios.get(`${API}/paper/analytics`)
      ]);
      if (results[0].status === 'fulfilled') {
        setStatus(results[0].value.data);
        setRunning(results[0].value.data?.running || false);
        setContinuousMode(results[0].value.data?.continuous_mode || false);
      }
      if (results[1].status === 'fulfilled') setPositions(results[1].value.data?.positions || []);
      if (results[2].status === 'fulfilled') setTrades(results[2].value.data?.trades || []);
      if (results[3].status === 'fulfilled') setAnalytics(results[3].value.data);
    } catch (e) { console.error('Error fetching data:', e); }
  }, []);

  const fetchAiStats = async () => {
    try { const r = await axios.get(`${API}/paper/ai-stats`); setAiStats(r.data?.ai_stats); } catch (e) {}
  };

  const fetchCumulativeStats = async () => {
    try { const r = await axios.get(`${API}/paper/cumulative-stats`); setCumulativeStats(r.data); } catch (e) {}
  };

  const fetchSessions = async () => {
    try { const r = await axios.get(`${API}/paper/sessions?limit=20`); setSessions(r.data?.sessions || []); } catch (e) {}
  };

  const fetchRlStats = async () => {
    try { const r = await axios.get(`${API}/rl/detailed-stats`); setRlStats(r.data?.rl_stats || r.data); } catch (e) {}
  };

  const fetchOptimizerParams = async () => {
    try { const r = await axios.get(`${API}/optimizer/params`); setOptimizerParams(r.data?.params); } catch (e) {}
  };

  useEffect(() => {
    fetchData(); fetchSessions(); fetchRlStats(); fetchOptimizerParams(); fetchAiStats(); fetchCumulativeStats(); fetchExitModeConfig();
    const pollingInterval = wsConnected ? 10000 : 5000;
    const interval = setInterval(() => {
      fetchData(); fetchCumulativeStats(); fetchSavedConfig();
      if (running) { fetchRlStats(); fetchAiStats(); }
    }, pollingInterval);
    return () => clearInterval(interval);
  }, [fetchData, running, wsConnected, fetchSavedConfig]);

  useEffect(() => { fetchSavedConfig(); }, [fetchSavedConfig]);

  // Live session timer - updates every second when running
  useEffect(() => {
    let interval;
    if (status?.running && status?.start_time) {
      // Calculate initial duration
      const startTime = new Date(status.start_time).getTime();
      const updateDuration = () => {
        const now = Date.now();
        const durationSecs = Math.floor((now - startTime) / 1000);
        setLiveSessionDuration(durationSecs);
      };
      
      updateDuration(); // Initial calculation
      interval = setInterval(updateDuration, 1000); // Update every second
    } else {
      setLiveSessionDuration(0);
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [status?.running, status?.start_time]);

  const startPaperTrading = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`${API}/paper/start?continuous_mode=${continuousMode}`, {}, AUTH_CONFIG);
      toast.success(`Paper trading started! Session: ${response.data.session_id}${continuousMode ? ' (Continuous)' : ''}`);
      setRunning(true);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Failed to start'); }
    finally { setLoading(false); }
  };

  const stopPaperTrading = async (graceful = false) => {
    setLoading(true); setShowStopOptions(false);
    try {
      const response = await axios.post(`${API}/paper/stop?graceful=${graceful}`, {}, AUTH_CONFIG);
      toast.success(graceful ? 'Graceful stop initiated' : 'Paper trading stopped');
      if (!graceful) setRunning(false);
      setStatus(response.data?.final_status);
      fetchSessions();
    } catch (e) { toast.error('Failed to stop'); }
    finally { setLoading(false); }
  };

  // Toggle exit mode (Dynamic vs Simple)
  const toggleExitMode = async () => {
    try {
      const newMode = !useDynamicExit;
      const response = await axios.post(`${API}/paper/exit-mode?use_dynamic=${newMode}`, {}, AUTH_CONFIG);
      setUseDynamicExit(newMode);
      toast.success(response.data?.message || `Exit mode: ${newMode ? 'Dynamic' : 'Simple'}`);
    } catch (e) { 
      toast.error('Failed to toggle exit mode'); 
    }
  };

  // Fetch exit mode config
  const fetchExitModeConfig = async () => {
    try {
      const response = await axios.get(`${API}/paper/exit-mode`, AUTH_CONFIG);
      setUseDynamicExit(response.data?.use_dynamic_exit ?? true);
      setDynamicExitConfig(response.data?.dynamic_exit_config);
    } catch (e) { 
      console.error('Failed to fetch exit mode config'); 
    }
  };

  // Reset handlers
  const handleResetLiveSession = () => {
    setConfirmModal({
      isOpen: true,
      title: 'Reset Live Session Data',
      message: 'This will clear all live session statistics, equity curves, and trade history. The session will continue running but stats will restart from zero. Are you sure?',
      onConfirm: async () => {
        try {
          await axios.post(`${API}/paper/reset-live-stats`, {}, AUTH_CONFIG);
          toast.success('Live session stats reset');
          fetchData();
        } catch (e) { toast.error('Failed to reset'); }
        setConfirmModal({ isOpen: false });
      }
    });
  };

  const handleResetCumulativeStats = () => {
    setConfirmModal({
      isOpen: true,
      title: 'Reset Cumulative Statistics',
      message: 'This will permanently delete ALL cumulative trading statistics across all sessions. This action cannot be undone. Are you sure?',
      onConfirm: async () => {
        try {
          await axios.post(`${API}/paper/reset-cumulative-stats`, {}, AUTH_CONFIG);
          toast.success('Cumulative stats reset');
          fetchCumulativeStats();
        } catch (e) { toast.error('Failed to reset'); }
        setConfirmModal({ isOpen: false });
      }
    });
  };

  const viewSessionTrades = async (session) => {
    try {
      const response = await axios.get(`${API}/paper/session/${session.session_id}/trades`);
      setSessionTradesModal({ isOpen: true, session, trades: response.data?.trades || [] });
    } catch (e) {
      toast.error('Failed to load session trades');
    }
  };

  const trainRLFromSession = async () => {
    try { toast.info('Training RL...'); await axios.post(`${API}/rl/train`, {}, AUTH_CONFIG); toast.success('RL training complete!'); fetchRlStats(); fetchAiStats(); } catch (e) { toast.error('RL training failed'); }
  };

  const runOptimization = async (sessionId) => {
    try { toast.info('Optimizing...'); const r = await axios.post(`${API}/optimizer/run/${sessionId}`, {}, AUTH_CONFIG); toast.success('Optimization complete!'); setOptimizerParams(r.data?.new_params); fetchOptimizerParams(); } catch (e) { toast.error('Optimization failed'); }
  };

  const applyOptimizedParams = async () => {
    try { await axios.post(`${API}/optimizer/apply`, {}, AUTH_CONFIG); toast.success('Parameters applied!'); } catch (e) { toast.error('Failed to apply'); }
  };

  // Prepare equity curve data with initial capital as starting point
  const initialCapital = savedConfig?.initial_capital || 10000;
  
  const prepareEquityCurveData = (equityCurve) => {
    if (!equityCurve || equityCurve.length === 0) return [];
    return equityCurve.map(point => ({
      ...point,
      total_equity: initialCapital + (point.pnl || 0),
      delta_neutral_pnl: point.delta_neutral_pnl || 0,
      volatility_pnl: point.volatility_pnl || 0,
      alpha_pnl: point.alpha_pnl || 0,
      arbitrage_pnl: point.arbitrage_pnl || 0
    }));
  };

  const prepareAssetClassEquityCurve = (equityCurve) => {
    if (!equityCurve || equityCurve.length === 0) return [];
    return equityCurve.map(point => {
      const flatPoint = { ...point, total_equity: initialCapital + (point.pnl || 0) };
      if (point.asset_class_equity) {
        Object.entries(point.asset_class_equity).forEach(([ac, val]) => {
          flatPoint[`ac_${ac}`] = val;
        });
      }
      return flatPoint;
    });
  };

  const TAB_CONFIG = [
    { id: 'live', label: 'Live Session', icon: Activity, color: 'cyan' },
    { id: 'cumulative', label: 'Cumulative Stats', icon: TrendingUp, color: 'emerald' },
    { id: 'history', label: `Sessions (${sessions.length})`, icon: History, color: 'blue' },
    { id: 'optimizer', label: 'Strategy Optimizer', icon: Settings, color: 'amber' },
    { id: 'rl', label: 'RL Learning', icon: Brain, color: 'purple' }
  ];

  return (
    <div className="space-y-6" data-testid="paper-trading-page">
      {/* Confirmation Modal */}
      <ConfirmModal 
        isOpen={confirmModal.isOpen}
        title={confirmModal.title}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm}
        onCancel={() => setConfirmModal({ isOpen: false })}
      />

      {/* Session Trades Modal */}
      <SessionTradesModal
        isOpen={sessionTradesModal.isOpen}
        session={sessionTradesModal.session}
        trades={sessionTradesModal.trades}
        onClose={() => setSessionTradesModal({ isOpen: false, session: null, trades: [] })}
      />
      
      {/* Sentiment Analysis Modal */}
      <SentimentModal
        isOpen={sentimentModal.isOpen}
        trade={sentimentModal.trade}
        onClose={() => setSentimentModal({ isOpen: false, trade: null })}
      />
      
      {/* Sizing Breakdown Modal */}
      <SizingBreakdownModal
        isOpen={sizingModal.isOpen}
        position={sizingModal.position}
        onClose={() => setSizingModal({ isOpen: false, position: null })}
      />

      {/* Header */}
      <div className="rounded-xl bg-slate-900/50 border border-white/10 overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
                <FileText className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">Paper Trading</h1>
                <p className="text-xs text-white/50">Simulate live trading with RL learning</p>
              </div>
            </div>
            
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${
              status?.circuit_breaker_triggered 
                ? 'bg-red-500/30 border-2 border-red-500/60 shadow-[0_0_20px_rgba(239,68,68,0.3)]' 
                : running 
                  ? status?.graceful_stop 
                    ? 'bg-amber-500/20 border border-amber-500/40' 
                    : 'bg-emerald-500/20 border border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.2)]' 
                  : 'bg-slate-800/50 border border-white/10'
            }`}>
              <div className={`w-2 h-2 rounded-full ${
                status?.circuit_breaker_triggered 
                  ? 'bg-red-500 animate-pulse' 
                  : running 
                    ? status?.graceful_stop 
                      ? 'bg-amber-400 animate-pulse' 
                      : 'bg-emerald-400 animate-pulse' 
                    : 'bg-slate-500'
              }`}></div>
              <span className={`text-xs font-mono uppercase tracking-wider ${
                status?.circuit_breaker_triggered 
                  ? 'text-red-400 font-bold' 
                  : running 
                    ? status?.graceful_stop 
                      ? 'text-amber-400' 
                      : 'text-emerald-400' 
                    : 'text-slate-400'
              }`}>
                {status?.circuit_breaker_triggered 
                  ? '🚨 CIRCUIT BREAKER' 
                  : running 
                    ? status?.graceful_stop 
                      ? 'CLOSING' 
                      : status?.continuous_mode 
                        ? 'CONTINUOUS' 
                        : 'TRADING' 
                    : 'STOPPED'}
              </span>
            </div>
            
            {/* Live Session Timer */}
            {running && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800/50 border border-white/10">
                <Clock className="w-3 h-3 text-cyan-400" />
                <span className="text-xs font-mono text-cyan-400">{formatDuration(liveSessionDuration)}</span>
              </div>
            )}
            
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded ${wsConnected ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
              {wsConnected ? <Wifi className="w-3 h-3 text-emerald-400" /> : <WifiOff className="w-3 h-3 text-rose-400" />}
              <span className={`text-[10px] font-mono ${wsConnected ? 'text-emerald-400' : 'text-rose-400'}`}>{wsConnected ? 'LIVE' : 'POLL'}</span>
            </div>
            
            {/* Compact Exit Mode Toggle */}
            <button 
              onClick={toggleExitMode}
              disabled={!running}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition-all ${
                useDynamicExit 
                  ? 'bg-cyan-500/20 border border-cyan-500/30 hover:bg-cyan-500/30' 
                  : 'bg-gray-500/20 border border-gray-500/30 hover:bg-gray-500/30'
              } disabled:opacity-40 disabled:cursor-not-allowed`}
              title={useDynamicExit ? 'Dynamic: Time-aware TP/SL' : 'Simple: Fixed TP/SL per strategy'}
            >
              {useDynamicExit ? <Sparkles className="w-3 h-3 text-cyan-400" /> : <Target className="w-3 h-3 text-gray-400" />}
              <span className={`text-[10px] font-medium ${useDynamicExit ? 'text-cyan-400' : 'text-gray-400'}`}>
                {useDynamicExit ? 'DYNAMIC' : 'SIMPLE'}
              </span>
            </button>
          </div>
          
          <div className="flex items-center gap-3">
            {running ? (
              <div className="relative">
                <button onClick={() => setShowStopOptions(!showStopOptions)} disabled={loading || status?.graceful_stop}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-rose-500 text-white font-bold hover:bg-rose-600 transition-all shadow-lg" data-testid="stop-paper-trading-btn">
                  <Square className="w-4 h-4" />{status?.graceful_stop ? 'Closing...' : 'Stop Session'}
                </button>
                {showStopOptions && (
                  <>
                    <div className="fixed inset-0 z-[90]" onClick={() => setShowStopOptions(false)}></div>
                    <div className="fixed top-20 right-8 w-72 rounded-xl bg-slate-800 border-2 border-white/20 shadow-2xl z-[100] overflow-hidden">
                      <div className="p-3 border-b border-white/10 bg-slate-900"><p className="text-sm text-white font-medium">Choose stop method:</p></div>
                      <button onClick={() => stopPaperTrading(false)} className="w-full px-4 py-4 text-left hover:bg-rose-500/20 flex items-center gap-3 transition-colors border-b border-white/5">
                        <div className="w-10 h-10 rounded-lg bg-rose-500/20 flex items-center justify-center"><Square className="w-5 h-5 text-rose-400" /></div>
                        <div><p className="text-white font-bold">Immediate Stop</p><p className="text-xs text-white/50">Close all positions now</p></div>
                      </button>
                      <button onClick={() => stopPaperTrading(true)} className="w-full px-4 py-4 text-left hover:bg-amber-500/20 flex items-center gap-3 transition-colors">
                        <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center"><Clock className="w-5 h-5 text-amber-400" /></div>
                        <div><p className="text-white font-bold">Graceful Stop</p><p className="text-xs text-white/50">Wait for TP/SL triggers</p></div>
                      </button>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <button onClick={startPaperTrading} disabled={loading}
                className="flex items-center gap-2 px-8 py-3 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-black text-base transition-all shadow-[0_0_30px_rgba(6,182,212,0.4)] hover:shadow-[0_0_40px_rgba(6,182,212,0.6)] hover:scale-105"
                data-testid="start-paper-trading-btn">
                <Play className="w-5 h-5" />START TRADING
              </button>
            )}
          </div>
        </div>
        
        <div className="flex items-center justify-between px-4 py-3 bg-slate-950/50">
          <div className="flex items-center gap-4">
            <span className="text-xs text-white/40 uppercase tracking-wider font-medium">Mode:</span>
            <div className="flex rounded-lg overflow-hidden border-2 border-white/20 shadow-lg">
              <button onClick={() => setContinuousMode(false)} disabled={running} data-testid="mode-single-btn"
                className={`px-5 py-2.5 text-sm font-bold transition-all flex items-center gap-2 ${!continuousMode ? 'bg-cyan-500 text-black shadow-[0_0_20px_rgba(6,182,212,0.4)]' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'} ${running ? 'opacity-50 cursor-not-allowed' : ''}`}>
                <div className={`w-2.5 h-2.5 rounded-full ${!continuousMode ? 'bg-black' : 'bg-slate-500'}`}></div>SINGLE
              </button>
              <button onClick={() => setContinuousMode(true)} disabled={running} data-testid="mode-continuous-btn"
                className={`px-5 py-2.5 text-sm font-bold transition-all flex items-center gap-2 ${continuousMode ? 'bg-purple-500 text-white shadow-[0_0_20px_rgba(139,92,246,0.4)]' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'} ${running ? 'opacity-50 cursor-not-allowed' : ''}`}>
                <RefreshCw className={`w-4 h-4 ${continuousMode ? 'animate-spin' : ''}`} />CONTINUOUS
              </button>
            </div>
          </div>
          
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2"><span className="text-[10px] text-white/40 uppercase tracking-wider">Capital</span><span className="text-sm font-mono text-white">${savedConfig?.initial_capital?.toLocaleString() || '10,000'}</span></div>
            <div className="flex items-center gap-2"><span className="text-[10px] text-white/40 uppercase tracking-wider">Deployed</span><span className="text-sm font-mono text-cyan-400">${((savedConfig?.initial_capital || 10000) * (savedConfig?.capital_deployment_pct || 80) / 100).toLocaleString()}<span className="text-white/40 ml-1">({savedConfig?.capital_deployment_pct || 80}%)</span></span></div>
            <div className="flex items-center gap-2"><span className="text-[10px] text-white/40 uppercase tracking-wider">Kelly</span><span className="text-sm font-mono text-purple-400">{((savedConfig?.kelly_fraction || 0.25) * 100).toFixed(0)}%</span></div>
            <div className="flex items-center gap-2"><span className="text-[10px] text-white/40 uppercase tracking-wider">Max DD</span><span className="text-sm font-mono text-rose-400">{savedConfig?.max_drawdown_pct || 10}%</span></div>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 p-1.5 rounded-xl bg-slate-900/50 border border-white/10">
        {TAB_CONFIG.map(tab => {
          const isActive = activeTab === tab.id;
          const colorClasses = {
            cyan: isActive ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40' : '',
            emerald: isActive ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' : '',
            blue: isActive ? 'bg-blue-500/20 text-blue-400 border-blue-500/40' : '',
            amber: isActive ? 'bg-amber-500/20 text-amber-400 border-amber-500/40' : '',
            purple: isActive ? 'bg-purple-500/20 text-purple-400 border-purple-500/40' : ''
          };
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} data-testid={`tab-${tab.id}`}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-all border ${isActive ? colorClasses[tab.color] : 'text-white/50 hover:text-white hover:bg-white/5 border-transparent'}`}>
              <tab.icon className={`w-4 h-4 ${isActive ? '' : 'opacity-60'}`} />
              <span className="text-sm">{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Live Session Tab */}
      {activeTab === 'live' && (
        <div className="space-y-5">
          
          {/* Circuit Breaker Alert - Compact with Flash Animation */}
          {status?.circuit_breaker_triggered && (
            <div className="relative overflow-hidden rounded-lg border border-red-500/60 bg-red-950/40" data-testid="circuit-breaker-banner">
              {/* Animated background pulse */}
              <div className="absolute inset-0 bg-gradient-to-r from-red-600/20 via-red-500/10 to-red-600/20 animate-pulse" />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(239,68,68,0.15),transparent_70%)]" />
              
              <div className="relative flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="absolute inset-0 rounded-full bg-red-500 animate-ping opacity-40" />
                    <div className="relative w-8 h-8 rounded-full bg-red-500/30 flex items-center justify-center border border-red-500/50">
                      <AlertTriangle className="w-4 h-4 text-red-400" />
                    </div>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-red-400 tracking-wide">CIRCUIT BREAKER ACTIVE</p>
                    <p className="text-xs text-red-300/60">New entries blocked • Monitoring exits</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-xs text-red-300/50 uppercase tracking-wider">Drawdown</p>
                    <p className="text-lg font-bold text-red-400 tabular-nums">{status?.current_drawdown_pct?.toFixed(1) || 0}%</p>
                  </div>
                  <div className="h-8 w-px bg-red-500/30" />
                  <div className="text-right">
                    <p className="text-xs text-red-300/50 uppercase tracking-wider">Limit</p>
                    <p className="text-lg font-bold text-red-300/80 tabular-nums">{status?.config?.max_drawdown_pct || 5}%</p>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* Performance Metrics - Improved Grid */}
          {status && (
            <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
              <MetricCard title="Capital" value={`$${(status.current_capital || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}`} subtitle={`Initial: $${(status.initial_capital || 10000).toLocaleString()}`} icon={Wallet} color="blue" />
              <MetricCard title="Total P&L" value={`${(status.combined_pnl || status.total_pnl || 0) >= 0 ? '+' : ''}$${Math.abs(status.combined_pnl || status.total_pnl || 0).toFixed(2)}`} subtitle={`Realized: $${(status.total_pnl || 0).toFixed(2)}`} trend={status.combined_pnl_pct || status.total_pnl_pct} icon={DollarSign} color={(status.combined_pnl || status.total_pnl || 0) >= 0 ? "green" : "red"} />
              <MetricCard title="Win Rate" value={`${((status.win_rate || 0) * 100).toFixed(1)}%`} subtitle={`${status.winning_trades || 0}/${status.total_trades || 0} wins`} icon={Target} color="cyan" />
              <MetricCard title="Total Trades" value={status.total_trades || 0} icon={Activity} color="purple" />
              <MetricCard title="Open Positions" value={status.open_positions ?? positions.length ?? 0} icon={Layers} color="orange" />
              <div className={`rounded-xl p-4 transition-all ${
                status?.circuit_breaker_triggered 
                  ? 'bg-red-500/20 border-2 border-red-500/50 shadow-[0_0_20px_rgba(239,68,68,0.3)] animate-pulse' 
                  : 'bg-white/5 border border-white/10'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs uppercase tracking-wider ${status?.circuit_breaker_triggered ? 'text-red-400' : 'text-white/40'}`}>Max Drawdown</span>
                  <Shield className={`w-4 h-4 ${status?.circuit_breaker_triggered ? 'text-red-400' : 'text-red-400/60'}`} />
                </div>
                <p className={`text-2xl font-bold tabular-nums ${status?.circuit_breaker_triggered ? 'text-red-400' : 'text-white'}`}>
                  {(status?.current_drawdown_pct || 0).toFixed(1)}%
                </p>
                <p className={`text-xs mt-1 ${status?.circuit_breaker_triggered ? 'text-red-300/60' : 'text-white/40'}`}>
                  Limit: {savedConfig?.max_drawdown_pct || status.config?.max_drawdown_pct || 5}%
                </p>
              </div>
            </div>
          )}

          {/* Asset Class Equity Breakdown (starts at $0 per session) */}
          {status && (
            <AssetClassEquityCard equityData={status?.asset_class_equity} initialCapital={initialCapital} />
          )}

          {/* Strategy & Asset Class Tables with Totals */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white/60">Strategy Performance (Live)</span>
                <ResetButton onClick={handleResetLiveSession} label="Reset Live Stats" />
              </div>
              <PerformanceTable title="Strategy Performance" icon={BarChart3} iconColor="purple" data={status?.strategy_results} dataType="strategy" showLiveBadge={running} initialCapital={initialCapital} />
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white/60">Asset Class Performance (Live)</span>
              </div>
              <PerformanceTable title="Asset Class Performance" icon={Layers} iconColor="orange" data={status?.asset_class_results} dataType="asset_class" showLiveBadge={running} initialCapital={initialCapital} />
            </div>
          </div>

          {/* Equity Curves */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white/60">Equity by Strategy</span>
                <ResetButton onClick={handleResetLiveSession} label="Reset" />
              </div>
              <div className="rounded-xl bg-white/5 border border-white/10 p-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <LineChartIcon className="w-5 h-5 text-cyan-400" />Equity Curve
                  <span className="text-xs text-white/40">(Total starts at ${initialCapital.toLocaleString()})</span>
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={prepareEquityCurveData(status?.equity_curve)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis dataKey="timestamp" stroke="rgba(255,255,255,0.4)" tick={{ fontSize: 9 }} tickFormatter={(val) => new Date(val).toLocaleTimeString()} />
                      <YAxis stroke="rgba(255,255,255,0.4)" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: 'rgba(30,41,59,0.98)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px', padding: '10px 14px' }} 
                        labelStyle={{ color: '#e2e8f0', fontWeight: 'bold', marginBottom: '4px' }} 
                        itemStyle={{ color: '#94a3b8' }}
                        formatter={(value, name) => [<span style={{color: value >= 0 ? '#22d3ee' : '#f87171', fontWeight: 'bold'}}>${value?.toFixed(2)}</span>, name]} 
                      />
                      <Legend wrapperStyle={{ fontSize: '10px' }} />
                      <Line type="monotone" dataKey="total_equity" name="Total Equity" stroke="#ffffff" strokeWidth={3} dot={false} />
                      <Line type="monotone" dataKey="delta_neutral_pnl" name="Delta-Neutral" stroke="#06b6d4" strokeWidth={1.5} dot={false} />
                      <Line type="monotone" dataKey="volatility_pnl" name="Volatility" stroke="#8b5cf6" strokeWidth={1.5} dot={false} />
                      <Line type="monotone" dataKey="alpha_pnl" name="Alpha" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
                      <Line type="monotone" dataKey="arbitrage_pnl" name="Arbitrage" stroke="#10b981" strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white/60">Equity by Asset Class</span>
                <ResetButton onClick={handleResetLiveSession} label="Reset" />
              </div>
              <div className="rounded-xl bg-white/5 border border-white/10 p-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <LineChartIcon className="w-5 h-5 text-orange-400" />Asset Class Equity
                  <span className="text-xs text-white/40">(Total starts at ${initialCapital.toLocaleString()})</span>
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={prepareAssetClassEquityCurve(status?.equity_curve)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis dataKey="timestamp" stroke="rgba(255,255,255,0.4)" tick={{ fontSize: 9 }} tickFormatter={(val) => new Date(val).toLocaleTimeString()} />
                      <YAxis stroke="rgba(255,255,255,0.4)" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: 'rgba(30,41,59,0.98)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px', padding: '10px 14px' }} 
                        labelStyle={{ color: '#e2e8f0', fontWeight: 'bold', marginBottom: '4px' }} 
                        itemStyle={{ color: '#94a3b8' }}
                        formatter={(value, name) => [<span style={{color: value >= 0 ? '#22d3ee' : '#f87171', fontWeight: 'bold'}}>${value?.toFixed(2)}</span>, name.replace('ac_', '')]} 
                      />
                      <Legend wrapperStyle={{ fontSize: '10px' }} formatter={(value) => value.replace('ac_', '')} />
                      <Line type="monotone" dataKey="total_equity" name="Total Equity" stroke="#ffffff" strokeWidth={3} dot={false} />
                      {status?.asset_class_equity && Object.keys(status.asset_class_equity).map((ac, idx) => (
                        <Line key={ac} type="monotone" dataKey={`ac_${ac}`} name={ac} stroke={Object.values(ASSET_CLASS_COLORS)[idx % 6]} strokeWidth={1.5} dot={false} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>

          {/* P&L Distribution */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-white/60">P&L Distribution (Live Session)</span>
              <ResetButton onClick={handleResetLiveSession} label="Reset" />
            </div>
            <PnLDistributionChart 
              data={status?.returns_distribution?.bins?.length > 0 ? status?.returns_distribution : status?.unrealized_distribution} 
              title={status?.returns_distribution?.bins?.length > 0 ? "Realized P&L Distribution" : "Unrealized P&L Distribution (Open Positions)"} 
            />
          </div>

          {/* Open Positions */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2"><Layers className="w-5 h-5 text-orange-400" />Open Positions ({positions.length})</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-80 overflow-y-auto">
              {positions.length > 0 ? positions.map((pos, idx) => (
                <PositionCard 
                  key={idx} 
                  position={pos} 
                  onViewSizing={(p) => setSizingModal({ isOpen: true, position: p })}
                />
              )) : <p className="text-white/40 text-center py-8 col-span-full">No open positions</p>}
            </div>
          </div>

          {/* Sizing Analytics Dashboard */}
          <SizingAnalyticsDashboard positions={positions} trades={trades} />
          
          {/* Historical Analytics Charts */}
          <HistoricalAnalyticsChart />

          {/* Trade History */}
          <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
            <div className="p-4 border-b border-white/10">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <History className="w-5 h-5 text-cyan-400" />Trade History
                <span className="text-xs text-white/40 ml-2">({trades.length} trades)</span>
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead><tr className="bg-white/5 text-left">
                  <SortableHeader label="Status" sortKey="type" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="Market" sortKey="market" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="Strategy" sortKey="strategy" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="Side" sortKey="side" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="Size" sortKey="size" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="Entry → Exit" sortKey="entry" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="P&L ($)" sortKey="pnl" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="Return (%)" sortKey="return" currentSort={tradeSort} onSort={handleTradeSort} />
                  <SortableHeader label="Time" sortKey="timestamp" currentSort={tradeSort} onSort={handleTradeSort} />
                  <th className="py-3 px-4 text-xs text-white/60 uppercase">AI</th>
                </tr></thead>
                <tbody>
                  {sortedTrades.slice(0, 50).map((trade, idx) => (
                    <TradeRow 
                      key={idx} 
                      trade={trade} 
                      onViewSentiment={(t) => setSentimentModal({ isOpen: true, trade: t })}
                    />
                  ))}
                  {sortedTrades.length === 0 && <tr><td colSpan={10} className="py-8 text-center text-white/40">No trades yet. Start paper trading to see activity.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Cumulative Stats Tab */}
      {activeTab === 'cumulative' && (
        <div className="space-y-6">
          {/* Overall Stats */}
          {cumulativeStats?.overall && (
            <div className="rounded-xl bg-gradient-to-br from-cyan-500/10 to-blue-500/10 border border-cyan-500/20 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <TrendingUp className="w-6 h-6 text-cyan-400" />Cumulative Statistics
                  <span className="text-xs text-white/40 ml-2">(All-time: {cumulativeStats.overall.total_sessions} sessions)</span>
                </h3>
                <div className="flex items-center gap-3">
                  {cumulativeStats.current_session_included && <span className="px-3 py-1 rounded-full bg-green-500/20 text-green-400 text-xs flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>Live included</span>}
                  <ResetButton onClick={handleResetCumulativeStats} label="Reset All Stats" />
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                <MetricCard title="Total Sessions" value={cumulativeStats.overall.total_sessions} subtitle={`${cumulativeStats.overall.continuous_sessions} continuous`} icon={History} color="blue" />
                <MetricCard title="Total Trades" value={cumulativeStats.overall.total_trades.toLocaleString()} subtitle={`Avg ${cumulativeStats.overall.avg_session_trades?.toFixed(0)}/session`} icon={Activity} color="purple" />
                <MetricCard title="Total Wins" value={cumulativeStats.overall.total_wins.toLocaleString()} icon={Award} color="green" />
                <MetricCard title="Win Rate" value={`${(cumulativeStats.overall.win_rate * 100).toFixed(1)}%`} icon={Target} color={cumulativeStats.overall.win_rate >= 0.5 ? "green" : "red"} />
                <MetricCard title="Total P&L" value={`${cumulativeStats.overall.total_pnl >= 0 ? '+' : ''}$${cumulativeStats.overall.total_pnl.toFixed(2)}`} icon={DollarSign} color={cumulativeStats.overall.total_pnl >= 0 ? "green" : "red"} />
                <MetricCard title="Capital Traded" value={`$${cumulativeStats.overall.total_initial_capital.toLocaleString()}`} icon={Wallet} color="cyan" />
              </div>
            </div>
          )}

          {/* Strategy & Asset Class Tables with Totals */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <PerformanceTable title="Cumulative Strategy Performance" icon={BarChart3} iconColor="purple" data={cumulativeStats?.by_strategy} dataType="strategy" showLiveBadge={false} initialCapital={cumulativeStats?.overall?.total_initial_capital || initialCapital} />
            <PerformanceTable title="Cumulative Asset Class Performance" icon={Layers} iconColor="orange" data={cumulativeStats?.by_asset_class} dataType="asset_class" showLiveBadge={false} initialCapital={cumulativeStats?.overall?.total_initial_capital || initialCapital} />
          </div>

          {/* Cumulative P&L Distribution */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-white/60">Cumulative P&L Distribution (All Sessions)</span>
              <ResetButton onClick={handleResetCumulativeStats} label="Reset" />
            </div>
            <PnLDistributionChart data={cumulativeStats?.returns_distribution} title="Cumulative P&L Distribution" />
          </div>

          {/* Info */}
          <div className="rounded-xl bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/20 p-4">
            <p className="text-blue-400 text-sm"><strong>Cumulative Stats:</strong> Aggregates ALL paper trading sessions for long-term performance analysis. {running && <span className="text-green-400 ml-2">● Live session included.</span>}</p>
          </div>
        </div>
      )}

      {/* Sessions History Tab */}
      {activeTab === 'history' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Trading Sessions History</h3>
              <button onClick={fetchSessions} className="p-2 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors"><RefreshCw className="w-4 h-4" /></button>
            </div>
            <div className="divide-y divide-white/5">
              {sessions.map((session) => (
                <div key={session.session_id} className="p-4 hover:bg-white/5 transition-colors">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-white font-medium">Session: {session.session_id}</p>
                      <p className="text-xs text-white/40 mt-1">{new Date(session.start_time).toLocaleString()} - {session.status}</p>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <div className="text-right"><p className="text-white/60">Trades</p><p className="text-white font-medium">{session.total_trades || 0}</p></div>
                      <div className="text-right"><p className="text-white/60">Win Rate</p><p className="text-white font-medium">{((session.win_rate || 0) * 100).toFixed(1)}%</p></div>
                      <div className="text-right"><p className="text-white/60">P&L</p><p className={`font-bold ${(session.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{(session.total_pnl || 0) >= 0 ? '+' : ''}${(session.total_pnl || 0).toFixed(2)}</p></div>
                      <button onClick={() => viewSessionTrades(session)} className="px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 text-xs flex items-center gap-1" data-testid={`view-trades-${session.session_id}`}>
                        <List className="w-3 h-3" />View Trades
                      </button>
                      <button onClick={() => runOptimization(session.session_id)} className="px-3 py-1.5 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 text-xs flex items-center gap-1">
                        <Sparkles className="w-3 h-3" />Optimize
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {sessions.length === 0 && <p className="p-8 text-center text-white/40">No paper trading sessions yet</p>}
            </div>
          </div>
        </div>
      )}

      {/* Optimizer Tab */}
      {activeTab === 'optimizer' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-gradient-to-br from-purple-500/10 to-pink-500/10 border border-purple-500/20 p-6">
            <div className="flex items-start justify-between mb-6">
              <div>
                <h3 className="text-xl font-bold text-white flex items-center gap-2"><Sparkles className="w-6 h-6 text-purple-400" />Strategy Optimizer</h3>
                <p className="text-white/60 text-sm mt-1">Automatically tune parameters from paper trading results</p>
              </div>
              <button onClick={applyOptimizedParams} disabled={!optimizerParams} className="px-4 py-2 rounded-lg bg-purple-500/20 border border-purple-500/30 text-purple-400 hover:bg-purple-500/30 disabled:opacity-50 flex items-center gap-2">
                <CheckCircle className="w-4 h-4" />Apply Parameters
              </button>
            </div>
            {optimizerParams && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2"><Crosshair className="w-4 h-4 text-cyan-400" />Entry Thresholds</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-white/60">Min RL Confidence</span><span className="text-white">{(optimizerParams.min_rl_confidence * 100).toFixed(0)}%</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Min Sentiment</span><span className="text-white">{(optimizerParams.min_sentiment_strength * 100).toFixed(0)}%</span></div>
                  </div>
                </div>
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2"><Target className="w-4 h-4 text-green-400" />Exit Thresholds</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-white/60">Take Profit</span><span className="text-green-400">{(optimizerParams.take_profit_pct * 100).toFixed(0)}%</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Stop Loss</span><span className="text-red-400">{(optimizerParams.stop_loss_pct * 100).toFixed(0)}%</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Max Hold</span><span className="text-white">{optimizerParams.max_hold_hours}h</span></div>
                  </div>
                </div>
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2"><Scale className="w-4 h-4 text-orange-400" />Position Sizing</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-white/60">Kelly Fraction</span><span className="text-white">{(optimizerParams.kelly_fraction * 100).toFixed(0)}%</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Max Position</span><span className="text-white">{(optimizerParams.max_position_pct * 100).toFixed(0)}%</span></div>
                  </div>
                </div>
              </div>
            )}
          </div>
          
          {/* Exit Mode Configuration */}
          <div className="rounded-xl bg-gradient-to-br from-cyan-500/10 to-blue-500/10 border border-cyan-500/20 p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <Target className="w-6 h-6 text-cyan-400" />
                  Exit Mode
                </h3>
              </div>
              <div className="flex items-center gap-3">
                <span className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
                  useDynamicExit 
                    ? 'bg-cyan-500/20 border border-cyan-500/30 text-cyan-400' 
                    : 'bg-gray-500/20 border border-gray-500/30 text-gray-400'
                }`}>
                  {useDynamicExit ? '⚡ Dynamic (Time-Aware)' : '⚙️ Simple (Fixed)'}
                </span>
                <button 
                  onClick={toggleExitMode}
                  disabled={!running}
                  className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/60 hover:text-white text-sm transition-all disabled:opacity-40"
                >
                  Switch
                </button>
              </div>
            </div>
            
            <div className="p-4 rounded-lg bg-white/5 border border-white/10">
              {useDynamicExit ? (
                <div className="space-y-2">
                  <p className="text-sm text-white/80">TP/SL calculated dynamically based on:</p>
                  <ul className="text-xs text-white/60 space-y-1 ml-4 list-disc">
                    <li>Max possible gain (10% capture, capped 0.5%-50%)</li>
                    <li>Price extremeness (tighter SL at extremes)</li>
                    <li>Time to expiry (hold to resolution if ≤3 days)</li>
                  </ul>
                  <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-white/10">
                    <span className="text-xs px-2 py-1 rounded bg-purple-500/20 text-purple-300">≤3d: Hold→Res</span>
                    <span className="text-xs px-2 py-1 rounded bg-blue-500/20 text-blue-300">4-7d: Hold+SL</span>
                    <span className="text-xs px-2 py-1 rounded bg-cyan-500/20 text-cyan-300">8-30d: Active</span>
                    <span className="text-xs px-2 py-1 rounded bg-yellow-500/20 text-yellow-300">&gt;30d: Quick</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-white/80">Fixed TP/SL per strategy (configure in Settings → Exit Parameters)</p>
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    {savedConfig?.exit_params && Object.entries(savedConfig.exit_params).slice(0, 4).map(([strategy, params]) => (
                      <div key={strategy} className="text-xs flex justify-between px-2 py-1 rounded bg-white/5">
                        <span className="text-white/50 capitalize">{strategy.replace('_', ' ').substring(0, 12)}</span>
                        <span className="text-white/80">TP:{(params.take_profit * 100).toFixed(0)}% SL:{(params.stop_loss * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            
            <p className="text-xs text-white/40 mt-3 text-center">
              Configure exit parameters in <a href="/config" className="text-cyan-400 hover:underline">Settings → Exit Parameters</a>
            </p>
          </div>
        </div>
      )}

      {/* RL Learning Tab */}
      {activeTab === 'rl' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-500/20 p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-white flex items-center gap-2">
                <Brain className="w-6 h-6 text-blue-400" />
                Reinforcement Learning Status
              </h3>
              {rlStats && (
                <div className="flex items-center gap-3">
                  <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                    rlStats.model_type === 'DQN' 
                      ? 'bg-purple-500/30 text-purple-300 border border-purple-500/50' 
                      : 'bg-blue-500/30 text-blue-300 border border-blue-500/50'
                  }`}>
                    {rlStats.model_type || 'Q-table'}
                  </span>
                  {rlStats.prioritized_replay && (
                    <span className="px-2 py-1 rounded-full text-[10px] bg-green-500/20 text-green-400 border border-green-500/30">
                      Prioritized Replay
                    </span>
                  )}
                </div>
              )}
            </div>
            
            {rlStats && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <MetricCard title="Training Iterations" value={rlStats.total_iterations?.toLocaleString() || 0} icon={Zap} color="blue" />
                <MetricCard title="Exploration Rate" value={`${((rlStats.epsilon || 0) * 100).toFixed(1)}%`} subtitle="Lower = more exploitation" icon={Crosshair} color="purple" />
                <MetricCard title="Avg Reward (100)" value={(rlStats.avg_reward_100 || 0).toFixed(3)} icon={Award} color={rlStats.avg_reward_100 >= 0 ? "green" : "red"} />
                <MetricCard title="Experience Buffer" value={rlStats.buffer_size?.toLocaleString() || 0} subtitle={rlStats.model_type === 'DQN' ? `β: ${(rlStats.buffer_beta || 0).toFixed(2)}` : "Max: 10,000"} icon={Database} color="cyan" />
              </div>
            )}
            
            {rlStats && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Model-specific info */}
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                    {rlStats.model_type === 'DQN' ? (
                      <>
                        <span className="w-2 h-2 rounded-full bg-purple-500"></span>
                        DQN Architecture
                      </>
                    ) : (
                      <>
                        <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                        Q-Table Analysis
                      </>
                    )}
                  </h4>
                  <div className="space-y-2 text-sm">
                    {rlStats.model_type === 'DQN' ? (
                      <>
                        <div className="flex justify-between"><span className="text-white/60">Architecture</span><span className="text-white font-mono text-xs">{rlStats.architecture}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Device</span><span className="text-white">{rlStats.device}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Learning Rate</span><span className="text-white">{rlStats.learning_rate}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Gamma (discount)</span><span className="text-white">{rlStats.gamma}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Target Update Freq</span><span className="text-white">{rlStats.target_update_freq}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Avg Loss (100)</span><span className="text-white">{(rlStats.avg_loss_100 || 0).toFixed(6)}</span></div>
                      </>
                    ) : (
                      <>
                        <div className="flex justify-between"><span className="text-white/60">Table Size</span><span className="text-white">{rlStats.q_table_size?.join(' x ')}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Non-zero %</span><span className="text-white">{(rlStats.q_table_nonzero_pct || 0).toFixed(1)}%</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Mean Q-Value</span><span className="text-white">{(rlStats.q_table_mean || 0).toFixed(4)}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Max Q-Value</span><span className="text-white">{(rlStats.q_table_max || 0).toFixed(4)}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Learning Rate</span><span className="text-white">{rlStats.learning_rate}</span></div>
                        <div className="flex justify-between"><span className="text-white/60">Discount Factor</span><span className="text-white">{rlStats.discount_factor}</span></div>
                      </>
                    )}
                  </div>
                </div>
                
                {/* Reward stats */}
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3">Reward Statistics</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-white/60">Positive Rate</span><span className="text-green-400">{((rlStats.positive_rate || 0) * 100).toFixed(1)}%</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Avg Positive</span><span className="text-green-400">+{(rlStats.avg_positive_reward || 0).toFixed(4)}</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Avg Negative</span><span className="text-red-400">{(rlStats.avg_negative_reward || 0).toFixed(4)}</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Std Dev</span><span className="text-white">{(rlStats.std_reward_100 || 0).toFixed(4)}</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Max Reward</span><span className="text-cyan-400">{(rlStats.max_reward_100 || 0).toFixed(4)}</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Min Reward</span><span className="text-orange-400">{(rlStats.min_reward_100 || 0).toFixed(4)}</span></div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Action Distribution */}
            {rlStats && rlStats.action_distribution && (
              <div className="mt-6 rounded-lg bg-white/5 p-4">
                <h4 className="text-white font-medium mb-3">Action Distribution</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries(rlStats.action_distribution).map(([action, count]) => {
                    const maxCount = Math.max(...Object.values(rlStats.action_distribution), 1);
                    const pct = (count / maxCount) * 100;
                    const isBuy = action.startsWith('BUY');
                    const isSell = action.startsWith('SELL');
                    const color = isBuy ? 'green' : isSell ? 'red' : 'blue';
                    return (
                      <div key={action} className="bg-white/5 rounded-lg p-2">
                        <div className="flex items-center justify-between mb-1">
                          <span className={`text-xs font-medium text-${color}-400`}>{action}</span>
                          <span className="text-white text-xs">{count}</span>
                        </div>
                        <div className="bg-white/10 rounded-full h-1.5">
                          <div className={`bg-${color}-500 h-1.5 rounded-full transition-all`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            
            {/* Force Train Section with Buffer Status */}
            <div className="mt-6 p-4 rounded-lg bg-white/5 border border-white/10">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-sm font-medium text-white">Manual Training</h4>
                  <p className="text-xs text-white/50 mt-0.5">Train RL model from experience buffer</p>
                </div>
                {rlStats && (
                  <div className="text-right">
                    <div className="text-xs text-white/60">Buffer Status</div>
                    <div className={`text-sm font-mono ${(rlStats.buffer_size || 0) >= 32 ? 'text-green-400' : 'text-yellow-400'}`}>
                      {rlStats.buffer_size || 0} / 32 min
                    </div>
                  </div>
                )}
              </div>
              
              {/* Progress bar for buffer */}
              {rlStats && (
                <div className="mb-3">
                  <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-300 ${(rlStats.buffer_size || 0) >= 32 ? 'bg-green-500' : 'bg-yellow-500'}`}
                      style={{ width: `${Math.min(100, ((rlStats.buffer_size || 0) / 32) * 100)}%` }}
                    />
                  </div>
                  {(rlStats.buffer_size || 0) < 32 && (
                    <p className="text-xs text-yellow-400/70 mt-1">
                      Need {32 - (rlStats.buffer_size || 0)} more closed trades to enable training
                    </p>
                  )}
                </div>
              )}
              
              <div className="flex gap-3">
                <button 
                  onClick={trainRLFromSession} 
                  disabled={!rlStats || (rlStats.buffer_size || 0) < 32}
                  className="px-4 py-2 rounded-lg bg-purple-500/20 border border-purple-500/30 text-purple-400 hover:bg-purple-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm transition"
                >
                  <Brain className="w-4 h-4" />
                  {(rlStats?.buffer_size || 0) >= 32 ? 'Force Train Now' : `Waiting for Data (${rlStats?.buffer_size || 0}/32)`}
                </button>
                
                {running && (
                  <span className="flex items-center gap-1.5 text-xs text-green-400/70">
                    <Activity className="w-3 h-3 animate-pulse" />
                    Auto-training every 30s
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PaperTrading;
