import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { TrendingUp, TrendingDown, DollarSign, Activity, Target, Zap, Clock, Timer, BarChart3, Layers, Brain, AlertTriangle, RefreshCw } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Dashboard = () => {
  const [performance, setPerformance] = useState(null);
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [tradeStats, setTradeStats] = useState(null);
  const [status, setStatus] = useState(null);
  const [rlStats, setRlStats] = useState(null);
  const [historicalStats, setHistoricalStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pnlHistory, setPnlHistory] = useState([]);
  const tradesFeedRef = useRef(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  // Track P&L history for chart
  useEffect(() => {
    if (tradeStats?.total_pnl !== undefined) {
      setPnlHistory(prev => {
        const newEntry = {
          time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' }),
          pnl: tradeStats.total_pnl
        };
        const updated = [...prev, newEntry].slice(-30); // Keep last 30 points
        return updated;
      });
    }
  }, [tradeStats?.total_pnl]);

  const fetchData = async () => {
    try {
      const [perfRes, posRes, tradesRes, statsRes, statusRes, rlRes, histRes] = await Promise.all([
        axios.get(`${API}/performance`),
        axios.get(`${API}/positions`),
        axios.get(`${API}/trades?limit=50`),
        axios.get(`${API}/trades/stats`),
        axios.get(`${API}/status`),
        axios.get(`${API}/rl/stats`).catch(() => ({ data: null })),
        axios.get(`${API}/historical/stats`).catch(() => ({ data: null }))
      ]);
      
      setPerformance(perfRes.data);
      setPositions(posRes.data.positions || []);
      setTrades(tradesRes.data.trades || []);
      setTradeStats(statsRes.data);
      setStatus(statusRes.data);
      setRlStats(rlRes.data);
      setHistoricalStats(histRes.data);
      setLoading(false);
    } catch (e) {
      console.error('Error fetching data:', e);
      setLoading(false);
    }
  };

  const startBot = async () => {
    try {
      await axios.post(`${API}/bot/start`);
      fetchData();
    } catch (e) {
      console.error('Failed to start bot:', e);
    }
  };

  const stopBot = async () => {
    try {
      await axios.post(`${API}/bot/stop`);
      fetchData();
    } catch (e) {
      console.error('Failed to stop bot:', e);
    }
  };

  const setMode = async (mode) => {
    if (mode === 'live' && status?.trading_mode !== 'live') {
      if (status?.trading_mode === 'backtest') {
        await axios.post(`${API}/backtest/stop`).catch(() => {});
      }
      await startBot();
    } else if (mode === 'backtest' && status?.trading_mode !== 'backtest') {
      if (status?.bot_running) {
        await stopBot();
      }
    } else if (mode === 'stopped') {
      if (status?.bot_running) {
        await stopBot();
      }
      if (status?.trading_mode === 'backtest') {
        await axios.post(`${API}/backtest/stop`).catch(() => {});
      }
    }
    fetchData();
  };

  const triggerDataCollection = async () => {
    try {
      await axios.post(`${API}/historical/collect`);
      fetchData();
    } catch (e) {
      console.error('Failed to collect data:', e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="dashboard-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  const tradingMode = status?.trading_mode || 'stopped';
  const botRunning = status?.bot_running || false;
  const pnl = tradeStats?.total_pnl || 0;
  const pnlPct = tradeStats?.pnl_pct || 0;
  const isProfitable = pnl >= 0;

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      
      {/* Mode Control Banner */}
      <div className="rounded-xl bg-gradient-to-r from-slate-800/80 to-slate-900/80 backdrop-blur-xl border border-white/10 p-6" data-testid="mode-control-banner">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-4">
          
          {/* Mode Buttons */}
          <div className="flex items-center gap-3">
            <span className="text-white/60 text-sm font-medium mr-2">MODE:</span>
            <button
              onClick={() => setMode('live')}
              data-testid="dashboard-live-btn"
              className={`px-6 py-3 rounded-xl font-bold text-sm transition-all duration-300 ${
                tradingMode === 'live'
                  ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white shadow-lg shadow-green-500/40 scale-105'
                  : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white border border-white/10'
              }`}
            >
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4" />
                LIVE TRADING
              </div>
            </button>
            
            <button
              onClick={() => setMode('backtest')}
              data-testid="dashboard-backtest-btn"
              className={`px-6 py-3 rounded-xl font-bold text-sm transition-all duration-300 ${
                tradingMode === 'backtest'
                  ? 'bg-gradient-to-r from-orange-500 to-amber-600 text-white shadow-lg shadow-orange-500/40 scale-105'
                  : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white border border-white/10'
              }`}
            >
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4" />
                BACKTEST
              </div>
            </button>

            <button
              onClick={() => setMode('stopped')}
              data-testid="dashboard-stop-btn"
              className={`px-6 py-3 rounded-xl font-bold text-sm transition-all duration-300 ${
                tradingMode === 'stopped'
                  ? 'bg-gradient-to-r from-red-500 to-rose-600 text-white shadow-lg shadow-red-500/40 scale-105'
                  : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white border border-white/10'
              }`}
            >
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-current" />
                STOP
              </div>
            </button>
          </div>

          {/* Current Mode Status */}
          <div className="flex items-center gap-4">
            <div className={`flex items-center gap-3 px-6 py-3 rounded-xl ${
              tradingMode === 'live' ? 'bg-green-500/20 border border-green-500/40' :
              tradingMode === 'backtest' ? 'bg-orange-500/20 border border-orange-500/40' :
              'bg-gray-500/20 border border-gray-500/40'
            }`} data-testid="current-mode-display">
              <div className={`w-3 h-3 rounded-full ${
                tradingMode === 'live' ? 'bg-green-400 animate-pulse' :
                tradingMode === 'backtest' ? 'bg-orange-400 animate-pulse' :
                'bg-gray-400'
              }`} />
              <span className={`font-bold text-lg ${
                tradingMode === 'live' ? 'text-green-400' :
                tradingMode === 'backtest' ? 'text-orange-400' :
                'text-gray-400'
              }`}>
                {tradingMode === 'live' ? 'LIVE TRADING ACTIVE' :
                 tradingMode === 'backtest' ? 'BACKTESTING MODE' :
                 'SYSTEM STOPPED'}
              </span>
            </div>
            
            {tradingMode === 'live' && (
              <button
                onClick={botRunning ? stopBot : startBot}
                data-testid="bot-control-btn"
                className={`px-5 py-3 rounded-xl font-bold text-sm transition-all ${
                  botRunning 
                    ? 'bg-red-500 hover:bg-red-600 text-white' 
                    : 'bg-green-500 hover:bg-green-600 text-white'
                }`}
              >
                {botRunning ? 'PAUSE BOT' : 'START BOT'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* P&L Hero Card with Real-time Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className={`lg:col-span-1 rounded-xl p-6 ${
          isProfitable 
            ? 'bg-gradient-to-br from-green-900/40 to-emerald-900/40 border border-green-500/30' 
            : 'bg-gradient-to-br from-red-900/40 to-rose-900/40 border border-red-500/30'
        }`} data-testid="pnl-hero-card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-white/60 text-sm font-medium mb-1">Total Profit & Loss</p>
              <h2 className={`text-4xl font-bold ${isProfitable ? 'text-green-400' : 'text-red-400'}`} data-testid="total-pnl-value">
                {isProfitable ? '+' : ''}{pnl.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
              </h2>
              <span className={`text-lg font-semibold ${isProfitable ? 'text-green-400/80' : 'text-red-400/80'}`}>
                ({isProfitable ? '+' : ''}{pnlPct.toFixed(2)}%)
              </span>
            </div>
            <div className={`w-16 h-16 rounded-2xl flex items-center justify-center ${
              isProfitable ? 'bg-green-500/20' : 'bg-red-500/20'
            }`}>
              {isProfitable ? (
                <TrendingUp className="w-8 h-8 text-green-400" />
              ) : (
                <TrendingDown className="w-8 h-8 text-red-400" />
              )}
            </div>
          </div>
        </div>

        {/* Real-time P&L Chart */}
        <div className="lg:col-span-2 rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-4" data-testid="realtime-pnl-chart">
          <h3 className="text-sm font-semibold text-white/80 mb-2">Real-time P&L</h3>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={pnlHistory}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="time" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
              <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
              <Tooltip 
                contentStyle={{backgroundColor: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', fontSize: '12px'}}
                labelStyle={{color: 'white'}}
              />
              <Line type="monotone" dataKey="pnl" stroke={isProfitable ? '#4ade80' : '#f87171'} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Trade Frequency Stats - Top Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Live Trades" value={tradeStats?.live_trades || 0} subtitle="Currently Active" icon={Zap} color="cyan" testId="live-trades-card" />
        <StatCard title="Last 10 Min" value={tradeStats?.trades_10min || 0} subtitle="trades executed" icon={Timer} color="blue" testId="trades-10min-card" />
        <StatCard title="Last 30 Min" value={tradeStats?.trades_30min || 0} subtitle="trades executed" icon={Clock} color="purple" testId="trades-30min-card" />
        <StatCard title="Last 1 Hour" value={tradeStats?.trades_1hr || 0} subtitle="trades executed" icon={Clock} color="indigo" testId="trades-1hr-card" />
      </div>

      {/* Second Row Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Last 24 Hours" value={tradeStats?.trades_24hr || 0} subtitle="trades executed" icon={Activity} color="orange" testId="trades-24hr-card" />
        <StatCard title="Win Rate" value={`${((performance?.win_rate || 0) * 100).toFixed(1)}%`} subtitle={`${performance?.num_trades || 0} total trades`} icon={Target} color="green" testId="win-rate-card" />
        <StatCard title="Sharpe Ratio" value={performance?.sharpe_ratio?.toFixed(2) || '0.00'} subtitle={`Max DD: ${((performance?.max_drawdown || 0) * 100).toFixed(1)}%`} icon={TrendingUp} color="teal" testId="sharpe-ratio-card" />
        <StatCard title="Active Positions" value={positions.length} subtitle="open positions" icon={Layers} color="pink" testId="active-positions-card" />
      </div>

      {/* AI & Data Status Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* RL Engine Status */}
        <div className="rounded-xl bg-gradient-to-br from-purple-900/30 to-indigo-900/30 border border-purple-500/20 p-4" data-testid="rl-status-card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Brain className="w-5 h-5 text-purple-400" />
              <h3 className="text-sm font-semibold text-white">RL Engine</h3>
            </div>
            <span className="text-xs px-2 py-1 rounded-full bg-purple-500/20 text-purple-400">
              {rlStats?.total_iterations || 0} iterations
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="text-white/60">Epsilon: <span className="text-white">{(rlStats?.epsilon || 0).toFixed(3)}</span></div>
            <div className="text-white/60">Buffer: <span className="text-white">{rlStats?.buffer_size || 0}</span></div>
            <div className="text-white/60">Avg Reward: <span className="text-cyan-400">{(rlStats?.avg_reward_100 || 0).toFixed(4)}</span></div>
          </div>
        </div>

        {/* Historical Data Status */}
        <div className="rounded-xl bg-gradient-to-br from-blue-900/30 to-cyan-900/30 border border-blue-500/20 p-4" data-testid="data-status-card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-blue-400" />
              <h3 className="text-sm font-semibold text-white">Historical Data</h3>
            </div>
            <button 
              onClick={triggerDataCollection}
              className="text-xs px-2 py-1 rounded-full bg-blue-500/20 text-blue-400 hover:bg-blue-500/40 transition flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" /> Collect
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="text-white/60">Snapshots: <span className="text-white">{(historicalStats?.total_snapshots || 0).toLocaleString()}</span></div>
            <div className="text-white/60">Markets: <span className="text-white">{historicalStats?.unique_markets || 0}</span></div>
            <div className="text-white/60">Status: <span className={historicalStats?.collector_running ? 'text-green-400' : 'text-gray-400'}>{historicalStats?.collector_running ? 'Running' : 'Stopped'}</span></div>
          </div>
        </div>

        {/* Risk Alert */}
        <div className="rounded-xl bg-gradient-to-br from-yellow-900/30 to-orange-900/30 border border-yellow-500/20 p-4" data-testid="risk-status-card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
              <h3 className="text-sm font-semibold text-white">Risk Status</h3>
            </div>
            <span className={`text-xs px-2 py-1 rounded-full ${
              (performance?.max_drawdown || 0) < 0.1 ? 'bg-green-500/20 text-green-400' :
              (performance?.max_drawdown || 0) < 0.2 ? 'bg-yellow-500/20 text-yellow-400' :
              'bg-red-500/20 text-red-400'
            }`}>
              {(performance?.max_drawdown || 0) < 0.1 ? 'Low Risk' :
               (performance?.max_drawdown || 0) < 0.2 ? 'Medium' : 'High Risk'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="text-white/60">Max DD: <span className="text-white">{((performance?.max_drawdown || 0) * 100).toFixed(1)}%</span></div>
            <div className="text-white/60">Positions: <span className="text-white">{positions.length}</span></div>
            <div className="text-white/60">Kelly: <span className="text-cyan-400">{status?.configuration?.kelly_fraction || 0.25}</span></div>
          </div>
        </div>
      </div>

      {/* Live Trade Feed and Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* P&L Chart */}
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="pnl-chart">
          <h3 className="text-lg font-semibold text-white mb-4">P&L by Trade</h3>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={trades.slice(0, 15).reverse().map((t, i) => ({
              name: `#${i+1}`,
              pnl: t.pnl || (t.price * t.shares - (t.fee || 0)),
              strategy: t.strategy
            }))}>
              <defs>
                <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
              <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
              <Tooltip 
                contentStyle={{backgroundColor: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px'}}
                labelStyle={{color: 'white'}}
              />
              <Area type="monotone" dataKey="pnl" stroke="#06b6d4" fillOpacity={1} fill="url(#colorPnl)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Live Trade Feed */}
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="trade-feed">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white">Live Trade Feed</h3>
            <span className="text-xs text-white/40">Last {trades.length} trades</span>
          </div>
          <div ref={tradesFeedRef} className="space-y-2 max-h-[280px] overflow-y-auto scrollbar-thin scrollbar-thumb-white/10">
            {trades.length === 0 ? (
              <p className="text-center text-white/60 py-8">No trades yet</p>
            ) : (
              trades.slice(0, 12).map((trade, idx) => (
                <div 
                  key={idx} 
                  className={`flex items-center justify-between p-3 rounded-lg transition ${
                    idx === 0 ? 'bg-cyan-500/10 border border-cyan-500/20' : 'bg-white/5 hover:bg-white/10'
                  }`} 
                  data-testid={`trade-item-${idx}`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${trade.side === 'BUY' ? 'bg-green-400' : 'bg-red-400'}`} />
                    <div>
                      <p className="text-sm font-medium text-white">{trade.strategy || 'Manual'}</p>
                      <p className="text-xs text-white/60">{trade.side} • {(trade.shares || 0).toFixed(2)} shares</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`text-sm font-semibold ${(trade.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${((trade.price || 0) * (trade.shares || 0)).toFixed(2)}
                    </p>
                    <p className="text-xs text-white/60">{trade.execution_latency_ms?.toFixed(0) || '0'}ms</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Open Positions Table */}
      <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="open-positions">
        <h3 className="text-lg font-semibold text-white mb-4">Open Positions ({positions.length})</h3>
        {positions.length === 0 ? (
          <p className="text-center text-white/60 py-8">No open positions</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left text-sm font-medium text-white/60 pb-3">Market ID</th>
                  <th className="text-left text-sm font-medium text-white/60 pb-3">Strategy</th>
                  <th className="text-right text-sm font-medium text-white/60 pb-3">Side</th>
                  <th className="text-right text-sm font-medium text-white/60 pb-3">Shares</th>
                  <th className="text-right text-sm font-medium text-white/60 pb-3">Avg Price</th>
                  <th className="text-right text-sm font-medium text-white/60 pb-3">Current</th>
                  <th className="text-right text-sm font-medium text-white/60 pb-3">P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx} className="border-b border-white/5" data-testid={`position-row-${idx}`}>
                    <td className="py-3 text-sm text-white/80">{(pos.market_id || '').substring(0, 12)}...</td>
                    <td className="py-3 text-sm text-cyan-400">{pos.strategy || 'N/A'}</td>
                    <td className="py-3 text-sm text-right text-white/80">{pos.side || 'N/A'}</td>
                    <td className="py-3 text-sm text-right text-white/80">{(pos.shares || 0).toFixed(2)}</td>
                    <td className="py-3 text-sm text-right text-white/80">${(pos.avg_price || 0).toFixed(3)}</td>
                    <td className="py-3 text-sm text-right text-white/80">${(pos.current_price || 0).toFixed(3)}</td>
                    <td className={`py-3 text-sm text-right font-semibold ${(pos.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${(pos.unrealized_pnl || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

// Stat Card Component
const StatCard = ({ title, value, subtitle, icon: Icon, color, testId }) => {
  const colorClasses = {
    cyan: 'from-cyan-400 to-cyan-600',
    blue: 'from-blue-400 to-blue-600',
    purple: 'from-purple-400 to-purple-600',
    indigo: 'from-indigo-400 to-indigo-600',
    orange: 'from-orange-400 to-orange-600',
    green: 'from-green-400 to-green-600',
    teal: 'from-teal-400 to-teal-600',
    pink: 'from-pink-400 to-pink-600'
  };

  return (
    <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-white/5 to-white/10 backdrop-blur-xl border border-white/10 p-5 hover:border-white/20 transition-all" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-white/60 mb-1 uppercase tracking-wide">{title}</p>
          <h3 className="text-2xl font-bold text-white mb-0.5">{value}</h3>
          <p className="text-xs text-cyan-400">{subtitle}</p>
        </div>
        <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${colorClasses[color]} flex items-center justify-center`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
