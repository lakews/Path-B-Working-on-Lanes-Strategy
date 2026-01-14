import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell } from 'recharts';
import { 
  TrendingUp, TrendingDown, DollarSign, Activity, Target, Zap, Clock, Timer, 
  BarChart3, Layers, Brain, AlertTriangle, RefreshCw, Play, Pause, Settings,
  ArrowUpRight, ArrowDownRight, Percent, Shield, Cpu, Database, Wifi, WifiOff
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444'];

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
  const [trainingRL, setTrainingRL] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const tradesFeedRef = useRef(null);

  const fetchData = useCallback(async () => {
    try {
      const [perfRes, posRes, tradesRes, statsRes, statusRes, rlRes, histRes] = await Promise.all([
        axios.get(`${API}/performance`),
        axios.get(`${API}/positions`),
        axios.get(`${API}/trades?limit=50`),
        axios.get(`${API}/trades/stats`),
        axios.get(`${API}/status`),
        axios.get(`${API}/rl/detailed-stats`).catch(() => ({ data: { rl_stats: null } })),
        axios.get(`${API}/historical/stats`).catch(() => ({ data: null }))
      ]);
      
      setPerformance(perfRes.data);
      setPositions(posRes.data.positions || []);
      setTrades(tradesRes.data.trades || []);
      setTradeStats(statsRes.data);
      setStatus(statusRes.data);
      setRlStats(rlRes.data?.rl_stats || rlRes.data);
      setHistoricalStats(histRes.data);
      setLoading(false);
    } catch (e) {
      console.error('Error fetching data:', e);
      setLoading(false);
    }
  }, []);

  // Initial fetch and polling
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    let ws = null;
    let reconnectTimeout = null;
    
    const connectWs = () => {
      try {
        // WebSocket endpoint is at /ws (not /ws/status)
        const wsUrl = BACKEND_URL.replace('https', 'wss').replace('http', 'ws') + '/ws';
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
          console.log('WebSocket connected');
          setWsConnected(true);
        };
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            // Handle different message types
            if (data.type === 'trade') {
              setTrades(prev => [data.trade, ...prev].slice(0, 50));
            } else if (data.type === 'position_update') {
              setPositions(data.positions || []);
            } else if (data.type === 'performance_update') {
              setPerformance(data.performance);
            } else if (data.type === 'status_update') {
              setStatus(data.status);
            }
          } catch (e) {
            console.error('Error parsing WebSocket message:', e);
          }
        };
        
        ws.onclose = () => {
          console.log('WebSocket disconnected');
          setWsConnected(false);
          // Reconnect after 5 seconds
          reconnectTimeout = setTimeout(connectWs, 5000);
        };
        
        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          setWsConnected(false);
        };
      } catch (e) {
        console.error('WS connection error:', e);
        setWsConnected(false);
      }
    };
    
    connectWs();
    
    return () => {
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // Track P&L history for chart
  const prevPnlRef = useRef(null);
  useEffect(() => {
    const currentPnl = tradeStats?.total_pnl;
    if (currentPnl !== undefined && currentPnl !== prevPnlRef.current) {
      prevPnlRef.current = currentPnl;
      const newEntry = {
        time: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' }),
        pnl: currentPnl
      };
      setPnlHistory(prev => [...prev, newEntry].slice(-30));
    }
  }, [tradeStats?.total_pnl]);

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

  // Train RL from all historical backtests
  const trainRLNow = async () => {
    setTrainingRL(true);
    try {
      // Get all backtest history
      const historyRes = await axios.get(`${API}/backtest/history?limit=100`);
      const backtests = historyRes.data?.history || [];
      
      if (backtests.length === 0) {
        alert('No backtests found. Run some backtests first to generate training data.');
        setTrainingRL(false);
        return;
      }

      // Train on each backtest
      let trained = 0;
      for (const bt of backtests) {
        try {
          await axios.post(`${API}/rl/learn-from-backtest/${bt.backtest_id}`);
          trained++;
        } catch (e) {
          console.error(`Failed to learn from ${bt.backtest_id}:`, e);
        }
      }
      
      // Refresh RL stats
      fetchData();
      alert(`RL Training Complete! Trained on ${trained} backtests.`);
    } catch (e) {
      console.error('RL Training failed:', e);
      alert('RL Training failed. Check console for details.');
    }
    setTrainingRL(false);
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

  // Strategy distribution for pie chart
  const strategyDist = trades.reduce((acc, t) => {
    const strat = t.strategy || 'Unknown';
    acc[strat] = (acc[strat] || 0) + 1;
    return acc;
  }, {});
  const pieData = Object.entries(strategyDist).map(([name, value]) => ({ name, value }));

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      
      {/* Hero Section - Redesigned Top */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 border border-white/10" data-testid="dashboard-hero">
        {/* Background Pattern */}
        <div className="absolute inset-0 opacity-30">
          <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl transform translate-x-1/2 -translate-y-1/2" />
          <div className="absolute bottom-0 left-0 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl transform -translate-x-1/2 translate-y-1/2" />
        </div>
        
        {/* Top Right Logo Badge */}
        <div className="absolute top-4 right-4 z-10">
          <div className="bg-white/10 backdrop-blur-md rounded-xl p-2 border border-white/20 shadow-lg">
            <img 
              src="https://customer-assets.emergentagent.com/job_aitrader-96/artifacts/adp4pnam_swaye%20logo.png" 
              alt="Swaye Ventures" 
              className="h-8 w-auto object-contain"
              style={{ imageRendering: 'crisp-edges', filter: 'contrast(1.1) brightness(1.05)' }}
            />
          </div>
        </div>
        
        <div className="relative p-6">
          {/* Top Row: Mode Control & Status */}
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 mb-6">
            {/* Left: Logo & Title */}
            <div className="flex items-center gap-4">
              <img 
                src="https://customer-assets.emergentagent.com/job_aitrader-96/artifacts/adp4pnam_swaye%20logo.png" 
                alt="Swaye Ventures" 
                className="h-12 w-auto"
              />
              <div>
                <h1 className="text-2xl font-bold text-white">APEX TRADER</h1>
                <p className="text-sm text-white/50">AI-Powered Prediction Market Engine</p>
              </div>
            </div>
            
            {/* Right: Mode Buttons & Status */}
            <div className="flex flex-wrap items-center gap-3">
              {/* Mode Switcher - Pill Style */}
              <div className="flex items-center bg-slate-800/80 rounded-xl p-1 border border-white/10">
                {[
                  { mode: 'live', icon: Zap, label: 'LIVE', activeColor: 'bg-gradient-to-r from-green-500 to-emerald-500' },
                  { mode: 'backtest', icon: BarChart3, label: 'BACKTEST', activeColor: 'bg-gradient-to-r from-orange-500 to-amber-500' },
                  { mode: 'stopped', icon: Pause, label: 'STOP', activeColor: 'bg-gradient-to-r from-red-500 to-rose-500' }
                ].map(({ mode, icon: Icon, label, activeColor }) => (
                  <button
                    key={mode}
                    onClick={() => setMode(mode)}
                    data-testid={`dashboard-${mode}-btn`}
                    className={`px-4 py-2 rounded-lg font-semibold text-sm transition-all duration-300 flex items-center gap-2 ${
                      tradingMode === mode
                        ? `${activeColor} text-white shadow-lg`
                        : 'text-white/60 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {label}
                  </button>
                ))}
              </div>
              
              {/* Status Badge */}
              <div className={`flex items-center gap-2 px-4 py-2 rounded-xl font-medium text-sm ${
                tradingMode === 'live' ? 'bg-green-500/20 border border-green-500/40 text-green-400' :
                tradingMode === 'backtest' ? 'bg-orange-500/20 border border-orange-500/40 text-orange-400' :
                'bg-slate-700/50 border border-white/10 text-white/50'
              }`} data-testid="current-mode-display">
                <div className={`w-2 h-2 rounded-full ${
                  tradingMode === 'live' ? 'bg-green-400 animate-pulse' :
                  tradingMode === 'backtest' ? 'bg-orange-400 animate-pulse' :
                  'bg-white/30'
                }`} />
                {tradingMode === 'live' ? 'LIVE TRADING' :
                 tradingMode === 'backtest' ? 'BACKTESTING' : 'ENGINE STOPPED'}
              </div>
              
              {/* WebSocket Status */}
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${wsConnected ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                {wsConnected ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
                <span className="text-xs font-medium">{wsConnected ? 'Connected' : 'Offline'}</span>
              </div>
              
              {/* Bot Control */}
              {tradingMode === 'live' && (
                <button
                  onClick={botRunning ? stopBot : startBot}
                  data-testid="bot-control-btn"
                  className={`px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all shadow-lg ${
                    botRunning 
                      ? 'bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white shadow-red-500/30' 
                      : 'bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white shadow-green-500/30'
                  }`}
                >
                  {botRunning ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  {botRunning ? 'STOP BOT' : 'START BOT'}
                </button>
              )}
            </div>
          </div>
          
          {/* Main Stats Row */}
          <div className="grid grid-cols-12 gap-4">
            {/* P&L Hero Card */}
            <div className={`col-span-12 lg:col-span-5 rounded-xl p-5 ${
              isProfitable 
                ? 'bg-gradient-to-br from-green-500/20 to-emerald-500/10 border border-green-500/30' 
                : 'bg-gradient-to-br from-red-500/20 to-rose-500/10 border border-red-500/30'
            }`} data-testid="pnl-hero-card">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white/50 text-xs font-medium mb-1 uppercase tracking-wider">Total P&L</p>
                  <div className="flex items-baseline gap-3">
                    <h2 className={`text-4xl font-bold tracking-tight ${isProfitable ? 'text-green-400' : 'text-red-400'}`} data-testid="total-pnl-value">
                      {isProfitable ? '+' : ''}{pnl.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
                    </h2>
                    <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-sm font-semibold ${
                      isProfitable ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {isProfitable ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {isProfitable ? '+' : ''}{pnlPct.toFixed(2)}%
                    </div>
                  </div>
                </div>
                <div className={`w-16 h-16 rounded-2xl flex items-center justify-center ${isProfitable ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                  {isProfitable ? <TrendingUp className="w-8 h-8 text-green-400" /> : <TrendingDown className="w-8 h-8 text-red-400" />}
                </div>
              </div>
              
              {/* Mini Stats Row */}
              <div className="flex items-center gap-6 mt-4 pt-4 border-t border-white/10">
                <div>
                  <p className="text-white/40 text-xs">Trades</p>
                  <p className="text-white font-semibold">{performance?.num_trades || 0}</p>
                </div>
                <div>
                  <p className="text-white/40 text-xs">Win Rate</p>
                  <p className="text-cyan-400 font-semibold">{((performance?.win_rate || 0) * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-white/40 text-xs">Sharpe</p>
                  <p className="text-purple-400 font-semibold">{performance?.sharpe_ratio?.toFixed(2) || '0.00'}</p>
                </div>
                <div>
                  <p className="text-white/40 text-xs">Max DD</p>
                  <p className="text-orange-400 font-semibold">{((performance?.max_drawdown || 0) * 100).toFixed(1)}%</p>
                </div>
              </div>
            </div>
            
            {/* Key Metrics Cards */}
            <div className="col-span-12 lg:col-span-3 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-white/5 border border-white/10 p-4 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-cyan-500/20 flex items-center justify-center">
                    <Target className="w-4 h-4 text-cyan-400" />
                  </div>
                  <span className="text-white/50 text-xs">Win Rate</span>
                </div>
                <p className="text-2xl font-bold text-white">{((performance?.win_rate || 0) * 100).toFixed(1)}%</p>
              </div>
              <div className="rounded-xl bg-white/5 border border-white/10 p-4 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
                    <TrendingUp className="w-4 h-4 text-purple-400" />
                  </div>
                  <span className="text-white/50 text-xs">Sharpe</span>
                </div>
                <p className="text-2xl font-bold text-white">{performance?.sharpe_ratio?.toFixed(2) || '0.00'}</p>
              </div>
              <div className="rounded-xl bg-white/5 border border-white/10 p-4 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-orange-500/20 flex items-center justify-center">
                    <Shield className="w-4 h-4 text-orange-400" />
                  </div>
                  <span className="text-white/50 text-xs">Max DD</span>
                </div>
                <p className="text-2xl font-bold text-white">{((performance?.max_drawdown || 0) * 100).toFixed(1)}%</p>
              </div>
              <div className="rounded-xl bg-white/5 border border-white/10 p-4 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center">
                    <Activity className="w-4 h-4 text-green-400" />
                  </div>
                  <span className="text-white/50 text-xs">Trades</span>
                </div>
                <p className="text-2xl font-bold text-white">{performance?.num_trades || 0}</p>
              </div>
            </div>
            
            {/* Real-time Chart */}
            <div className="col-span-12 lg:col-span-4 rounded-xl bg-white/5 border border-white/10 p-4" data-testid="realtime-pnl-chart">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                  <h3 className="text-sm font-semibold text-white">Real-time P&L</h3>
                </div>
                <span className="text-xs text-white/40">Last 30 updates</span>
              </div>
              <ResponsiveContainer width="100%" height={120}>
                <AreaChart data={pnlHistory}>
                  <defs>
                    <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={isProfitable ? '#4ade80' : '#f87171'} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={isProfitable ? '#4ade80' : '#f87171'} stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" stroke="rgba(255,255,255,0.2)" tick={{ fontSize: 9 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="rgba(255,255,255,0.2)" tick={{ fontSize: 9 }} width={45} axisLine={false} tickLine={false} />
                  <Tooltip 
                    contentStyle={{backgroundColor: 'rgba(15,23,42,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', fontSize: '11px'}}
                    formatter={(value) => [`$${value.toFixed(2)}`, 'P&L']}
                  />
                  <Area type="monotone" dataKey="pnl" stroke={isProfitable ? '#4ade80' : '#f87171'} strokeWidth={2} fill="url(#pnlGradient)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* Trade Frequency Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard title="Live" value={tradeStats?.live_trades || 0} icon={Zap} color="cyan" />
        <StatCard title="10 Min" value={tradeStats?.trades_10min || 0} icon={Timer} color="blue" />
        <StatCard title="30 Min" value={tradeStats?.trades_30min || 0} icon={Clock} color="purple" />
        <StatCard title="1 Hour" value={tradeStats?.trades_1hr || 0} icon={Clock} color="indigo" />
        <StatCard title="24 Hours" value={tradeStats?.trades_24hr || 0} icon={Activity} color="orange" />
      </div>

      {/* AI/Data/Risk Status Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        
        {/* RL Engine Status - With Train Button */}
        <div className="rounded-xl bg-gradient-to-br from-purple-900/30 to-indigo-900/30 border border-purple-500/20 p-4" data-testid="rl-status-card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Brain className="w-5 h-5 text-purple-400" />
              <h3 className="text-sm font-semibold text-white">RL Engine</h3>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-1 rounded-full ${
                (rlStats?.total_iterations || 0) > 0 ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'
              }`}>
                {(rlStats?.total_iterations || 0) > 0 ? 'Active' : 'Not Trained'}
              </span>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-2 text-xs mb-3">
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Iterations</p>
              <p className="text-lg font-bold text-purple-400">{rlStats?.total_iterations || 0}</p>
            </div>
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Exploration</p>
              <p className="text-lg font-bold text-cyan-400">{((rlStats?.epsilon || 0.15) * 100).toFixed(0)}%</p>
            </div>
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Avg Reward</p>
              <p className={`text-lg font-bold ${(rlStats?.avg_reward_100 || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {(rlStats?.avg_reward_100 || 0).toFixed(4)}
              </p>
            </div>
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Q-Table</p>
              <p className="text-lg font-bold text-yellow-400">{(rlStats?.q_table_nonzero_pct || 0).toFixed(2)}%</p>
            </div>
          </div>
          
          {/* Train RL Now Button */}
          <button
            onClick={trainRLNow}
            disabled={trainingRL}
            className="w-full py-2 rounded-lg bg-gradient-to-r from-purple-500 to-indigo-600 text-white text-sm font-bold hover:from-purple-600 hover:to-indigo-700 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            data-testid="train-rl-btn"
          >
            {trainingRL ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Training...
              </>
            ) : (
              <>
                <Cpu className="w-4 h-4" />
                Train RL Now
              </>
            )}
          </button>
        </div>

        {/* Historical Data Status */}
        <div className="rounded-xl bg-gradient-to-br from-blue-900/30 to-cyan-900/30 border border-blue-500/20 p-4" data-testid="data-status-card">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-blue-400" />
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
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Snapshots</p>
              <p className="text-lg font-bold text-white">{(historicalStats?.total_snapshots || 0).toLocaleString()}</p>
            </div>
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Markets</p>
              <p className="text-lg font-bold text-white">{historicalStats?.unique_markets || 0}</p>
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs">
            <span className="text-white/50">Collector:</span>
            <span className={historicalStats?.collector_running ? 'text-green-400' : 'text-gray-400'}>
              {historicalStats?.collector_running ? '● Running' : '○ Stopped'}
            </span>
          </div>
        </div>

        {/* Risk Status */}
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
              {(performance?.max_drawdown || 0) < 0.1 ? 'Low' :
               (performance?.max_drawdown || 0) < 0.2 ? 'Medium' : 'High'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Max Drawdown</p>
              <p className="text-lg font-bold text-white">{((performance?.max_drawdown || 0) * 100).toFixed(1)}%</p>
            </div>
            <div className="p-2 rounded-lg bg-white/5">
              <p className="text-white/50">Kelly Fraction</p>
              <p className="text-lg font-bold text-cyan-400">{status?.configuration?.kelly_fraction || 0.25}</p>
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between text-xs">
            <span className="text-white/50">Positions:</span>
            <span className="text-white font-medium">{positions.length} open</span>
          </div>
        </div>
      </div>

      {/* Charts & Feed Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* P&L Chart */}
        <div className="lg:col-span-2 rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="pnl-chart">
          <h3 className="text-lg font-semibold text-white mb-4">P&L by Trade</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={trades.slice(0, 20).reverse().map((t, i) => ({
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
              />
              <Area type="monotone" dataKey="pnl" stroke="#06b6d4" fillOpacity={1} fill="url(#colorPnl)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Strategy Distribution Pie */}
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="strategy-pie">
          <h3 className="text-lg font-semibold text-white mb-4">Strategy Distribution</h3>
          {pieData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={150}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={60}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1 mt-2">
                {pieData.slice(0, 4).map((entry, idx) => (
                  <div key={entry.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }} />
                      <span className="text-white/70">{entry.name}</span>
                    </div>
                    <span className="text-white font-medium">{entry.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-white/40">No trade data</div>
          )}
        </div>
      </div>

      {/* Live Trade Feed */}
      <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="trade-feed">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">Live Trade Feed</h3>
          <span className="text-xs text-white/40">{trades.length} trades</span>
        </div>
        <div ref={tradesFeedRef} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[300px] overflow-y-auto">
          {trades.length === 0 ? (
            <p className="text-center text-white/60 py-8 col-span-full">No trades yet</p>
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
                    <p className="text-xs text-white/60">{trade.side} • {(trade.shares || 0).toFixed(2)}</p>
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

      {/* Open Positions */}
      {positions.length > 0 && (
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="open-positions">
          <h3 className="text-lg font-semibold text-white mb-4">Open Positions ({positions.length})</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left text-xs font-medium text-white/60 pb-3">Market</th>
                  <th className="text-left text-xs font-medium text-white/60 pb-3">Strategy</th>
                  <th className="text-right text-xs font-medium text-white/60 pb-3">Side</th>
                  <th className="text-right text-xs font-medium text-white/60 pb-3">Shares</th>
                  <th className="text-right text-xs font-medium text-white/60 pb-3">Entry</th>
                  <th className="text-right text-xs font-medium text-white/60 pb-3">Current</th>
                  <th className="text-right text-xs font-medium text-white/60 pb-3">P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx} className="border-b border-white/5" data-testid={`position-row-${idx}`}>
                    <td className="py-3 text-sm text-white/80">{(pos.market_id || '').substring(0, 12)}...</td>
                    <td className="py-3 text-sm text-cyan-400">{pos.strategy || 'N/A'}</td>
                    <td className="py-3 text-sm text-right">
                      <span className={`px-2 py-0.5 rounded text-xs ${pos.side === 'BUY' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                        {pos.side || 'N/A'}
                      </span>
                    </td>
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
        </div>
      )}

      {/* Live Trading Performance Tables */}
      {trades.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Strategy Performance Table */}
          <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="live-strategy-performance">
            <div className="flex items-center gap-2 mb-4">
              <Zap className="w-5 h-5 text-cyan-400" />
              <h3 className="text-lg font-semibold text-white">Strategy Performance</h3>
            </div>
            {(() => {
              // Calculate strategy performance from trades
              const strategyStats = trades.reduce((acc, t) => {
                const strategy = t.strategy || 'Unknown';
                if (!acc[strategy]) {
                  acc[strategy] = { pnl: 0, trades: 0, wins: 0 };
                }
                acc[strategy].pnl += t.pnl || 0;
                acc[strategy].trades += 1;
                if ((t.pnl || 0) > 0) acc[strategy].wins += 1;
                return acc;
              }, {});
              
              const strategyEntries = Object.entries(strategyStats);
              const totalPnl = strategyEntries.reduce((sum, [, d]) => sum + d.pnl, 0);
              const initialCapital = 1000; // Default
              
              return (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left text-xs text-white/50 font-medium py-2 px-2">Strategy</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">P&L</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">% Return</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Contrib %</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Trades</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Win Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {strategyEntries.map(([strategy, data]) => {
                        const isPositive = data.pnl >= 0;
                        const returnPct = (data.pnl / initialCapital) * 100;
                        const contribPct = totalPnl !== 0 ? (data.pnl / totalPnl) * 100 : 0;
                        const winRate = data.trades > 0 ? (data.wins / data.trades) * 100 : 0;
                        return (
                          <tr key={strategy} className="border-b border-white/5 hover:bg-white/5">
                            <td className="py-2 px-2">
                              <span className="text-sm text-white">{strategy.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                            </td>
                            <td className={`text-right py-2 px-2 font-bold text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                              {isPositive ? '+' : ''}${data.pnl.toFixed(2)}
                            </td>
                            <td className={`text-right py-2 px-2 text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                              {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
                            </td>
                            <td className={`text-right py-2 px-2 text-sm ${contribPct >= 0 ? 'text-cyan-400' : 'text-orange-400'}`}>
                              {contribPct.toFixed(1)}%
                            </td>
                            <td className="text-right text-sm text-white/70 py-2 px-2">{data.trades}</td>
                            <td className={`text-right text-sm py-2 px-2 ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                              {winRate.toFixed(1)}%
                            </td>
                          </tr>
                        );
                      })}
                      {/* TOTALS ROW */}
                      {strategyEntries.length > 0 && (
                        <tr className="border-t-2 border-white/20 bg-white/5 font-semibold">
                          <td className="py-2 px-2 text-sm text-white">TOTAL</td>
                          <td className={`text-right py-2 px-2 text-sm ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
                          </td>
                          <td className={`text-right py-2 px-2 text-sm ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {totalPnl >= 0 ? '+' : ''}{((totalPnl / initialCapital) * 100).toFixed(2)}%
                          </td>
                          <td className="text-right py-2 px-2 text-sm text-cyan-400">100%</td>
                          <td className="text-right text-sm text-white py-2 px-2">{trades.length}</td>
                          <td className={`text-right text-sm py-2 px-2 ${(tradeStats?.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                            {((tradeStats?.win_rate || 0) * 100).toFixed(1)}%
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </div>

          {/* Asset Class Performance Table */}
          <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="live-asset-class-performance">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="w-5 h-5 text-purple-400" />
              <h3 className="text-lg font-semibold text-white">Asset Class Performance</h3>
            </div>
            {(() => {
              // Calculate asset class performance from trades
              const assetStats = trades.reduce((acc, t) => {
                const category = t.category || t.asset_class || 'Unknown';
                if (!acc[category]) {
                  acc[category] = { pnl: 0, trades: 0, wins: 0 };
                }
                acc[category].pnl += t.pnl || 0;
                acc[category].trades += 1;
                if ((t.pnl || 0) > 0) acc[category].wins += 1;
                return acc;
              }, {});
              
              const assetEntries = Object.entries(assetStats).sort((a, b) => b[1].pnl - a[1].pnl);
              const totalPnl = assetEntries.reduce((sum, [, d]) => sum + d.pnl, 0);
              const initialCapital = 1000;
              
              return (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="text-left text-xs text-white/50 font-medium py-2 px-2">Asset Class</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">P&L</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">% Return</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Contrib %</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Trades</th>
                        <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Win Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assetEntries.map(([category, data]) => {
                        const isPositive = data.pnl >= 0;
                        const returnPct = (data.pnl / initialCapital) * 100;
                        const contribPct = totalPnl !== 0 ? (data.pnl / totalPnl) * 100 : 0;
                        const winRate = data.trades > 0 ? (data.wins / data.trades) * 100 : 0;
                        return (
                          <tr key={category} className="border-b border-white/5 hover:bg-white/5">
                            <td className="py-2 px-2">
                              <span className="text-sm text-white capitalize">{category}</span>
                            </td>
                            <td className={`text-right py-2 px-2 font-bold text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                              {isPositive ? '+' : ''}${data.pnl.toFixed(2)}
                            </td>
                            <td className={`text-right py-2 px-2 text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                              {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
                            </td>
                            <td className={`text-right py-2 px-2 text-sm ${contribPct >= 0 ? 'text-cyan-400' : 'text-orange-400'}`}>
                              {contribPct.toFixed(1)}%
                            </td>
                            <td className="text-right text-sm text-white/70 py-2 px-2">{data.trades}</td>
                            <td className={`text-right text-sm py-2 px-2 ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                              {winRate.toFixed(1)}%
                            </td>
                          </tr>
                        );
                      })}
                      {/* TOTALS ROW */}
                      {assetEntries.length > 0 && (
                        <tr className="border-t-2 border-white/20 bg-white/5 font-semibold">
                          <td className="py-2 px-2 text-sm text-white">TOTAL</td>
                          <td className={`text-right py-2 px-2 text-sm ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
                          </td>
                          <td className={`text-right py-2 px-2 text-sm ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {totalPnl >= 0 ? '+' : ''}{((totalPnl / initialCapital) * 100).toFixed(2)}%
                          </td>
                          <td className="text-right py-2 px-2 text-sm text-cyan-400">100%</td>
                          <td className="text-right text-sm text-white py-2 px-2">{trades.length}</td>
                          <td className={`text-right text-sm py-2 px-2 ${(tradeStats?.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                            {((tradeStats?.win_rate || 0) * 100).toFixed(1)}%
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Returns Distribution Chart */}
      {trades.length > 0 && (
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="live-returns-distribution">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-cyan-400" />
              <h3 className="text-lg font-semibold text-white">Returns Distribution</h3>
              <div className="group relative">
                <div className="w-4 h-4 rounded-full bg-white/10 flex items-center justify-center cursor-help">
                  <span className="text-xs text-white/50">?</span>
                </div>
                <div className="absolute left-0 bottom-full mb-2 w-64 p-3 bg-slate-900 border border-white/20 rounded-lg text-xs text-white/80 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                  Histogram of individual trade returns. Bell curve centered right of 0 = consistent profits. Skew indicates asymmetry.
                </div>
              </div>
            </div>
            {(() => {
              const returns = trades.map(t => ((t.pnl || 0) / Math.max(Math.abs(t.price * t.shares), 0.01)) * 100);
              const mean = returns.length > 0 ? returns.reduce((a, b) => a + b, 0) / returns.length : 0;
              const sortedReturns = [...returns].sort((a, b) => a - b);
              const median = returns.length > 0 ? sortedReturns[Math.floor(returns.length / 2)] : 0;
              const variance = returns.length > 0 ? returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length : 0;
              const std = Math.sqrt(variance);
              return (
                <div className="flex items-center gap-4 text-xs">
                  <span className="text-white/50">Mean: <span className={mean >= 0 ? 'text-green-400' : 'text-red-400'}>{mean.toFixed(2)}%</span></span>
                  <span className="text-white/50">Median: <span className="text-cyan-400">{median.toFixed(2)}%</span></span>
                  <span className="text-white/50">Std Dev: <span className="text-purple-400">{std.toFixed(2)}%</span></span>
                </div>
              );
            })()}
          </div>
          <ResponsiveContainer width="100%" height={200}>
            {(() => {
              // Calculate returns distribution
              const returns = trades.map(t => ((t.pnl || 0) / Math.max(Math.abs(t.price * t.shares), 0.01)) * 100);
              const minReturn = Math.min(...returns, -10);
              const maxReturn = Math.max(...returns, 10);
              const binCount = 20;
              const binSize = (maxReturn - minReturn) / binCount;
              
              const bins = Array.from({ length: binCount }, (_, i) => {
                const rangeStart = minReturn + i * binSize;
                const rangeEnd = rangeStart + binSize;
                const count = returns.filter(r => r >= rangeStart && r < rangeEnd).length;
                return {
                  range: `${rangeStart.toFixed(1)}%`,
                  count,
                  rangeStart,
                  rangeEnd
                };
              });
              
              return (
                <AreaChart data={bins}>
                  <defs>
                    <linearGradient id="colorReturns" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.1}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="range" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 9 }} interval={3} />
                  <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
                  <Tooltip 
                    contentStyle={{backgroundColor: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', fontSize: '11px'}}
                    formatter={(value, name) => [value, 'Trades']}
                    labelFormatter={(label) => `Return: ${label}`}
                  />
                  <Area type="monotone" dataKey="count" stroke="#06b6d4" fillOpacity={1} fill="url(#colorReturns)" />
                </AreaChart>
              );
            })()}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

// Compact Metric Card
const MetricCard = ({ icon: Icon, label, value, color }) => {
  const colors = {
    cyan: 'text-cyan-400',
    purple: 'text-purple-400',
    orange: 'text-orange-400',
    green: 'text-green-400'
  };
  
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-3 hover:bg-white/10 transition">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-4 h-4 ${colors[color]}`} />
        <span className="text-xs text-white/50 uppercase">{label}</span>
      </div>
      <p className={`text-xl font-bold ${colors[color]}`}>{value}</p>
    </div>
  );
};

// Stat Card Component
const StatCard = ({ title, value, icon: Icon, color }) => {
  const colorClasses = {
    cyan: 'from-cyan-500/20 to-cyan-600/10 border-cyan-500/30',
    blue: 'from-blue-500/20 to-blue-600/10 border-blue-500/30',
    purple: 'from-purple-500/20 to-purple-600/10 border-purple-500/30',
    indigo: 'from-indigo-500/20 to-indigo-600/10 border-indigo-500/30',
    orange: 'from-orange-500/20 to-orange-600/10 border-orange-500/30'
  };
  const iconColors = {
    cyan: 'text-cyan-400',
    blue: 'text-blue-400',
    purple: 'text-purple-400',
    indigo: 'text-indigo-400',
    orange: 'text-orange-400'
  };

  return (
    <div className={`rounded-xl bg-gradient-to-br ${colorClasses[color]} border p-3`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-white/50 mb-0.5">{title}</p>
          <p className="text-xl font-bold text-white">{value}</p>
        </div>
        <Icon className={`w-5 h-5 ${iconColors[color]}`} />
      </div>
    </div>
  );
};

export default Dashboard;
