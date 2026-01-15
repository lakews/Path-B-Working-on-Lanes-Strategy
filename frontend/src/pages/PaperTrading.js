import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { 
  Play, Square, TrendingUp, TrendingDown, Activity, DollarSign, Target, 
  BarChart3, Clock, Zap, Shield, Award, Percent, ChevronRight, Database,
  RefreshCw, AlertTriangle, CheckCircle, XCircle, History, Brain, Download,
  Layers, Settings, Sparkles, Crosshair, Scale, Timer, Wallet, ArrowUpRight,
  ArrowDownRight, Eye, FileText, PieChart, LineChart as LineChartIcon
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar, Cell, PieChart as RePieChart, Pie, Legend } from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STRATEGY_INFO = {
  delta_neutral: { 
    name: 'Delta-Neutral', 
    color: '#06b6d4',
    icon: Scale
  },
  volatility_exploitation: { 
    name: 'Volatility', 
    color: '#8b5cf6',
    icon: Zap
  },
  alpha_directional: { 
    name: 'Alpha', 
    color: '#f59e0b',
    icon: Target
  },
  arbitrage: { 
    name: 'Arbitrage', 
    color: '#10b981',
    icon: Layers
  }
};

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
            <span className={`text-xs px-2 py-0.5 rounded ${position.side === 'YES' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
              {position.side}
            </span>
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
  
  return (
    <tr className="border-b border-white/5 hover:bg-white/5">
      <td className="py-3 px-4">
        <span className={`text-xs px-2 py-1 rounded ${isEntry ? 'bg-blue-500/20 text-blue-400' : isProfit ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
          {trade.type?.toUpperCase()}
        </span>
      </td>
      <td className="py-3 px-4 text-sm text-white/80 max-w-xs truncate">{trade.market_id?.substring(0, 20)}...</td>
      <td className="py-3 px-4 text-sm text-white/60">{trade.strategy}</td>
      <td className="py-3 px-4 text-sm text-white/80">{trade.side}</td>
      <td className="py-3 px-4 text-sm text-white/80">${trade.size?.toFixed(2)}</td>
      <td className="py-3 px-4 text-sm text-white/80">${trade.price?.toFixed(4)}</td>
      <td className={`py-3 px-4 text-sm font-medium ${isEntry ? 'text-white/40' : isProfit ? 'text-green-400' : 'text-red-400'}`}>
        {isEntry ? '-' : `${isProfit ? '+' : ''}$${trade.pnl?.toFixed(2)}`}
      </td>
      <td className="py-3 px-4 text-xs text-white/40">
        {new Date(trade.timestamp).toLocaleTimeString()}
      </td>
    </tr>
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
  const [activeTab, setActiveTab] = useState('live'); // 'live', 'history', 'optimizer', 'rl'
  const [initialCapital, setInitialCapital] = useState(10000);
  const [selectedSession, setSelectedSession] = useState(null);
  const [continuousMode, setContinuousMode] = useState(false);
  const [aiStats, setAiStats] = useState(null);
  const [showStopOptions, setShowStopOptions] = useState(false);
  const [cumulativeStats, setCumulativeStats] = useState(null);

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, positionsRes, tradesRes, analyticsRes] = await Promise.all([
        axios.get(`${API}/paper/status`),
        axios.get(`${API}/paper/positions`),
        axios.get(`${API}/paper/trades?limit=50`),
        axios.get(`${API}/paper/analytics`)
      ]);
      
      setStatus(statusRes.data);
      setRunning(statusRes.data?.running || false);
      setContinuousMode(statusRes.data?.continuous_mode || false);
      setPositions(positionsRes.data?.positions || []);
      setTrades(tradesRes.data?.trades || []);
      setAnalytics(analyticsRes.data);
    } catch (e) {
      console.error('Error fetching data:', e);
    }
  }, []);

  const fetchAiStats = async () => {
    try {
      const response = await axios.get(`${API}/paper/ai-stats`);
      setAiStats(response.data?.ai_stats);
    } catch (e) {
      console.error('Error fetching AI stats:', e);
    }
  };

  const fetchCumulativeStats = async () => {
    try {
      const response = await axios.get(`${API}/paper/cumulative-stats`);
      setCumulativeStats(response.data);
    } catch (e) {
      console.error('Error fetching cumulative stats:', e);
    }
  };

  const fetchSessions = async () => {
    try {
      const response = await axios.get(`${API}/paper/sessions?limit=20`);
      setSessions(response.data?.sessions || []);
    } catch (e) {
      console.error('Error fetching sessions:', e);
    }
  };

  const fetchRlStats = async () => {
    try {
      const response = await axios.get(`${API}/rl/detailed-stats`);
      setRlStats(response.data?.rl_stats || response.data);
    } catch (e) {
      console.error('Error fetching RL stats:', e);
    }
  };

  const fetchOptimizerParams = async () => {
    try {
      const response = await axios.get(`${API}/optimizer/params`);
      setOptimizerParams(response.data?.params);
    } catch (e) {
      console.error('Error fetching optimizer params:', e);
    }
  };

  useEffect(() => {
    fetchData();
    fetchSessions();
    fetchRlStats();
    fetchOptimizerParams();
    fetchAiStats();
    fetchCumulativeStats();
    
    const interval = setInterval(() => {
      fetchData();
      fetchCumulativeStats();
      if (running) {
        fetchRlStats();
        fetchAiStats();
      }
    }, 5000);
    
    return () => clearInterval(interval);
  }, [fetchData, running]);

  const startPaperTrading = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`${API}/paper/start?initial_capital=${initialCapital}&continuous_mode=${continuousMode}`);
      toast.success(`Paper trading started! Session: ${response.data.session_id}${continuousMode ? ' (Continuous Mode)' : ''}`);
      setRunning(true);
      fetchData();
    } catch (e) {
      toast.error(e.response?.data?.message || 'Failed to start paper trading');
    } finally {
      setLoading(false);
    }
  };

  const stopPaperTrading = async (graceful = false) => {
    setLoading(true);
    setShowStopOptions(false);
    try {
      const response = await axios.post(`${API}/paper/stop?graceful=${graceful}`);
      toast.success(graceful ? 'Graceful stop initiated - waiting for positions to close' : 'Paper trading stopped');
      if (!graceful) {
        setRunning(false);
      }
      setStatus(response.data?.final_status);
      fetchSessions();
    } catch (e) {
      toast.error('Failed to stop paper trading');
    } finally {
      setLoading(false);
    }
  };

  const trainRLFromSession = async () => {
    try {
      toast.info('Training RL from paper trading session...');
      // Trigger RL training from current session
      await axios.post(`${API}/rl/train`);
      toast.success('RL training complete!');
      fetchRlStats();
      fetchAiStats();
    } catch (e) {
      toast.error('RL training failed');
    }
  };

  const runOptimization = async (sessionId) => {
    try {
      toast.info('Running strategy optimization...');
      const response = await axios.post(`${API}/optimizer/run/${sessionId}`);
      toast.success('Optimization complete!');
      setOptimizerParams(response.data?.new_params);
      fetchOptimizerParams();
    } catch (e) {
      toast.error('Optimization failed');
    }
  };

  const applyOptimizedParams = async () => {
    try {
      await axios.post(`${API}/optimizer/apply`);
      toast.success('Optimized parameters applied!');
    } catch (e) {
      toast.error('Failed to apply parameters');
    }
  };

  const viewSessionDetails = async (sessionId) => {
    try {
      const response = await axios.get(`${API}/paper/session/${sessionId}`);
      setSelectedSession(response.data);
    } catch (e) {
      toast.error('Failed to load session details');
    }
  };

  // Prepare chart data
  const equityCurveData = analytics?.equity_curve || [];
  
  const strategyPieData = analytics?.strategy_performance ? 
    Object.entries(analytics.strategy_performance)
      .filter(([_, data]) => data.trades > 0)
      .map(([strategy, data]) => ({
        name: STRATEGY_INFO[strategy]?.name || strategy,
        value: data.trades,
        pnl: data.pnl,
        wins: data.wins,
        fill: STRATEGY_INFO[strategy]?.color || '#888'
      })) : [];

  return (
    <div className="space-y-6" data-testid="paper-trading-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <FileText className="w-7 h-7 text-blue-400" />
            Paper Trading
          </h1>
          <p className="text-white/60 text-sm mt-1">
            Simulate live trading with RL learning - No real money at risk
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Status Badge */}
          <div className={`flex items-center gap-2 px-4 py-2 rounded-lg backdrop-blur-sm border ${
            running 
              ? status?.graceful_stop 
                ? 'bg-yellow-500/20 border-yellow-500/30' 
                : 'bg-blue-500/20 border-blue-500/30' 
              : 'bg-white/5 border-white/10'
          }`}>
            <div className={`w-2 h-2 rounded-full ${running ? status?.graceful_stop ? 'bg-yellow-400 animate-pulse' : 'bg-blue-400 animate-pulse' : 'bg-gray-400'}`}></div>
            <span className={`text-sm ${running ? status?.graceful_stop ? 'text-yellow-400' : 'text-blue-400' : 'text-white/60'}`}>
              {running 
                ? status?.graceful_stop 
                  ? '⏳ CLOSING POSITIONS' 
                  : status?.continuous_mode 
                    ? '🔄 CONTINUOUS MODE' 
                    : '📝 PAPER TRADING' 
                : 'Stopped'}
            </span>
          </div>
          
          {/* Start/Stop Button */}
          {running ? (
            <div className="relative">
              <button
                onClick={() => setShowStopOptions(!showStopOptions)}
                disabled={loading || status?.graceful_stop}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-red-500/20 border border-red-500/30 text-red-400 hover:bg-red-500/30 transition-colors"
                data-testid="stop-paper-trading-btn"
              >
                <Square className="w-4 h-4" />
                {status?.graceful_stop ? 'Closing...' : 'Stop Session'}
              </button>
              {/* Stop Options Dropdown */}
              {showStopOptions && (
                <div className="absolute top-full right-0 mt-2 w-64 rounded-lg bg-slate-800 border border-white/10 shadow-xl z-50">
                  <div className="p-2 border-b border-white/10">
                    <p className="text-xs text-white/60 px-2">How do you want to stop?</p>
                  </div>
                  <button
                    onClick={() => stopPaperTrading(false)}
                    className="w-full px-4 py-3 text-left hover:bg-white/10 flex items-center gap-3 text-sm"
                  >
                    <Square className="w-4 h-4 text-red-400" />
                    <div>
                      <p className="text-white">Immediate Stop</p>
                      <p className="text-xs text-white/40">Close all positions now at current prices</p>
                    </div>
                  </button>
                  <button
                    onClick={() => stopPaperTrading(true)}
                    className="w-full px-4 py-3 text-left hover:bg-white/10 flex items-center gap-3 text-sm"
                  >
                    <Clock className="w-4 h-4 text-yellow-400" />
                    <div>
                      <p className="text-white">Graceful Stop</p>
                      <p className="text-xs text-white/40">Let positions close by TP/SL strategy</p>
                    </div>
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div className="relative">
                <label className="absolute -top-2 left-2 px-1 text-[10px] text-white/50 bg-slate-900">Initial Capital</label>
                <input
                  type="number"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(Number(e.target.value))}
                  className="w-32 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white text-sm"
                  placeholder="10000"
                />
              </div>
              {/* Continuous Mode Toggle */}
              <button
                onClick={() => setContinuousMode(!continuousMode)}
                className={`px-3 py-2 rounded-lg border text-sm flex items-center gap-2 ${
                  continuousMode 
                    ? 'bg-purple-500/20 border-purple-500/30 text-purple-400' 
                    : 'bg-white/5 border-white/20 text-white/60 hover:text-white'
                }`}
                title="Continuous mode runs indefinitely until manually stopped. Learning is applied immediately to subsequent trades."
              >
                <RefreshCw className={`w-4 h-4 ${continuousMode ? 'animate-spin' : ''}`} />
                {continuousMode ? 'Continuous' : 'Single'}
              </button>
              <button
                onClick={startPaperTrading}
                disabled={loading}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-500 to-cyan-500 text-white font-medium hover:from-blue-600 hover:to-cyan-600 transition-all shadow-lg shadow-blue-500/25"
                data-testid="start-paper-trading-btn"
              >
                <Play className="w-4 h-4" />
                Start Paper Trading
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 p-1 rounded-xl bg-white/5 border border-white/10">
        {[
          { id: 'live', label: 'Live Session', icon: Activity },
          { id: 'cumulative', label: 'Cumulative Stats', icon: TrendingUp },
          { id: 'history', label: `Sessions (${sessions.length})`, icon: History },
          { id: 'optimizer', label: 'Strategy Optimizer', icon: Settings },
          { id: 'rl', label: 'RL Learning', icon: Brain }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            data-testid={`tab-${tab.id}`}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-gradient-to-r from-blue-500/20 to-cyan-500/20 text-blue-400 border border-blue-500/30'
                : 'text-white/60 hover:text-white hover:bg-white/5'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            <span className="text-sm">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Live Session Tab */}
      {activeTab === 'live' && (
        <div className="space-y-6">
          {/* Performance Metrics */}
          {status && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              <MetricCard
                title="Capital"
                value={`$${(status.current_capital || 0).toFixed(0)}`}
                subtitle={status.initial_capital ? `Initial: $${status.initial_capital}` : 'Not started'}
                icon={Wallet}
                color="blue"
              />
              <MetricCard
                title="Total P&L"
                value={`${status.total_pnl >= 0 ? '+' : ''}$${(status.total_pnl || 0).toFixed(2)}`}
                trend={status.total_pnl_pct}
                icon={DollarSign}
                color={status.total_pnl >= 0 ? "green" : "red"}
              />
              <MetricCard
                title="Win Rate"
                value={`${((status.win_rate || 0) * 100).toFixed(1)}%`}
                subtitle={`${status.winning_trades || 0}/${status.total_trades || 0} wins`}
                icon={Target}
                color="cyan"
              />
              <MetricCard
                title="Total Trades"
                value={status.total_trades || 0}
                icon={Activity}
                color="purple"
              />
              <MetricCard
                title="Open Positions"
                value={status.open_positions || 0}
                icon={Layers}
                color="orange"
              />
              <MetricCard
                title="Max Drawdown"
                value={`${((status.max_drawdown || 0) * 100).toFixed(1)}%`}
                icon={Shield}
                color="red"
              />
            </div>
          )}

          {/* Strategy & Asset Class Performance Tables - CUMULATIVE & CONTINUOUS */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Strategy Performance Table - Cumulative */}
            <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-purple-400" />
                  Strategy Performance
                  <span className="text-xs text-white/40">(Cumulative)</span>
                </h3>
                {running && (
                  <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-[10px] flex items-center gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></div>
                    LIVE
                  </span>
                )}
              </div>
              {cumulativeStats?.by_strategy && (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-white/5 text-left">
                        <th className="py-2 px-3 text-xs text-white/60 uppercase">Strategy</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">P&L</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">% Return</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Contrib %</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Trades</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Win Rate</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">PF</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const entries = Object.entries(cumulativeStats.by_strategy)
                          .sort((a, b) => b[1].total_pnl - a[1].total_pnl);
                        const totalPnl = entries.reduce((sum, [_, d]) => sum + (d.total_pnl || 0), 0);
                        const totalCapital = cumulativeStats.overall?.total_initial_capital || 10000;
                        const absTotalPnl = Math.abs(totalPnl);
                        
                        return entries.map(([strategy, data]) => {
                          const isPositive = data.total_pnl >= 0;
                          const returnPct = (data.total_pnl / totalCapital) * 100;
                          const contribPct = absTotalPnl > 0 ? (data.total_pnl / totalPnl) * 100 : 0;
                          const profitFactor = data.total_wins > 0 && (data.total_trades - data.total_wins) > 0 
                            ? (data.total_pnl > 0 ? data.total_pnl : 0) / Math.abs(data.total_pnl < 0 ? data.total_pnl : 0.01)
                            : data.total_pnl > 0 ? 2.0 : 0;
                          const info = STRATEGY_INFO[strategy];
                          return (
                            <tr key={strategy} className="border-b border-white/5 hover:bg-white/5">
                              <td className="py-2 px-3">
                                <div className="flex items-center gap-2">
                                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: info?.color }} />
                                  <span className="text-sm text-white">{info?.name || strategy}</span>
                                </div>
                              </td>
                              <td className={`py-2 px-3 text-right text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}${data.total_pnl?.toFixed(2)}
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${contribPct >= 0 ? 'text-cyan-400' : 'text-orange-400'}`}>
                                {isNaN(contribPct) ? '0.0' : contribPct.toFixed(1)}%
                              </td>
                              <td className="py-2 px-3 text-right text-sm text-white font-bold">{data.total_trades}</td>
                              <td className={`py-2 px-3 text-right text-sm ${data.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                                {(data.win_rate * 100).toFixed(1)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${profitFactor >= 1.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                                {profitFactor.toFixed(2)}
                              </td>
                            </tr>
                          );
                        });
                      })()}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Asset Class Performance Table - Cumulative */}
            <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Layers className="w-5 h-5 text-orange-400" />
                  Asset Class Performance
                  <span className="text-xs text-white/40">(Cumulative)</span>
                </h3>
                {running && (
                  <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-[10px] flex items-center gap-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></div>
                    LIVE
                  </span>
                )}
              </div>
              {cumulativeStats?.by_asset_class && Object.keys(cumulativeStats.by_asset_class).length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-white/5 text-left">
                        <th className="py-2 px-3 text-xs text-white/60 uppercase">Asset Class</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">P&L</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">% Return</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Contrib %</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Trades</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Win Rate</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">PF</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const entries = Object.entries(cumulativeStats.by_asset_class)
                          .sort((a, b) => b[1].total_pnl - a[1].total_pnl);
                        const totalPnl = entries.reduce((sum, [_, d]) => sum + (d.total_pnl || 0), 0);
                        const totalCapital = cumulativeStats.overall?.total_initial_capital || 10000;
                        const absTotalPnl = Math.abs(totalPnl);
                        
                        return entries.map(([assetClass, data]) => {
                          const isPositive = data.total_pnl >= 0;
                          const returnPct = (data.total_pnl / totalCapital) * 100;
                          const contribPct = absTotalPnl > 0 ? (data.total_pnl / totalPnl) * 100 : 0;
                          const profitFactor = data.total_wins > 0 && (data.total_trades - data.total_wins) > 0 
                            ? (data.total_pnl > 0 ? data.total_pnl : 0) / Math.abs(data.total_pnl < 0 ? data.total_pnl : 0.01)
                            : data.total_pnl > 0 ? 2.0 : 0;
                          return (
                            <tr key={assetClass} className="border-b border-white/5 hover:bg-white/5">
                              <td className="py-2 px-3">
                                <span className="text-sm text-white capitalize">{assetClass}</span>
                              </td>
                              <td className={`py-2 px-3 text-right text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}${data.total_pnl?.toFixed(2)}
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${contribPct >= 0 ? 'text-cyan-400' : 'text-orange-400'}`}>
                                {isNaN(contribPct) ? '0.0' : contribPct.toFixed(1)}%
                              </td>
                              <td className="py-2 px-3 text-right text-sm text-white font-bold">{data.total_trades}</td>
                              <td className={`py-2 px-3 text-right text-sm ${data.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                                {(data.win_rate * 100).toFixed(1)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${profitFactor >= 1.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                                {profitFactor.toFixed(2)}
                              </td>
                            </tr>
                          );
                        });
                      })()}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center text-white/40">No asset class data yet - start paper trading to see data</div>
              )}
            </div>
          </div>

          {/* Equity Curves - Two Charts Side by Side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Equity Curve by Strategy */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <LineChartIcon className="w-5 h-5 text-cyan-400" />
                Equity by Strategy
                <span className="text-xs text-white/40 ml-2">(Total + per strategy)</span>
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={status?.equity_curve || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis 
                      dataKey="timestamp" 
                      stroke="rgba(255,255,255,0.4)"
                      tick={{ fontSize: 9 }}
                      tickFormatter={(val) => new Date(val).toLocaleTimeString()}
                    />
                    <YAxis stroke="rgba(255,255,255,0.4)" tick={{ fontSize: 10 }} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                      labelStyle={{ color: '#94a3b8' }}
                      formatter={(value, name) => [`$${value?.toFixed(2)}`, name]}
                    />
                    <Legend wrapperStyle={{ fontSize: '10px' }} />
                    <Line type="monotone" dataKey="pnl" name="Total" stroke="#ffffff" strokeWidth={3} dot={false} />
                    <Line type="monotone" dataKey="delta_neutral_pnl" name="Delta-Neutral" stroke="#06b6d4" strokeWidth={1.5} dot={false} />
                    <Line type="monotone" dataKey="volatility_pnl" name="Volatility" stroke="#8b5cf6" strokeWidth={1.5} dot={false} />
                    <Line type="monotone" dataKey="alpha_pnl" name="Alpha" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
                    <Line type="monotone" dataKey="arbitrage_pnl" name="Arbitrage" stroke="#10b981" strokeWidth={1.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Equity Curve by Asset Class */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <LineChartIcon className="w-5 h-5 text-orange-400" />
                Equity by Asset Class
                <span className="text-xs text-white/40 ml-2">(Total + per asset class)</span>
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={status?.equity_curve?.map(point => {
                    // Flatten asset_class_equity into individual keys
                    const flatPoint = { ...point };
                    if (point.asset_class_equity) {
                      Object.entries(point.asset_class_equity).forEach(([ac, val]) => {
                        flatPoint[`ac_${ac}`] = val;
                      });
                    }
                    return flatPoint;
                  }) || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis 
                      dataKey="timestamp" 
                      stroke="rgba(255,255,255,0.4)"
                      tick={{ fontSize: 9 }}
                      tickFormatter={(val) => new Date(val).toLocaleTimeString()}
                    />
                    <YAxis stroke="rgba(255,255,255,0.4)" tick={{ fontSize: 10 }} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                      labelStyle={{ color: '#94a3b8' }}
                      formatter={(value, name) => [`$${value?.toFixed(2)}`, name.replace('ac_', '')]}
                    />
                    <Legend wrapperStyle={{ fontSize: '10px' }} formatter={(value) => value.replace('ac_', '')} />
                    <Line type="monotone" dataKey="pnl" name="Total" stroke="#ffffff" strokeWidth={3} dot={false} />
                    {/* Dynamic asset class lines based on what data exists */}
                    {status?.asset_class_equity && Object.keys(status.asset_class_equity).map((ac, idx) => {
                      const colors = ['#ef4444', '#f59e0b', '#10b981', '#06b6d4', '#8b5cf6', '#ec4899'];
                      return (
                        <Line 
                          key={ac}
                          type="monotone" 
                          dataKey={`ac_${ac}`} 
                          name={ac}
                          stroke={colors[idx % colors.length]} 
                          strokeWidth={1.5} 
                          dot={false} 
                        />
                      );
                    })}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Returns Distribution */}
                    <tbody>
                      {(() => {
                        const entries = Object.entries(status.strategy_results)
                          .filter(([_, d]) => d.trades > 0)
                          .sort((a, b) => b[1].pnl - a[1].pnl);
                        const totalPnl = entries.reduce((sum, [_, d]) => sum + (d.pnl || 0), 0);
                        const absTotalPnl = Math.abs(totalPnl);
                        
                        return entries.map(([strategy, data]) => {
                          const isPositive = data.pnl >= 0;
                          const returnPct = ((data.pnl || 0) / (status.initial_capital || 10000)) * 100;
                          const contribPct = absTotalPnl > 0 ? ((data.pnl || 0) / totalPnl) * 100 : 0;
                          const info = STRATEGY_INFO[strategy];
                          return (
                            <tr key={strategy} className="border-b border-white/5 hover:bg-white/5">
                              <td className="py-2 px-3">
                                <div className="flex items-center gap-2">
                                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: info?.color }} />
                                  <span className="text-sm text-white">{info?.name || strategy}</span>
                                </div>
                              </td>
                              <td className={`py-2 px-3 text-right text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}${data.pnl?.toFixed(2)}
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${contribPct >= 0 ? 'text-cyan-400' : 'text-orange-400'}`}>
                                {contribPct.toFixed(1)}%
                              </td>
                              <td className="py-2 px-3 text-right text-sm text-white/70">{data.trades}</td>
                              <td className={`py-2 px-3 text-right text-sm ${(data.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                                {((data.win_rate || 0) * 100).toFixed(1)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${(data.profit_factor || 0) >= 1.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                                {(data.profit_factor || 0).toFixed(2)}
                              </td>
                            </tr>
                          );
                        });
                      })()}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center text-white/40">No strategy data yet</div>
              )}
            </div>

            {/* Asset Class Performance Table */}
            <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
              <div className="p-4 border-b border-white/10">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Layers className="w-5 h-5 text-orange-400" />
                  Asset Class Performance
                </h3>
              </div>
              {status?.asset_class_results && Object.keys(status.asset_class_results).length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-white/5 text-left">
                        <th className="py-2 px-3 text-xs text-white/60 uppercase">Asset Class</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">P&L</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">% Return</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Contrib %</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Trades</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">Win Rate</th>
                        <th className="py-2 px-3 text-xs text-white/60 uppercase text-right">PF</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const entries = Object.entries(status.asset_class_results)
                          .filter(([_, d]) => d.trades > 0)
                          .sort((a, b) => b[1].pnl - a[1].pnl);
                        const totalPnl = entries.reduce((sum, [_, d]) => sum + (d.pnl || 0), 0);
                        const absTotalPnl = Math.abs(totalPnl);
                        
                        return entries.map(([assetClass, data]) => {
                          const isPositive = data.pnl >= 0;
                          const returnPct = ((data.pnl || 0) / (status.initial_capital || 10000)) * 100;
                          const contribPct = absTotalPnl > 0 ? ((data.pnl || 0) / totalPnl) * 100 : 0;
                          return (
                            <tr key={assetClass} className="border-b border-white/5 hover:bg-white/5">
                              <td className="py-2 px-3">
                                <span className="text-sm text-white capitalize">{assetClass}</span>
                              </td>
                              <td className={`py-2 px-3 text-right text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}${data.pnl?.toFixed(2)}
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${contribPct >= 0 ? 'text-cyan-400' : 'text-orange-400'}`}>
                                {contribPct.toFixed(1)}%
                              </td>
                              <td className="py-2 px-3 text-right text-sm text-white/70">{data.trades}</td>
                              <td className={`py-2 px-3 text-right text-sm ${(data.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                                {((data.win_rate || 0) * 100).toFixed(1)}%
                              </td>
                              <td className={`py-2 px-3 text-right text-sm ${(data.profit_factor || 0) >= 1.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                                {(data.profit_factor || 0).toFixed(2)}
                              </td>
                            </tr>
                          );
                        });
                      })()}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center text-white/40">No asset class data yet</div>
              )}
            </div>
          </div>

          {/* Returns Distribution */}
          {status?.returns_distribution?.bins?.length > 0 && (
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-purple-400" />
                  Returns Distribution
                  <span className="text-xs text-white/40 ml-2">
                    ({status.returns_distribution.bins.filter(b => b.count > 0).length} bins with data)
                  </span>
                </h3>
                {status.returns_distribution.stats && (
                  <div className="flex items-center gap-4 text-xs">
                    <span className="text-white/50">Mean: <span className={status.returns_distribution.stats.mean >= 0 ? 'text-green-400' : 'text-red-400'}>{status.returns_distribution.stats.mean?.toFixed(2)}%</span></span>
                    <span className="text-white/50">Median: <span className="text-cyan-400">{status.returns_distribution.stats.median?.toFixed(2)}%</span></span>
                    <span className="text-white/50">Std Dev: <span className="text-purple-400">{status.returns_distribution.stats.std?.toFixed(2)}%</span></span>
                  </div>
                )}
              </div>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={status.returns_distribution.bins.filter(b => b.count > 0)} margin={{ top: 10, right: 30, left: 0, bottom: 30 }}>
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
                      contentStyle={{backgroundColor: 'rgba(0,0,0,0.95)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px'}}
                      formatter={(value) => [`${value} trades`, 'Count']}
                      labelFormatter={(label) => `Return: ${label}`}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {status.returns_distribution.bins.filter(b => b.count > 0).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.min >= 0 ? '#10b981' : '#ef4444'} fillOpacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {status.returns_distribution.stats && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-white/10">
                  <div className="text-center">
                    <p className="text-xs text-white/50">Positive Returns</p>
                    <p className="text-lg font-bold text-green-400">{status.returns_distribution.stats.positive_returns || 0}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-white/50">Negative Returns</p>
                    <p className="text-lg font-bold text-red-400">{status.returns_distribution.stats.negative_returns || 0}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-white/50">Skewness</p>
                    <p className={`text-lg font-bold ${(status.returns_distribution.stats.skewness || 0) > 0 ? 'text-green-400' : 'text-yellow-400'}`}>
                      {status.returns_distribution.stats.skewness?.toFixed(2) || '0.00'}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-white/50">Kurtosis</p>
                    <p className="text-lg font-bold text-purple-400">{status.returns_distribution.stats.kurtosis?.toFixed(2) || '0.00'}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Open Positions */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Layers className="w-5 h-5 text-orange-400" />
              Open Positions ({positions.length})
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-80 overflow-y-auto">
              {positions.length > 0 ? positions.map((pos, idx) => (
                <PositionCard key={idx} position={pos} />
              )) : (
                <p className="text-white/40 text-center py-8 col-span-full">No open positions</p>
              )}
            </div>
          </div>

          {/* Trade History Table */}
          <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
            <div className="p-4 border-b border-white/10">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <History className="w-5 h-5 text-cyan-400" />
                Recent Trades
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-white/5 text-left">
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">Type</th>
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">Market</th>
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">Strategy</th>
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">Side</th>
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">Size</th>
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">Price</th>
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">P&L</th>
                    <th className="py-3 px-4 text-xs text-white/60 uppercase">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.slice(0, 20).map((trade, idx) => (
                    <TradeRow key={idx} trade={trade} />
                  ))}
                  {trades.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-white/40">
                        No trades yet. Start paper trading to see activity.
                      </td>
                    </tr>
                  )}
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
                  <TrendingUp className="w-6 h-6 text-cyan-400" />
                  Cumulative Trading Statistics
                  <span className="text-xs text-white/40 ml-2">
                    (All-time across {cumulativeStats.overall.total_sessions} sessions)
                  </span>
                </h3>
                {cumulativeStats.current_session_included && (
                  <span className="px-3 py-1 rounded-full bg-green-500/20 text-green-400 text-xs flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>
                    Live session included
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                <MetricCard
                  title="Total Sessions"
                  value={cumulativeStats.overall.total_sessions}
                  subtitle={`${cumulativeStats.overall.continuous_sessions} continuous`}
                  icon={History}
                  color="blue"
                />
                <MetricCard
                  title="Total Trades"
                  value={cumulativeStats.overall.total_trades.toLocaleString()}
                  subtitle={`Avg ${cumulativeStats.overall.avg_session_trades?.toFixed(0)}/session`}
                  icon={Activity}
                  color="purple"
                />
                <MetricCard
                  title="Total Wins"
                  value={cumulativeStats.overall.total_wins.toLocaleString()}
                  icon={Award}
                  color="green"
                />
                <MetricCard
                  title="Win Rate"
                  value={`${(cumulativeStats.overall.win_rate * 100).toFixed(1)}%`}
                  icon={Target}
                  color={cumulativeStats.overall.win_rate >= 0.5 ? "green" : "red"}
                />
                <MetricCard
                  title="Total P&L"
                  value={`${cumulativeStats.overall.total_pnl >= 0 ? '+' : ''}$${cumulativeStats.overall.total_pnl.toFixed(2)}`}
                  icon={DollarSign}
                  color={cumulativeStats.overall.total_pnl >= 0 ? "green" : "red"}
                />
                <MetricCard
                  title="Total Capital Traded"
                  value={`$${cumulativeStats.overall.total_initial_capital.toLocaleString()}`}
                  icon={Wallet}
                  color="cyan"
                />
              </div>
            </div>
          )}

          {/* Strategy Cumulative Table */}
          {cumulativeStats?.by_strategy && (
            <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
              <div className="p-4 border-b border-white/10">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-purple-400" />
                  Cumulative Strategy Performance
                  <span className="text-xs text-white/40 ml-2">(All-time totals)</span>
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-white/5 text-left">
                      <th className="py-3 px-4 text-xs text-white/60 uppercase">Strategy</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Total Trades</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Total Wins</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Win Rate</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Total P&L</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Sessions Used</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Avg P&L/Session</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(cumulativeStats.by_strategy)
                      .sort((a, b) => b[1].total_trades - a[1].total_trades)
                      .map(([strategy, data]) => {
                        const info = STRATEGY_INFO[strategy];
                        const avgPnlPerSession = data.sessions > 0 ? data.total_pnl / data.sessions : 0;
                        return (
                          <tr key={strategy} className="border-b border-white/5 hover:bg-white/5">
                            <td className="py-3 px-4">
                              <div className="flex items-center gap-2">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: info?.color }} />
                                <span className="text-white font-medium">{info?.name || strategy}</span>
                              </div>
                            </td>
                            <td className="py-3 px-4 text-right text-xl font-bold text-white">
                              {data.total_trades.toLocaleString()}
                            </td>
                            <td className="py-3 px-4 text-right text-white/80">
                              {data.total_wins.toLocaleString()}
                            </td>
                            <td className={`py-3 px-4 text-right font-medium ${data.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                              {(data.win_rate * 100).toFixed(1)}%
                            </td>
                            <td className={`py-3 px-4 text-right font-bold ${data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {data.total_pnl >= 0 ? '+' : ''}${data.total_pnl.toFixed(2)}
                            </td>
                            <td className="py-3 px-4 text-right text-white/60">
                              {data.sessions}
                            </td>
                            <td className={`py-3 px-4 text-right ${avgPnlPerSession >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {avgPnlPerSession >= 0 ? '+' : ''}${avgPnlPerSession.toFixed(2)}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Asset Class Cumulative Table */}
          {cumulativeStats?.by_asset_class && Object.keys(cumulativeStats.by_asset_class).length > 0 && (
            <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
              <div className="p-4 border-b border-white/10">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Layers className="w-5 h-5 text-orange-400" />
                  Cumulative Asset Class Performance
                  <span className="text-xs text-white/40 ml-2">(All-time totals)</span>
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-white/5 text-left">
                      <th className="py-3 px-4 text-xs text-white/60 uppercase">Asset Class</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Total Trades</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Total Wins</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Win Rate</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Total P&L</th>
                      <th className="py-3 px-4 text-xs text-white/60 uppercase text-right">Sessions Used</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(cumulativeStats.by_asset_class)
                      .sort((a, b) => b[1].total_trades - a[1].total_trades)
                      .map(([assetClass, data]) => (
                        <tr key={assetClass} className="border-b border-white/5 hover:bg-white/5">
                          <td className="py-3 px-4">
                            <span className="text-white font-medium capitalize">{assetClass}</span>
                          </td>
                          <td className="py-3 px-4 text-right text-xl font-bold text-white">
                            {data.total_trades.toLocaleString()}
                          </td>
                          <td className="py-3 px-4 text-right text-white/80">
                            {data.total_wins.toLocaleString()}
                          </td>
                          <td className={`py-3 px-4 text-right font-medium ${data.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                            {(data.win_rate * 100).toFixed(1)}%
                          </td>
                          <td className={`py-3 px-4 text-right font-bold ${data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {data.total_pnl >= 0 ? '+' : ''}${data.total_pnl.toFixed(2)}
                          </td>
                          <td className="py-3 px-4 text-right text-white/60">
                            {data.sessions}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Info Box */}
          <div className="rounded-xl bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/20 p-4">
            <p className="text-blue-400 text-sm">
              <strong>📊 Cumulative Stats:</strong> These statistics aggregate ALL your paper trading sessions to show long-term performance trends. 
              Use this to identify which strategies and asset classes perform best over time. 
              {running && <span className="text-green-400 ml-2">● Live session data is included in real-time.</span>}
            </p>
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-white/5 border border-white/10 overflow-hidden">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Paper Trading Sessions</h3>
              <button
                onClick={fetchSessions}
                className="p-2 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
            <div className="divide-y divide-white/5">
              {sessions.map((session) => (
                <div 
                  key={session.session_id}
                  className="p-4 hover:bg-white/5 transition-colors cursor-pointer"
                  onClick={() => viewSessionDetails(session.session_id)}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-white font-medium">Session: {session.session_id}</p>
                      <p className="text-xs text-white/40 mt-1">
                        {new Date(session.start_time).toLocaleString()} - {session.status}
                      </p>
                    </div>
                    <div className="flex items-center gap-6 text-sm">
                      <div className="text-right">
                        <p className="text-white/60">Trades</p>
                        <p className="text-white font-medium">{session.total_trades || 0}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-white/60">Win Rate</p>
                        <p className="text-white font-medium">{((session.win_rate || 0) * 100).toFixed(1)}%</p>
                      </div>
                      <div className="text-right">
                        <p className="text-white/60">P&L</p>
                        <p className={`font-bold ${(session.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {(session.total_pnl || 0) >= 0 ? '+' : ''}${(session.total_pnl || 0).toFixed(2)}
                        </p>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          runOptimization(session.session_id);
                        }}
                        className="px-3 py-1.5 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 text-xs flex items-center gap-1"
                      >
                        <Sparkles className="w-3 h-3" />
                        Optimize
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {sessions.length === 0 && (
                <p className="p-8 text-center text-white/40">No paper trading sessions yet</p>
              )}
            </div>
          </div>

          {/* Selected Session Details */}
          {selectedSession && (
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">
                  Session Details: {selectedSession.session?.session_id}
                </h3>
                <button
                  onClick={() => setSelectedSession(null)}
                  className="p-2 rounded-lg hover:bg-white/10 text-white/60"
                >
                  ✕
                </button>
              </div>
              
              <div className="grid grid-cols-4 gap-4 mb-6">
                <MetricCard
                  title="Final Capital"
                  value={`$${(selectedSession.session?.final_capital || 0).toFixed(0)}`}
                  icon={Wallet}
                />
                <MetricCard
                  title="Total P&L"
                  value={`${(selectedSession.session?.total_pnl || 0) >= 0 ? '+' : ''}$${(selectedSession.session?.total_pnl || 0).toFixed(2)}`}
                  icon={DollarSign}
                  color={(selectedSession.session?.total_pnl || 0) >= 0 ? "green" : "red"}
                />
                <MetricCard
                  title="Win Rate"
                  value={`${((selectedSession.session?.win_rate || 0) * 100).toFixed(1)}%`}
                  icon={Target}
                />
                <MetricCard
                  title="Max Drawdown"
                  value={`${((selectedSession.session?.max_drawdown || 0) * 100).toFixed(1)}%`}
                  icon={Shield}
                  color="red"
                />
              </div>

              {/* Session Trades */}
              <h4 className="text-white font-medium mb-2">Session Trades ({selectedSession.trades?.length || 0})</h4>
              <div className="max-h-64 overflow-y-auto rounded-lg bg-black/20">
                <table className="w-full text-sm">
                  <thead className="bg-white/5 sticky top-0">
                    <tr>
                      <th className="py-2 px-3 text-left text-xs text-white/60">Type</th>
                      <th className="py-2 px-3 text-left text-xs text-white/60">Strategy</th>
                      <th className="py-2 px-3 text-left text-xs text-white/60">Side</th>
                      <th className="py-2 px-3 text-left text-xs text-white/60">Price</th>
                      <th className="py-2 px-3 text-left text-xs text-white/60">P&L</th>
                      <th className="py-2 px-3 text-left text-xs text-white/60">RL Reward</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedSession.trades?.slice(0, 50).map((trade, idx) => (
                      <tr key={idx} className="border-b border-white/5">
                        <td className="py-2 px-3 text-white/80">{trade.type}</td>
                        <td className="py-2 px-3 text-white/60">{trade.strategy}</td>
                        <td className="py-2 px-3 text-white/80">{trade.side}</td>
                        <td className="py-2 px-3 text-white/80">${trade.price?.toFixed(4)}</td>
                        <td className={`py-2 px-3 ${(trade.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {trade.type === 'exit' ? `$${(trade.pnl || 0).toFixed(2)}` : '-'}
                        </td>
                        <td className="py-2 px-3 text-purple-400">
                          {trade.reward_signal?.toFixed(3) || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Optimizer Tab */}
      {activeTab === 'optimizer' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-gradient-to-br from-purple-500/10 to-pink-500/10 border border-purple-500/20 p-6">
            <div className="flex items-start justify-between mb-6">
              <div>
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-6 h-6 text-purple-400" />
                  Strategy Optimizer
                </h3>
                <p className="text-white/60 text-sm mt-1">
                  Automatically tune entry/exit thresholds, position sizing, and strategy weights from paper trading results
                </p>
              </div>
              <button
                onClick={applyOptimizedParams}
                disabled={!optimizerParams}
                className="px-4 py-2 rounded-lg bg-purple-500/20 border border-purple-500/30 text-purple-400 hover:bg-purple-500/30 disabled:opacity-50 flex items-center gap-2"
              >
                <CheckCircle className="w-4 h-4" />
                Apply Parameters
              </button>
            </div>

            {optimizerParams && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Entry Thresholds */}
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                    <Crosshair className="w-4 h-4 text-cyan-400" />
                    Entry Thresholds
                  </h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-white/60">Min RL Confidence</span>
                      <span className="text-white">{(optimizerParams.min_rl_confidence * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Min Sentiment</span>
                      <span className="text-white">{(optimizerParams.min_sentiment_strength * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Min Sharp Align</span>
                      <span className="text-white">{(optimizerParams.min_sharp_alignment * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>

                {/* Exit Thresholds */}
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                    <Target className="w-4 h-4 text-green-400" />
                    Exit Thresholds
                  </h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-white/60">Take Profit</span>
                      <span className="text-green-400">{(optimizerParams.take_profit_pct * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Stop Loss</span>
                      <span className="text-red-400">{(optimizerParams.stop_loss_pct * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Max Hold</span>
                      <span className="text-white">{optimizerParams.max_hold_hours}h</span>
                    </div>
                  </div>
                </div>

                {/* Position Sizing */}
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                    <Scale className="w-4 h-4 text-orange-400" />
                    Position Sizing
                  </h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-white/60">Kelly Fraction</span>
                      <span className="text-white">{(optimizerParams.kelly_fraction * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Max Position</span>
                      <span className="text-white">{(optimizerParams.max_position_pct * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Min Size</span>
                      <span className="text-white">${optimizerParams.min_position_size}</span>
                    </div>
                  </div>
                </div>

                {/* Strategy Weights */}
                <div className="rounded-lg bg-white/5 p-4 md:col-span-2 lg:col-span-3">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                    <PieChart className="w-4 h-4 text-purple-400" />
                    Strategy Weights
                  </h4>
                  <div className="flex gap-4 flex-wrap">
                    {optimizerParams.strategy_weights && Object.entries(optimizerParams.strategy_weights).map(([strategy, weight]) => {
                      const info = STRATEGY_INFO[strategy];
                      return (
                        <div key={strategy} className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: info?.color }} />
                          <span className="text-white/80">{info?.name || strategy}</span>
                          <span className="text-white font-medium">{(weight * 100).toFixed(0)}%</span>
                        </div>
                      );
                    })}
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
            <h3 className="text-xl font-bold text-white flex items-center gap-2 mb-6">
              <Brain className="w-6 h-6 text-blue-400" />
              Reinforcement Learning Status
            </h3>

            {rlStats && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <MetricCard
                  title="Training Iterations"
                  value={rlStats.total_iterations?.toLocaleString() || 0}
                  icon={Zap}
                  color="blue"
                />
                <MetricCard
                  title="Exploration Rate"
                  value={`${((rlStats.epsilon || 0) * 100).toFixed(1)}%`}
                  subtitle="Lower = more exploitation"
                  icon={Crosshair}
                  color="purple"
                />
                <MetricCard
                  title="Avg Reward (100)"
                  value={(rlStats.avg_reward_100 || 0).toFixed(3)}
                  icon={Award}
                  color={rlStats.avg_reward_100 >= 0 ? "green" : "red"}
                />
                <MetricCard
                  title="Experience Buffer"
                  value={rlStats.buffer_size?.toLocaleString() || 0}
                  subtitle={`Max: 10,000`}
                  icon={Database}
                  color="cyan"
                />
              </div>
            )}

            {/* Q-Table Stats */}
            {rlStats && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3">Q-Table Analysis</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-white/60">Table Size</span>
                      <span className="text-white">{rlStats.q_table_size?.join(' x ')}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Non-zero %</span>
                      <span className="text-white">{(rlStats.q_table_nonzero_pct || 0).toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Mean Q-Value</span>
                      <span className="text-white">{(rlStats.q_table_mean || 0).toFixed(4)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/60">Max Q-Value</span>
                      <span className="text-white">{(rlStats.q_table_max || 0).toFixed(4)}</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg bg-white/5 p-4">
                  <h4 className="text-white font-medium mb-3">Action Distribution</h4>
                  <div className="space-y-2">
                    {rlStats.action_distribution && Object.entries(rlStats.action_distribution).map(([action, count]) => (
                      <div key={action} className="flex items-center gap-2">
                        <span className="text-white/60 text-sm w-24">{action}</span>
                        <div className="flex-1 bg-white/10 rounded-full h-2">
                          <div 
                            className="bg-cyan-500 h-2 rounded-full"
                            style={{ width: `${(count / Math.max(...Object.values(rlStats.action_distribution))) * 100}%` }}
                          />
                        </div>
                        <span className="text-white text-sm w-12 text-right">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="mt-6 p-4 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <p className="text-blue-400 text-sm">
                <strong>How RL Learning Works:</strong> During paper trading, every trade outcome (profit/loss) is converted into a reward signal. 
                The Q-Learning algorithm updates its value estimates, learning which actions work best in different market conditions. 
                Over time, the model will prefer strategies and actions that historically produced positive returns.
              </p>
            </div>
          </div>

          {/* AI Session Learning Stats */}
          {aiStats?.session_learning && (
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-purple-400" />
                  Session Learning Progress
                </h3>
                <button
                  onClick={trainRLFromSession}
                  disabled={!running}
                  className="px-4 py-2 rounded-lg bg-purple-500/20 border border-purple-500/30 text-purple-400 hover:bg-purple-500/30 disabled:opacity-50 flex items-center gap-2 text-sm"
                >
                  <Brain className="w-4 h-4" />
                  Force Train Now
                </button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="text-center p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-white/50">Trades Fed to RL</p>
                  <p className="text-xl font-bold text-cyan-400">{aiStats.session_learning.trades_fed_to_rl}</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-white/50">Total Reward Signals</p>
                  <p className={`text-xl font-bold ${aiStats.session_learning.total_reward_signals >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {aiStats.session_learning.total_reward_signals?.toFixed(2)}
                  </p>
                </div>
                <div className="text-center p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-white/50">Avg Reward</p>
                  <p className={`text-xl font-bold ${aiStats.session_learning.avg_reward >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {aiStats.session_learning.avg_reward?.toFixed(3)}
                  </p>
                </div>
                <div className="text-center p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-white/50">Positive Rewards</p>
                  <p className="text-xl font-bold text-green-400">{aiStats.session_learning.positive_rewards}</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-white/5">
                  <p className="text-xs text-white/50">Negative Rewards</p>
                  <p className="text-xl font-bold text-red-400">{aiStats.session_learning.negative_rewards}</p>
                </div>
              </div>
            </div>
          )}

          {/* AI Signal Usage */}
          {aiStats?.signal_usage && (
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
                <Activity className="w-5 h-5 text-cyan-400" />
                AI Signal Integration
                <span className="text-xs text-white/40 ml-2">(Signals used for trade decisions)</span>
              </h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 rounded-lg bg-gradient-to-br from-purple-500/10 to-purple-500/5 border border-purple-500/20">
                  <p className="text-xs text-white/50 mb-1">Volatility Signals</p>
                  <p className="text-2xl font-bold text-purple-400">{aiStats.signal_usage.volatility_signals}</p>
                  <p className="text-xs text-white/40 mt-1">Market volatility predictions</p>
                </div>
                <div className="text-center p-4 rounded-lg bg-gradient-to-br from-cyan-500/10 to-cyan-500/5 border border-cyan-500/20">
                  <p className="text-xs text-white/50 mb-1">Sentiment Signals</p>
                  <p className="text-2xl font-bold text-cyan-400">{aiStats.signal_usage.sentiment_signals}</p>
                  <p className="text-xs text-white/40 mt-1">Social sentiment analysis</p>
                </div>
                <div className="text-center p-4 rounded-lg bg-gradient-to-br from-orange-500/10 to-orange-500/5 border border-orange-500/20">
                  <p className="text-xs text-white/50 mb-1">Sharp Trader Signals</p>
                  <p className="text-2xl font-bold text-orange-400">{aiStats.signal_usage.sharp_signals}</p>
                  <p className="text-xs text-white/40 mt-1">Professional trader tracking</p>
                </div>
              </div>
            </div>
          )}

          {/* Learning Status Info */}
          <div className="rounded-xl bg-gradient-to-br from-green-500/10 to-emerald-500/10 border border-green-500/20 p-6">
            <h3 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
              <CheckCircle className="w-5 h-5 text-green-400" />
              Continuous Learning Status
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
                <div className={`w-3 h-3 rounded-full ${running ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`}></div>
                <div>
                  <p className="text-white text-sm font-medium">RL Learning</p>
                  <p className="text-xs text-white/40">{running ? 'Active - Learning from every trade' : 'Inactive'}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
                <div className={`w-3 h-3 rounded-full ${running ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`}></div>
                <div>
                  <p className="text-white text-sm font-medium">Strategy Optimization</p>
                  <p className="text-xs text-white/40">{running ? 'Data collection active' : 'Run optimizer after session'}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
                <div className={`w-3 h-3 rounded-full ${running ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`}></div>
                <div>
                  <p className="text-white text-sm font-medium">Model Saving</p>
                  <p className="text-xs text-white/40">{running ? 'Auto-saves every 10 trades' : 'Saved on stop'}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PaperTrading;
