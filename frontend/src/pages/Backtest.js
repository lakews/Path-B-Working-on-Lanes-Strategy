import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Play, Square, TrendingUp, Activity, DollarSign, Target, Calendar } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Backtest = () => {
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const [config, setConfig] = useState({
    start_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']
  });

  useEffect(() => {
    checkStatus();
    fetchLatestResults();
    const interval = setInterval(() => {
      checkStatus();
      if (backtestRunning) {
        fetchLatestResults();
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
      }
    } catch (e) {
      // No results yet
    }
  };

  const startBacktest = async () => {
    setLoading(true);
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

  return (
    <div className="space-y-6" data-testid="backtest-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Backtesting</h2>
          <p className="text-white/60 text-sm mt-1">Test strategies on historical data</p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 rounded-lg backdrop-blur-sm bg-white/5 border border-white/10">
          <div className={`w-2 h-2 rounded-full ${backtestRunning ? 'bg-orange-400 animate-pulse' : 'bg-gray-400'}`}></div>
          <span className="text-sm text-white/90">{backtestRunning ? 'Running' : 'Idle'}</span>
        </div>
      </div>

      {/* Configuration */}
      <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="backtest-config">
        <h3 className="text-lg font-semibold text-white mb-4">Backtest Configuration</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              <Calendar className="w-4 h-4 inline mr-2" />
              Start Date
            </label>
            <input
              type="date"
              value={config.start_date}
              onChange={(e) => setConfig({...config, start_date: e.target.value})}
              disabled={backtestRunning}
              className="w-full px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:border-cyan-500 transition disabled:opacity-50"
              data-testid="start-date-input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              <Calendar className="w-4 h-4 inline mr-2" />
              End Date
            </label>
            <input
              type="date"
              value={config.end_date}
              onChange={(e) => setConfig({...config, end_date: e.target.value})}
              disabled={backtestRunning}
              className="w-full px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:border-cyan-500 transition disabled:opacity-50"
              data-testid="end-date-input"
            />
          </div>
        </div>

        {/* Strategy Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-white mb-3">Strategies to Test</label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { id: 'delta_neutral', name: 'Delta-Neutral Market Making', desc: 'Capture spreads with minimal risk' },
              { id: 'volatility_exploitation', name: 'Volatility Exploitation', desc: '30-100x on extreme prices' },
              { id: 'alpha_directional', name: 'Alpha-Directional', desc: 'High-confidence directional trades' },
              { id: 'all', name: 'All Strategies Combined', desc: 'Test all strategies together' }
            ].map((strategy) => (
              <button
                key={strategy.id}
                onClick={() => {
                  if (strategy.id === 'all') {
                    // Toggle all
                    if (config.strategies.length === 3) {
                      setConfig({...config, strategies: []});
                    } else {
                      setConfig({...config, strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional']});
                    }
                  } else {
                    toggleStrategy(strategy.id);
                  }
                }}
                disabled={backtestRunning}
                data-testid={`strategy-${strategy.id}-toggle`}
                className={`p-4 rounded-lg font-medium transition disabled:opacity-50 text-left border-2 ${
                  (strategy.id === 'all' && config.strategies.length === 3) || 
                  (strategy.id !== 'all' && config.strategies.includes(strategy.id))
                    ? 'bg-cyan-500/20 border-cyan-500 text-white'
                    : 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10 hover:border-white/20'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="font-semibold text-base mb-1">{strategy.name}</div>
                    <div className="text-xs text-white/60">{strategy.desc}</div>
                  </div>
                  <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                    (strategy.id === 'all' && config.strategies.length === 3) || 
                    (strategy.id !== 'all' && config.strategies.includes(strategy.id))
                      ? 'border-cyan-500 bg-cyan-500'
                      : 'border-white/30'
                  }`}>
                    {((strategy.id === 'all' && config.strategies.length === 3) || 
                      (strategy.id !== 'all' && config.strategies.includes(strategy.id))) && (
                      <span className="text-white text-xs">✓</span>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
          <p className="text-xs text-white/60 mt-2">
            {config.strategies.length} strateg{config.strategies.length === 1 ? 'y' : 'ies'} selected
          </p>
        </div>

        {/* Control Button */}
        <button
          onClick={backtestRunning ? stopBacktest : startBacktest}
          disabled={loading || config.strategies.length === 0}
          data-testid="backtest-control-button"
          className={`w-full px-6 py-3 rounded-lg font-semibold transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed ${
            backtestRunning
              ? 'bg-red-500 hover:bg-red-600 text-white'
              : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white'
          }`}
        >
          {backtestRunning ? (
            <><Square className="w-5 h-5" /> Stop Backtest</>
          ) : (
            <><Play className="w-5 h-5" /> {loading ? 'Starting...' : 'Start Backtest'}</>
          )}
        </button>
      </div>

      {/* Results */}
      {results && (
        <>
          {/* Metrics Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="backtest-return-card">
              <div className="flex items-center gap-3 mb-2">
                <DollarSign className="w-8 h-8 text-green-400" />
                <h3 className="text-sm text-white/60">Total Return</h3>
              </div>
              <p className={`text-3xl font-bold ${results.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {results.total_return_pct >= 0 ? '+' : ''}{results.total_return_pct?.toFixed(2)}%
              </p>
              <p className="text-xs text-white/60 mt-1">
                ${results.total_pnl?.toFixed(2)} P&L
              </p>
            </div>

            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="backtest-winrate-card">
              <div className="flex items-center gap-3 mb-2">
                <Target className="w-8 h-8 text-cyan-400" />
                <h3 className="text-sm text-white/60">Win Rate</h3>
              </div>
              <p className="text-3xl font-bold text-white">
                {((results.win_rate || 0) * 100).toFixed(1)}%
              </p>
              <p className="text-xs text-cyan-400 mt-1">
                {results.winning_trades}W / {results.losing_trades}L
              </p>
            </div>

            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="backtest-sharpe-card">
              <div className="flex items-center gap-3 mb-2">
                <TrendingUp className="w-8 h-8 text-purple-400" />
                <h3 className="text-sm text-white/60">Sharpe Ratio</h3>
              </div>
              <p className="text-3xl font-bold text-white">
                {results.sharpe_ratio?.toFixed(2)}
              </p>
              <p className="text-xs text-purple-400 mt-1">Risk-adjusted</p>
            </div>

            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="backtest-drawdown-card">
              <div className="flex items-center gap-3 mb-2">
                <Activity className="w-8 h-8 text-orange-400" />
                <h3 className="text-sm text-white/60">Max Drawdown</h3>
              </div>
              <p className="text-3xl font-bold text-red-400">
                {((results.max_drawdown || 0) * 100).toFixed(2)}%
              </p>
              <p className="text-xs text-orange-400 mt-1">{results.total_trades} trades</p>
            </div>
          </div>

          {/* Equity Curve */}
          <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="equity-curve">
            <h3 className="text-lg font-semibold text-white mb-4">Equity Curve</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={results.equity_curve || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="timestamp" stroke="rgba(255,255,255,0.5)" hide />
                <YAxis stroke="rgba(255,255,255,0.5)" />
                <Tooltip 
                  contentStyle={{backgroundColor: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px'}}
                />
                <Line type="monotone" dataKey="equity" stroke="#06b6d4" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {!results && !backtestRunning && (
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-16 text-center">
          <Activity className="w-16 h-16 text-white/20 mx-auto mb-4" />
          <p className="text-white/60 text-lg">No backtest results yet</p>
          <p className="text-white/40 text-sm mt-2">Configure and start a backtest to see results</p>
        </div>
      )}
    </div>
  );
};

export default Backtest;