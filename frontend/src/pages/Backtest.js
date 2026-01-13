import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { 
  Play, Square, TrendingUp, TrendingDown, Activity, DollarSign, Target, Calendar,
  BarChart3, Clock, Zap, Shield, Award, Percent, ChevronRight, Database,
  RefreshCw, AlertTriangle, CheckCircle, XCircle
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar, Cell } from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STRATEGY_INFO = {
  delta_neutral: { 
    name: 'Delta-Neutral Market Making', 
    desc: 'Capture spreads with minimal directional risk',
    color: '#06b6d4',
    risk: 'Low'
  },
  volatility_exploitation: { 
    name: 'Volatility Exploitation', 
    desc: 'Profit from extreme price movements (30-100x)',
    color: '#8b5cf6',
    risk: 'Medium'
  },
  alpha_directional: { 
    name: 'Alpha-Directional', 
    desc: 'High-confidence directional bets with AI signals',
    color: '#f59e0b',
    risk: 'Medium-High'
  },
  arbitrage: { 
    name: 'Multi-Market Arbitrage', 
    desc: 'Cross-market price inefficiency exploitation',
    color: '#10b981',
    risk: 'Low'
  }
};

const Backtest = () => {
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [historicalStats, setHistoricalStats] = useState(null);
  const [progress, setProgress] = useState(0);
  
  const [config, setConfig] = useState({
    start_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage'],
    initial_capital: 1000,
    kelly_fraction: 0.25
  });

  useEffect(() => {
    checkStatus();
    fetchLatestResults();
    fetchHistoricalStats();
    const interval = setInterval(() => {
      checkStatus();
      if (backtestRunning) {
        fetchLatestResults();
        setProgress(prev => Math.min(prev + 5, 95));
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [backtestRunning]);

  const checkStatus = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setBacktestRunning(response.data.trading_mode === 'backtest');
    } catch (e) {
      console.error('Error checking status:', e);
    }
  };

  const fetchLatestResults = async () => {
    try {
      const response = await axios.get(`${API}/backtest/results`);
      if (response.data && !response.data.message) {
        setResults(response.data);
        setProgress(100);
      }
    } catch (e) {
      // No results yet
    }
  };

  const fetchHistoricalStats = async () => {
    try {
      const response = await axios.get(`${API}/historical/stats`);
      setHistoricalStats(response.data);
    } catch (e) {
      console.error('Error fetching historical stats:', e);
    }
  };

  const startBacktest = async () => {
    setLoading(true);
    setProgress(0);
    try {
      const response = await axios.post(`${API}/backtest/start`, null, {
        params: {
          start_date: `${config.start_date}T00:00:00Z`,
          end_date: `${config.end_date}T23:59:59Z`,
          strategies: config.strategies
        }
      });
      toast.success('Backtest started');
      setBacktestRunning(true);
      setResults(null);
    } catch (e) {
      toast.error(e.response?.data?.message || 'Failed to start backtest');
    } finally {
      setLoading(false);
    }
  };

  const stopBacktest = async () => {
    try {
      await axios.post(`${API}/backtest/stop`);
      toast.warning('Backtest stopped');
      setBacktestRunning(false);
      await fetchLatestResults();
    } catch (e) {
      toast.error('Failed to stop backtest');
    }
  };

  const toggleStrategy = (strategy) => {
    if (config.strategies.includes(strategy)) {
      setConfig({
        ...config,
        strategies: config.strategies.filter(s => s !== strategy)
      });
    } else {
      setConfig({
        ...config,
        strategies: [...config.strategies, strategy]
      });
    }
  };

  // Calculate date range duration
  const dateDiff = Math.ceil((new Date(config.end_date) - new Date(config.start_date)) / (1000 * 60 * 60 * 24));

  return (
    <div className="space-y-6" data-testid="backtest-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Strategy Backtesting</h1>
          <p className="text-white/60 text-sm mt-1">Test and validate trading strategies on historical data</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Data Status */}
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500/30">
            <Database className="w-4 h-4 text-blue-400" />
            <span className="text-sm text-blue-400">
              {historicalStats?.total_snapshots?.toLocaleString() || 0} snapshots
            </span>
          </div>
          {/* Running Status */}
          <div className={`flex items-center gap-2 px-4 py-2 rounded-lg backdrop-blur-sm border ${
            backtestRunning 
              ? 'bg-orange-500/20 border-orange-500/30' 
              : 'bg-white/5 border-white/10'
          }`}>
            <div className={`w-2 h-2 rounded-full ${backtestRunning ? 'bg-orange-400 animate-pulse' : 'bg-gray-400'}`}></div>
            <span className={`text-sm ${backtestRunning ? 'text-orange-400' : 'text-white/60'}`}>
              {backtestRunning ? 'Running' : 'Ready'}
            </span>
          </div>
        </div>
      </div>

      {/* Progress Bar (when running) */}
      {backtestRunning && (
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-white/60">Backtest Progress</span>
            <span className="text-sm text-cyan-400">{progress}%</span>
          </div>
          <div className="h-2 bg-white/10 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Configuration Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Date Range & Capital */}
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="backtest-config">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-cyan-400" />
            Test Parameters
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-white/60 mb-1">Start Date</label>
              <input
                type="date"
                value={config.start_date}
                onChange={(e) => setConfig({...config, start_date: e.target.value})}
                disabled={backtestRunning}
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm focus:outline-none focus:border-cyan-500 transition disabled:opacity-50"
                data-testid="start-date-input"
              />
            </div>
            <div>
              <label className="block text-xs text-white/60 mb-1">End Date</label>
              <input
                type="date"
                value={config.end_date}
                onChange={(e) => setConfig({...config, end_date: e.target.value})}
                disabled={backtestRunning}
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm focus:outline-none focus:border-cyan-500 transition disabled:opacity-50"
                data-testid="end-date-input"
              />
            </div>
            
            <div className="pt-3 border-t border-white/10">
              <div className="flex justify-between text-sm">
                <span className="text-white/60">Duration</span>
                <span className="text-white font-medium">{dateDiff} days</span>
              </div>
            </div>

            <div>
              <label className="block text-xs text-white/60 mb-1">Initial Capital ($)</label>
              <input
                type="number"
                value={config.initial_capital}
                onChange={(e) => setConfig({...config, initial_capital: parseFloat(e.target.value) || 1000})}
                disabled={backtestRunning}
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm focus:outline-none focus:border-cyan-500 transition disabled:opacity-50"
                min="100"
              />
            </div>

            <div>
              <label className="block text-xs text-white/60 mb-1">Kelly Fraction</label>
              <select
                value={config.kelly_fraction}
                onChange={(e) => setConfig({...config, kelly_fraction: parseFloat(e.target.value)})}
                disabled={backtestRunning}
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm focus:outline-none focus:border-cyan-500"
              >
                <option value={0.1}>10% (Very Conservative)</option>
                <option value={0.15}>15% (Conservative)</option>
                <option value={0.25}>25% (Moderate)</option>
                <option value={0.35}>35% (Aggressive)</option>
                <option value={0.5}>50% (Full Kelly)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Strategy Selection */}
        <div className="lg:col-span-2 rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-400" />
            Select Strategies
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(STRATEGY_INFO).map(([id, info]) => (
              <button
                key={id}
                onClick={() => toggleStrategy(id)}
                disabled={backtestRunning}
                data-testid={`strategy-${id}-toggle`}
                className={`p-4 rounded-xl font-medium transition-all disabled:opacity-50 text-left border-2 ${
                  config.strategies.includes(id)
                    ? 'border-cyan-500 bg-cyan-500/10'
                    : 'border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20'
                }`}
              >
                <div className="flex items-start gap-3">
                  <div 
                    className="w-3 h-3 rounded-full mt-1 flex-shrink-0"
                    style={{ backgroundColor: info.color }}
                  />
                  <div className="flex-1">
                    <div className="font-semibold text-white text-sm mb-1">{info.name}</div>
                    <div className="text-xs text-white/50 mb-2">{info.desc}</div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        info.risk === 'Low' ? 'bg-green-500/20 text-green-400' :
                        info.risk === 'Medium' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-orange-500/20 text-orange-400'
                      }`}>
                        {info.risk} Risk
                      </span>
                    </div>
                  </div>
                  <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                    config.strategies.includes(id) ? 'border-cyan-500 bg-cyan-500' : 'border-white/30'
                  }`}>
                    {config.strategies.includes(id) && <CheckCircle className="w-3 h-3 text-white" />}
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm text-white/60">
              {config.strategies.length} of 4 strategies selected
            </p>
            <button
              onClick={() => {
                if (config.strategies.length === 4) {
                  setConfig({...config, strategies: []});
                } else {
                  setConfig({...config, strategies: Object.keys(STRATEGY_INFO)});
                }
              }}
              disabled={backtestRunning}
              className="text-sm text-cyan-400 hover:text-cyan-300 transition"
            >
              {config.strategies.length === 4 ? 'Deselect All' : 'Select All'}
            </button>
          </div>
        </div>
      </div>

      {/* Start/Stop Button */}
      <button
        onClick={backtestRunning ? stopBacktest : startBacktest}
        disabled={loading || config.strategies.length === 0}
        data-testid="backtest-control-button"
        className={`w-full px-6 py-4 rounded-xl font-semibold transition-all flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed ${
          backtestRunning
            ? 'bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white'
            : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white'
        }`}
      >
        {backtestRunning ? (
          <><Square className="w-5 h-5" /> Stop Backtest</>
        ) : (
          <><Play className="w-5 h-5" /> {loading ? 'Starting...' : 'Run Backtest'}</>
        )}
      </button>

      {/* Results Section */}
      {results && (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <MetricCard
              icon={DollarSign}
              label="Total Return"
              value={`${results.total_return_pct >= 0 ? '+' : ''}${results.total_return_pct?.toFixed(2)}%`}
              subValue={`$${results.total_pnl?.toFixed(2)}`}
              color={results.total_pnl >= 0 ? 'green' : 'red'}
            />
            <MetricCard
              icon={Target}
              label="Win Rate"
              value={`${((results.win_rate || 0) * 100).toFixed(1)}%`}
              subValue={`${results.winning_trades}W / ${results.losing_trades}L`}
              color="cyan"
            />
            <MetricCard
              icon={TrendingUp}
              label="Sharpe Ratio"
              value={results.sharpe_ratio?.toFixed(2) || '0.00'}
              subValue="Risk-adjusted"
              color="purple"
            />
            <MetricCard
              icon={AlertTriangle}
              label="Max Drawdown"
              value={`${((results.max_drawdown || 0) * 100).toFixed(2)}%`}
              subValue="Peak to trough"
              color="orange"
            />
            <MetricCard
              icon={Activity}
              label="Total Trades"
              value={results.total_trades || 0}
              subValue={`${dateDiff} days`}
              color="blue"
            />
            <MetricCard
              icon={Award}
              label="Profit Factor"
              value={results.profit_factor?.toFixed(2) || '0.00'}
              subValue={results.profit_factor > 1.5 ? 'Excellent' : 'Target: >1.5'}
              color={results.profit_factor > 1.5 ? 'green' : 'yellow'}
            />
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Equity Curve */}
            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="equity-curve">
              <h3 className="text-lg font-semibold text-white mb-4">Equity Curve</h3>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={results.equity_curve || []}>
                  <defs>
                    <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4}/>
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="timestamp" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
                  <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
                  <Tooltip 
                    contentStyle={{backgroundColor: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px'}}
                  />
                  <Area type="monotone" dataKey="equity" stroke="#06b6d4" strokeWidth={2} fill="url(#equityGradient)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Strategy Breakdown */}
            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Strategy Performance</h3>
              {results.strategy_results ? (
                <div className="space-y-3">
                  {Object.entries(results.strategy_results || {}).map(([strategy, data]) => {
                    const info = STRATEGY_INFO[strategy] || { name: strategy, color: '#666' };
                    return (
                      <div key={strategy} className="p-3 rounded-lg bg-white/5">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: info.color }} />
                            <span className="text-sm text-white">{info.name}</span>
                          </div>
                          <span className={`text-sm font-bold ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {data.pnl >= 0 ? '+' : ''}${data.pnl?.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-white/60">
                          <span>{data.trades} trades</span>
                          <span>{((data.win_rate || 0) * 100).toFixed(1)}% win rate</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="h-64 flex items-center justify-center text-white/40">
                  No strategy breakdown available
                </div>
              )}
            </div>
          </div>

          {/* Summary Card */}
          <div className={`rounded-xl border p-6 ${
            results.total_pnl >= 0 
              ? 'bg-gradient-to-r from-green-500/10 to-emerald-500/10 border-green-500/30'
              : 'bg-gradient-to-r from-red-500/10 to-rose-500/10 border-red-500/30'
          }`}>
            <div className="flex items-center gap-3 mb-3">
              {results.total_pnl >= 0 ? (
                <CheckCircle className="w-6 h-6 text-green-400" />
              ) : (
                <XCircle className="w-6 h-6 text-red-400" />
              )}
              <h3 className="text-lg font-semibold text-white">
                Backtest {results.total_pnl >= 0 ? 'Profitable' : 'Unprofitable'}
              </h3>
            </div>
            <p className="text-sm text-white/70">
              Over {dateDiff} days with ${config.initial_capital} initial capital, the selected strategies 
              {results.total_pnl >= 0 ? ' generated' : ' lost'} <strong className={results.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                ${Math.abs(results.total_pnl || 0).toFixed(2)}
              </strong> ({results.total_return_pct >= 0 ? '+' : ''}{results.total_return_pct?.toFixed(2)}%) 
              with a Sharpe ratio of {results.sharpe_ratio?.toFixed(2)}.
            </p>
          </div>
        </>
      )}

      {/* No Results State */}
      {!results && !backtestRunning && (
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-12 text-center">
          <BarChart3 className="w-16 h-16 text-white/20 mx-auto mb-4" />
          <p className="text-white/60 text-lg">No backtest results yet</p>
          <p className="text-white/40 text-sm mt-2">Configure your parameters and run a backtest to see performance metrics</p>
        </div>
      )}
    </div>
  );
};

// Metric Card Component
const MetricCard = ({ icon: Icon, label, value, subValue, color }) => {
  const colorMap = {
    green: 'text-green-400',
    red: 'text-red-400',
    cyan: 'text-cyan-400',
    purple: 'text-purple-400',
    orange: 'text-orange-400',
    blue: 'text-blue-400',
    yellow: 'text-yellow-400'
  };

  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${colorMap[color]}`} />
        <span className="text-xs text-white/60 uppercase">{label}</span>
      </div>
      <p className={`text-xl font-bold ${colorMap[color]}`}>{value}</p>
      {subValue && <p className="text-xs text-white/40 mt-1">{subValue}</p>}
    </div>
  );
};

export default Backtest;
