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
      setPositions(positionsRes.data?.positions || []);
      setTrades(tradesRes.data?.trades || []);
      setAnalytics(analyticsRes.data);
    } catch (e) {
      console.error('Error fetching data:', e);
    }
  }, []);

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
    
    const interval = setInterval(() => {
      fetchData();
      if (running) {
        fetchRlStats();
      }
    }, 5000);
    
    return () => clearInterval(interval);
  }, [fetchData, running]);

  const startPaperTrading = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`${API}/paper/start?initial_capital=${initialCapital}`);
      toast.success(`Paper trading started! Session: ${response.data.session_id}`);
      setRunning(true);
      fetchData();
    } catch (e) {
      toast.error(e.response?.data?.message || 'Failed to start paper trading');
    } finally {
      setLoading(false);
    }
  };

  const stopPaperTrading = async () => {
    setLoading(true);
    try {
      const response = await axios.post(`${API}/paper/stop`);
      toast.success('Paper trading stopped');
      setRunning(false);
      setStatus(response.data?.final_status);
      fetchSessions();
    } catch (e) {
      toast.error('Failed to stop paper trading');
    } finally {
      setLoading(false);
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
              ? 'bg-blue-500/20 border-blue-500/30' 
              : 'bg-white/5 border-white/10'
          }`}>
            <div className={`w-2 h-2 rounded-full ${running ? 'bg-blue-400 animate-pulse' : 'bg-gray-400'}`}></div>
            <span className={`text-sm ${running ? 'text-blue-400' : 'text-white/60'}`}>
              {running ? '📝 PAPER TRADING' : 'Stopped'}
            </span>
          </div>
          
          {/* Start/Stop Button */}
          {running ? (
            <button
              onClick={stopPaperTrading}
              disabled={loading}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-red-500/20 border border-red-500/30 text-red-400 hover:bg-red-500/30 transition-colors"
              data-testid="stop-paper-trading-btn"
            >
              <Square className="w-4 h-4" />
              Stop Session
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                className="w-28 px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white text-sm"
                placeholder="Capital"
              />
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

          {/* Equity Curve */}
          {equityCurveData.length > 0 && (
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <LineChartIcon className="w-5 h-5 text-cyan-400" />
                Equity Curve (Live)
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityCurveData}>
                    <defs>
                      <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis 
                      dataKey="timestamp" 
                      stroke="rgba(255,255,255,0.4)"
                      tick={{ fontSize: 10 }}
                      tickFormatter={(val) => new Date(val).toLocaleTimeString()}
                    />
                    <YAxis stroke="rgba(255,255,255,0.4)" tick={{ fontSize: 10 }} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.1)' }}
                      labelStyle={{ color: '#94a3b8' }}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="pnl" 
                      stroke="#06b6d4" 
                      fill="url(#pnlGradient)" 
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Strategy Performance & Positions Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Strategy Performance */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <PieChart className="w-5 h-5 text-purple-400" />
                Strategy Performance
              </h3>
              {status?.strategy_stats && (
                <div className="space-y-3">
                  {Object.entries(status.strategy_stats).map(([strategy, data]) => {
                    const winRate = data.trades > 0 ? (data.wins / data.trades * 100) : 0;
                    const info = STRATEGY_INFO[strategy];
                    return (
                      <div key={strategy} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                        <div className="flex items-center gap-3">
                          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: info?.color }} />
                          <span className="text-sm text-white">{info?.name || strategy}</span>
                        </div>
                        <div className="flex items-center gap-4 text-sm">
                          <span className="text-white/60">{data.trades} trades</span>
                          <span className="text-white/60">{winRate.toFixed(0)}% win</span>
                          <span className={data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {data.pnl >= 0 ? '+' : ''}${data.pnl.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Open Positions */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Layers className="w-5 h-5 text-orange-400" />
                Open Positions ({positions.length})
              </h3>
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {positions.length > 0 ? positions.map((pos, idx) => (
                  <PositionCard key={idx} position={pos} />
                )) : (
                  <p className="text-white/40 text-center py-8">No open positions</p>
                )}
              </div>
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
        </div>
      )}
    </div>
  );
};

export default PaperTrading;
