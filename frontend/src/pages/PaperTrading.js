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
                const pnlPct = trade.entry_price > 0 ? ((trade.exit_price - trade.entry_price) / trade.entry_price * 100) : 0;
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

// Position Card Component
const PositionCard = ({ position }) => {
  const pnlPct = position.unrealized_pnl_pct || 0;
  const isProfit = pnlPct >= 0;
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4 hover:bg-white/10 transition-colors">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white font-medium truncate">{position.market_question}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-xs px-2 py-0.5 rounded ${position.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{position.side}</span>
            <span className="text-xs text-white/40">{position.strategy}</span>
          </div>
        </div>
        <div className={`text-right ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
          <p className="text-sm font-bold">{isProfit ? '+' : ''}{pnlPct.toFixed(1)}%</p>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs text-white/40">
        <span>Entry: ${position.entry_price?.toFixed(4)}</span>
        <span>Size: ${position.size?.toFixed(2)}</span>
        <span>RL: {(position.rl_confidence * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
};

// Trade Row Component
const TradeRow = ({ trade }) => {
  const isEntry = trade.type === 'entry';
  const isProfit = trade.pnl > 0;
  
  // For entry trades: price is the entry price
  // For exit trades: entry_price and exit_price are available
  const entryPrice = isEntry ? trade.price : trade.entry_price;
  const exitPrice = isEntry ? null : (trade.exit_price || trade.price);
  
  return (
    <tr className="border-b border-white/5 hover:bg-white/5">
      <td className="py-3 px-4">
        <span className={`text-xs px-2 py-1 rounded ${isEntry ? 'bg-blue-500/20 text-blue-400' : isProfit ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
          {trade.type?.toUpperCase()}
        </span>
      </td>
      <td className="py-3 px-4 text-sm text-white/80 max-w-xs truncate" title={trade.market_question || trade.market_id}>
        {trade.market_question || trade.market_id?.substring(0, 30) + '...'}
      </td>
      <td className="py-3 px-4 text-sm text-white/60">{STRATEGY_INFO[trade.strategy]?.name || trade.strategy}</td>
      <td className="py-3 px-4 text-sm text-white/80">{trade.side}</td>
      <td className="py-3 px-4 text-sm text-white/80">${trade.size?.toFixed(2)}</td>
      <td className="py-3 px-4 text-sm text-cyan-400">${entryPrice?.toFixed(4) || '-'}</td>
      <td className="py-3 px-4 text-sm text-amber-400">{exitPrice ? `$${exitPrice.toFixed(4)}` : '-'}</td>
      <td className={`py-3 px-4 text-sm font-medium ${isEntry ? 'text-white/40' : isProfit ? 'text-green-400' : 'text-red-400'}`}>
        {isEntry ? '-' : `${isProfit ? '+' : ''}$${trade.pnl?.toFixed(2)}`}
      </td>
      <td className="py-3 px-4 text-xs text-white/40">{new Date(trade.timestamp).toLocaleTimeString()}</td>
    </tr>
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

  const entries = Object.entries(data).sort((a, b) => b[1].total_pnl - a[1].total_pnl);
  
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
  
  // Modal states
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null });
  const [sessionTradesModal, setSessionTradesModal] = useState({ isOpen: false, session: null, trades: [] });

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
    fetchData(); fetchSessions(); fetchRlStats(); fetchOptimizerParams(); fetchAiStats(); fetchCumulativeStats();
    const pollingInterval = wsConnected ? 10000 : 5000;
    const interval = setInterval(() => {
      fetchData(); fetchCumulativeStats(); fetchSavedConfig();
      if (running) { fetchRlStats(); fetchAiStats(); }
    }, pollingInterval);
    return () => clearInterval(interval);
  }, [fetchData, running, wsConnected, fetchSavedConfig]);

  useEffect(() => { fetchSavedConfig(); }, [fetchSavedConfig]);

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
              running ? status?.graceful_stop ? 'bg-amber-500/20 border border-amber-500/40' : 'bg-emerald-500/20 border border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.2)]' : 'bg-slate-800/50 border border-white/10'
            }`}>
              <div className={`w-2 h-2 rounded-full ${running ? status?.graceful_stop ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`}></div>
              <span className={`text-xs font-mono uppercase tracking-wider ${running ? status?.graceful_stop ? 'text-amber-400' : 'text-emerald-400' : 'text-slate-400'}`}>
                {running ? status?.graceful_stop ? 'CLOSING' : status?.continuous_mode ? 'CONTINUOUS' : 'TRADING' : 'STOPPED'}
              </span>
            </div>
            
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded ${wsConnected ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}>
              {wsConnected ? <Wifi className="w-3 h-3 text-emerald-400" /> : <WifiOff className="w-3 h-3 text-rose-400" />}
              <span className={`text-[10px] font-mono ${wsConnected ? 'text-emerald-400' : 'text-rose-400'}`}>{wsConnected ? 'LIVE' : 'POLL'}</span>
            </div>
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
            <div className="flex items-center gap-2"><span className="text-[10px] text-white/40 uppercase tracking-wider">Max DD</span><span className="text-sm font-mono text-rose-400">{savedConfig?.max_drawdown_pct || 5}%</span></div>
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
        <div className="space-y-6">
          {/* Performance Metrics */}
          {status && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              <MetricCard title="Capital" value={`$${(status.current_capital || 0).toFixed(0)}`} subtitle={`Initial: $${status.initial_capital}`} icon={Wallet} color="blue" />
              <MetricCard title="Total P&L" value={`${(status.combined_pnl || status.total_pnl || 0) >= 0 ? '+' : ''}$${(status.combined_pnl || status.total_pnl || 0).toFixed(2)}`} subtitle={`Realized: $${(status.total_pnl || 0).toFixed(2)}`} trend={status.combined_pnl_pct || status.total_pnl_pct} icon={DollarSign} color={(status.combined_pnl || status.total_pnl || 0) >= 0 ? "green" : "red"} />
              <MetricCard title="Win Rate" value={`${((status.win_rate || 0) * 100).toFixed(1)}%`} subtitle={`${status.winning_trades || 0}/${status.total_trades || 0} wins`} icon={Target} color="cyan" />
              <MetricCard title="Total Trades" value={status.total_trades || 0} icon={Activity} color="purple" />
              <MetricCard title="Open Positions" value={status.open_positions ?? positions.length ?? 0} icon={Layers} color="orange" />
              <MetricCard title="Max Drawdown" value={`${((status.max_drawdown || 0) * 100).toFixed(1)}%`} subtitle={`Limit: ${status.config?.max_drawdown_pct || 5}%`} icon={Shield} color="red" />
            </div>
          )}

          {/* Strategy & Asset Class Tables with Totals */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white/60">Strategy Performance (Live)</span>
                <ResetButton onClick={handleResetLiveSession} label="Reset Live Stats" />
              </div>
              <PerformanceTable title="Strategy Performance" icon={BarChart3} iconColor="purple" data={cumulativeStats?.by_strategy} dataType="strategy" showLiveBadge={running} initialCapital={initialCapital} />
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white/60">Asset Class Performance (Live)</span>
              </div>
              <PerformanceTable title="Asset Class Performance" icon={Layers} iconColor="orange" data={cumulativeStats?.by_asset_class} dataType="asset_class" showLiveBadge={running} initialCapital={initialCapital} />
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
            <PnLDistributionChart data={status?.returns_distribution} title="Live Session P&L Distribution" />
          </div>

          {/* Open Positions */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2"><Layers className="w-5 h-5 text-orange-400" />Open Positions ({positions.length})</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-80 overflow-y-auto">
              {positions.length > 0 ? positions.map((pos, idx) => <PositionCard key={idx} position={pos} />) : <p className="text-white/40 text-center py-8 col-span-full">No open positions</p>}
            </div>
          </div>

          {/* Trade History */}
          <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
            <div className="p-4 border-b border-white/10"><h3 className="text-lg font-semibold text-white flex items-center gap-2"><History className="w-5 h-5 text-cyan-400" />Recent Trades</h3></div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead><tr className="bg-white/5 text-left"><th className="py-3 px-4 text-xs text-white/60 uppercase">Type</th><th className="py-3 px-4 text-xs text-white/60 uppercase">Market</th><th className="py-3 px-4 text-xs text-white/60 uppercase">Strategy</th><th className="py-3 px-4 text-xs text-white/60 uppercase">Side</th><th className="py-3 px-4 text-xs text-white/60 uppercase">Size</th><th className="py-3 px-4 text-xs text-cyan-400/80 uppercase">Entry</th><th className="py-3 px-4 text-xs text-amber-400/80 uppercase">Exit</th><th className="py-3 px-4 text-xs text-white/60 uppercase">P&L</th><th className="py-3 px-4 text-xs text-white/60 uppercase">Time</th></tr></thead>
                <tbody>
                  {trades.slice(0, 20).map((trade, idx) => <TradeRow key={idx} trade={trade} />)}
                  {trades.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-white/40">No trades yet. Start paper trading to see activity.</td></tr>}
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
        </div>
      )}

      {/* RL Learning Tab */}
      {activeTab === 'rl' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-500/20 p-6">
            <h3 className="text-xl font-bold text-white flex items-center gap-2 mb-6"><Brain className="w-6 h-6 text-blue-400" />Reinforcement Learning Status</h3>
            {rlStats && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <MetricCard title="Training Iterations" value={rlStats.total_iterations?.toLocaleString() || 0} icon={Zap} color="blue" />
                <MetricCard title="Exploration Rate" value={`${((rlStats.epsilon || 0) * 100).toFixed(1)}%`} subtitle="Lower = more exploitation" icon={Crosshair} color="purple" />
                <MetricCard title="Avg Reward (100)" value={(rlStats.avg_reward_100 || 0).toFixed(3)} icon={Award} color={rlStats.avg_reward_100 >= 0 ? "green" : "red"} />
                <MetricCard title="Experience Buffer" value={rlStats.buffer_size?.toLocaleString() || 0} subtitle="Max: 10,000" icon={Database} color="cyan" />
              </div>
            )}
            {rlStats && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3">Q-Table Analysis</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-white/60">Table Size</span><span className="text-white">{rlStats.q_table_size?.join(' x ')}</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Non-zero %</span><span className="text-white">{(rlStats.q_table_nonzero_pct || 0).toFixed(1)}%</span></div>
                    <div className="flex justify-between"><span className="text-white/60">Mean Q-Value</span><span className="text-white">{(rlStats.q_table_mean || 0).toFixed(4)}</span></div>
                  </div>
                </div>
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3">Action Distribution</h4>
                  <div className="space-y-2">
                    {rlStats.action_distribution && Object.entries(rlStats.action_distribution).map(([action, count]) => (
                      <div key={action} className="flex items-center gap-2">
                        <span className="text-white/60 text-sm w-24">{action}</span>
                        <div className="flex-1 bg-white/10 rounded-full h-2">
                          <div className="bg-cyan-500 h-2 rounded-full" style={{ width: `${(count / Math.max(...Object.values(rlStats.action_distribution))) * 100}%` }} />
                        </div>
                        <span className="text-white text-sm w-12 text-right">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
            <div className="mt-6 flex gap-4">
              <button onClick={trainRLFromSession} disabled={!running} className="px-4 py-2 rounded-lg bg-purple-500/20 border border-purple-500/30 text-purple-400 hover:bg-purple-500/30 disabled:opacity-50 flex items-center gap-2 text-sm">
                <Brain className="w-4 h-4" />Force Train Now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PaperTrading;
