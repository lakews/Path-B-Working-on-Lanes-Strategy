import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { 
  Play, Square, TrendingUp, TrendingDown, Activity, DollarSign, Target, Calendar,
  BarChart3, Clock, Zap, Shield, Award, Percent, ChevronRight, Database,
  RefreshCw, AlertTriangle, CheckCircle, XCircle, History, GitCompare, Trash2,
  BookOpen, Lightbulb, ChevronDown, ChevronUp, Eye, FileBarChart, Brain, Download, X, Layers
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar, Cell, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend, ComposedChart, ReferenceLine } from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Data Source Options
const DATA_SOURCE_OPTIONS = [
  { id: 'auto', name: 'Auto (Best Available)', desc: 'Automatically selects best data', icon: '🔄' },
  { id: 'real', name: 'Real Price History', desc: 'Most accurate, tick-level data', icon: '📈' },
  { id: 'snapshots', name: 'Historical Snapshots', desc: 'Faster, periodic snapshots', icon: '📸' },
  { id: 'hybrid', name: 'Hybrid Mode', desc: 'Combines real prices + snapshots', icon: '🔀' }
];

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

// Tooltip explanations for metrics
const METRIC_TOOLTIPS = {
  sentiment_signals: "Number of markets analyzed for social media and news sentiment. Higher values indicate broader market coverage.",
  whale_signals: "Number of markets checked for large trader (whale) activity. Whales can move markets significantly.",
  avg_sentiment: "Average sentiment score across all analyzed markets. >50% indicates bullish bias, <50% bearish.",
  avg_whale_activity: "Average whale activity level. Higher % means more large traders are active.",
  bullish_whales: "Markets where whales are predominantly buying (bullish positioning).",
  bearish_whales: "Markets where whales are predominantly selling (bearish positioning).",
  training_iterations: "Total number of learning cycles the RL model has completed.",
  exploration_rate: "Probability of exploring new strategies vs exploiting known good ones. Lower = more exploitation.",
  avg_reward: "Average reward signal from recent trades. Positive indicates profitable learning.",
  experience_buffer: "Number of past experiences stored for learning. More data = better learning.",
  q_table_usage: "Percentage of Q-table cells with learned values. Higher = more market conditions explored.",
  action_distribution: "How the RL model distributes decisions across different action types.",
  real_data_pct: "Percentage of data from real tick-level prices vs simulated data.",
  sharpe_ratio: "Risk-adjusted return. Measures excess return per unit of risk. >1 is good, >2 is excellent.",
  profit_factor: "Gross profits divided by gross losses. >1.5 indicates strong profitability.",
  max_drawdown: "Largest peak-to-trough decline. Lower is better for risk management.",
  win_rate: "Percentage of trades that were profitable."
};

// Tooltip Component
const InfoTooltip = ({ text, children }) => (
  <div className="relative group inline-flex items-center">
    {children}
    <div className="ml-1 cursor-help">
      <svg className="w-3.5 h-3.5 text-white/30 hover:text-white/60 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    </div>
    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-slate-900 border border-white/20 rounded-lg text-xs text-white/80 w-64 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 shadow-xl">
      {text}
      <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900"></div>
    </div>
  </div>
);

const Backtest = () => {
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [historicalStats, setHistoricalStats] = useState(null);
  const [priceHistoryStats, setPriceHistoryStats] = useState(null);
  const [collectingPrices, setCollectingPrices] = useState(false);
  const [progress, setProgress] = useState(0);
  
  // History & Comparison State
  const [history, setHistory] = useState([]);
  const [selectedBacktests, setSelectedBacktests] = useState([]);
  const [comparisonData, setComparisonData] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const [showEducation, setShowEducation] = useState(false);
  const [activeTab, setActiveTab] = useState('results'); // 'results', 'history', 'compare', 'learn'
  
  // Deep-dive modal state
  const [deepDiveBacktest, setDeepDiveBacktest] = useState(null);
  const [deepDiveLoading, setDeepDiveLoading] = useState(false);
  
  const [config, setConfig] = useState({
    start_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage'],
    initial_capital: 1000,
    kelly_fraction: 0.25,
    data_source: 'auto'
  });

  useEffect(() => {
    checkStatus();
    fetchLatestResults();
    fetchHistoricalStats();
    fetchPriceHistoryStats();
    fetchBacktestHistory();
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
      
      // Load user's configured strategies and asset classes
      const serverConfig = response.data.configuration || {};
      if (serverConfig.enabled_strategies && serverConfig.enabled_strategies.length > 0) {
        setConfig(prev => ({
          ...prev,
          strategies: serverConfig.enabled_strategies
        }));
      }
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

  const fetchPriceHistoryStats = async () => {
    try {
      const response = await axios.get(`${API}/historical/price-stats`);
      setPriceHistoryStats(response.data);
    } catch (e) {
      console.error('Error fetching price history stats:', e);
    }
  };

  const collectPriceHistory = async () => {
    setCollectingPrices(true);
    try {
      const response = await axios.post(`${API}/historical/collect-prices?market_limit=100&interval=1w&fidelity=60`);
      toast.success(`Collected ${response.data.stats?.stored_snapshots || 0} price points from ${response.data.stats?.markets_with_history || 0} markets`);
      await fetchPriceHistoryStats();
      await fetchHistoricalStats();
    } catch (e) {
      toast.error('Failed to collect price history');
    } finally {
      setCollectingPrices(false);
    }
  };

  const fetchBacktestHistory = async () => {
    try {
      const response = await axios.get(`${API}/backtest/history?limit=10`);
      if (response.data && response.data.history) {
        setHistory(response.data.history);
      }
    } catch (e) {
      console.error('Error fetching backtest history:', e);
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
          strategies: config.strategies,
          data_source: config.data_source
        }
      });
      toast.success(`Backtest started (${config.data_source} mode)`);
      setBacktestRunning(true);
      setResults(null);
    } catch (e) {
      toast.error(e.response?.data?.message || 'Failed to start backtest');
    } finally {
      setLoading(false);
    }
  };

  // Deep dive into a specific backtest
  const openDeepDive = async (backtestId) => {
    setDeepDiveLoading(true);
    try {
      const response = await axios.get(`${API}/backtest/results?backtest_id=${backtestId}`);
      if (response.data && !response.data.message) {
        setDeepDiveBacktest(response.data);
      }
    } catch (e) {
      toast.error('Failed to load backtest details');
    } finally {
      setDeepDiveLoading(false);
    }
  };

  const closeDeepDive = () => {
    setDeepDiveBacktest(null);
  };

  const stopBacktest = async () => {
    try {
      await axios.post(`${API}/backtest/stop`);
      toast.warning('Backtest stopped');
      setBacktestRunning(false);
      await fetchLatestResults();
      await fetchBacktestHistory();
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

  const toggleBacktestSelection = (backtestId) => {
    if (selectedBacktests.includes(backtestId)) {
      setSelectedBacktests(selectedBacktests.filter(id => id !== backtestId));
    } else {
      setSelectedBacktests([...selectedBacktests, backtestId]);
    }
  };

  const compareSelectedBacktests = async () => {
    if (selectedBacktests.length === 0) {
      toast.error('Select at least 1 backtest to analyze');
      return;
    }
    
    try {
      const response = await axios.post(`${API}/backtest/compare`, selectedBacktests);
      setComparisonData(response.data);
      setActiveTab('compare');
      toast.success(`Analyzing ${selectedBacktests.length} backtest(s)`);
    } catch (e) {
      toast.error('Failed to compare backtests');
    }
  };

  const deleteBacktest = async (backtestId) => {
    if (!window.confirm('Delete this backtest result?')) return;
    
    try {
      await axios.delete(`${API}/backtest/${backtestId}`);
      toast.success('Backtest deleted');
      fetchBacktestHistory();
      setSelectedBacktests(selectedBacktests.filter(id => id !== backtestId));
    } catch (e) {
      toast.error('Failed to delete backtest');
    }
  };

  const viewBacktestResult = async (backtestId) => {
    try {
      const response = await axios.get(`${API}/backtest/results?backtest_id=${backtestId}`);
      if (response.data && !response.data.message) {
        setResults(response.data);
        setActiveTab('results');
        toast.success('Loaded backtest result');
      }
    } catch (e) {
      toast.error('Failed to load backtest');
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
          <p className="text-white/60 text-sm mt-1">Test, compare, and learn from your trading strategies</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500/30">
            <Database className="w-4 h-4 text-blue-400" />
            <span className="text-sm text-blue-400">
              {historicalStats?.total_snapshots?.toLocaleString() || 0} snapshots
            </span>
          </div>
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

      {/* Tab Navigation */}
      <div className="flex gap-2 p-1 rounded-xl bg-white/5 border border-white/10">
        {[
          { id: 'results', label: 'Results', icon: FileBarChart },
          { id: 'history', label: `History (${history.length})`, icon: History },
          { id: 'compare', label: 'Compare & Analyze', icon: GitCompare },
          { id: 'learn', label: 'Learn', icon: BookOpen }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            data-testid={`tab-${tab.id}`}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-gradient-to-r from-cyan-500/20 to-blue-500/20 text-cyan-400 border border-cyan-500/30'
                : 'text-white/60 hover:text-white hover:bg-white/5'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            <span className="text-sm">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Historical Data Summary with Data Source Selector */}
      {historicalStats && (
        <div className="rounded-xl bg-gradient-to-r from-blue-500/10 to-cyan-500/10 border border-blue-500/20 p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-xs text-blue-400/80 uppercase">Data Range</p>
                <p className="text-sm text-white font-medium">
                  {historicalStats.oldest_snapshot ? new Date(historicalStats.oldest_snapshot).toLocaleDateString() : 'N/A'} - {historicalStats.newest_snapshot ? new Date(historicalStats.newest_snapshot).toLocaleDateString() : 'N/A'}
                </p>
              </div>
              <div className="w-px h-8 bg-white/10" />
              <div>
                <p className="text-xs text-blue-400/80 uppercase">Unique Markets</p>
                <p className="text-sm text-white font-medium">{historicalStats.unique_markets || 0}</p>
              </div>
              <div className="w-px h-8 bg-white/10" />
              <div>
                <p className="text-xs text-blue-400/80 uppercase">Real Price Data</p>
                <p className="text-sm text-white font-medium">
                  {priceHistoryStats?.real_price_snapshots?.toLocaleString() || 0} pts
                  <span className={`ml-2 text-xs ${priceHistoryStats?.real_price_percentage > 50 ? 'text-green-400' : 'text-yellow-400'}`}>
                    ({priceHistoryStats?.real_price_percentage || 0}%)
                  </span>
                </p>
              </div>
              <div className="w-px h-8 bg-white/10" />
              <div>
                <p className="text-xs text-blue-400/80 uppercase">Categories</p>
                <div className="flex gap-2 mt-1">
                  {historicalStats.category_distribution && Object.entries(historicalStats.category_distribution).slice(0,4).map(([cat, count]) => (
                    <span key={cat} className="text-xs px-2 py-0.5 rounded bg-white/10 text-white/70">
                      {cat}: {count}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {/* Data Source Selector - Moved here */}
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-blue-400" />
                <select
                  value={config.data_source}
                  onChange={(e) => setConfig({...config, data_source: e.target.value})}
                  disabled={backtestRunning}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 border border-blue-500/30 text-white text-xs font-medium focus:outline-none focus:border-cyan-500"
                  data-testid="data-source-select-header"
                  style={{ colorScheme: 'dark' }}
                >
                  {DATA_SOURCE_OPTIONS.map(opt => (
                    <option key={opt.id} value={opt.id} className="bg-slate-800 text-white">{opt.icon} {opt.name}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={collectPriceHistory}
                disabled={collectingPrices}
                className="px-3 py-1.5 rounded-lg bg-cyan-500/20 border border-cyan-500/30 text-cyan-400 text-xs font-medium hover:bg-cyan-500/30 transition disabled:opacity-50 flex items-center gap-2"
                data-testid="collect-prices-btn"
              >
                <Download className={`w-3 h-3 ${collectingPrices ? 'animate-spin' : ''}`} />
                {collectingPrices ? 'Collecting...' : 'Fetch Real Prices'}
              </button>
              <div className="text-xs text-blue-400">
                {historicalStats.collector_running ? '● Collecting' : '○ Idle'}
              </div>
            </div>
          </div>
        </div>
      )}

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

      {/* RESULTS TAB */}
      {activeTab === 'results' && (
        <>
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
                    className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-white/10 text-white text-sm focus:outline-none focus:border-cyan-500"
                    style={{ colorScheme: 'dark' }}
                  >
                    <option value={0.1} className="bg-slate-800 text-white">10% (Very Conservative)</option>
                    <option value={0.15} className="bg-slate-800 text-white">15% (Conservative)</option>
                    <option value={0.25} className="bg-slate-800 text-white">25% (Moderate)</option>
                    <option value={0.35} className="bg-slate-800 text-white">35% (Aggressive)</option>
                    <option value={0.5} className="bg-slate-800 text-white">50% (Full Kelly)</option>
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
                      <div className={`w-6 h-6 rounded-md border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                        config.strategies.includes(id) 
                          ? 'border-cyan-500 bg-cyan-500 shadow-lg shadow-cyan-500/30' 
                          : 'border-white/30 hover:border-white/50'
                      }`}>
                        {config.strategies.includes(id) && (
                          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
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
              {/* Data Summary Bar at Top */}
              <div className="rounded-xl bg-gradient-to-r from-slate-800/50 to-slate-700/50 border border-white/10 p-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-6">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-cyan-400" />
                      <span className="text-sm text-white/70">Data Sources:</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="px-3 py-1.5 rounded-lg bg-green-500/10 border border-green-500/20">
                        <span className="text-xs text-green-400 font-medium">
                          {results.data_quality?.real_price_data_points?.toLocaleString() || 0} Real Prices
                        </span>
                      </div>
                      <div className="px-3 py-1.5 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                        <span className="text-xs text-yellow-400 font-medium">
                          {results.data_quality?.simulated_price_data_points?.toLocaleString() || 0} Simulated
                        </span>
                      </div>
                      <div className="px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20">
                        <span className="text-xs text-blue-400 font-medium">
                          {results.data_summary?.total_snapshots?.toLocaleString() || 0} Snapshots
                        </span>
                      </div>
                      <div className="px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/20">
                        <span className="text-xs text-purple-400 font-medium">
                          {results.data_summary?.unique_markets || 0} Markets
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                      results.data_quality?.real_data_percentage > 50 
                        ? 'bg-green-500/20 text-green-400' 
                        : 'bg-yellow-500/20 text-yellow-400'
                    }`}>
                      {results.data_quality?.real_data_percentage || 0}% Real Data
                    </span>
                    <span className="px-3 py-1.5 rounded-lg bg-white/10 text-xs text-white/60">
                      Mode: {results.data_quality?.data_source_mode || 'auto'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Key Metrics with Tooltips */}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <DollarSign className={`w-4 h-4 ${results.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`} />
                    <span className="text-xs text-white/50">Total Return</span>
                  </div>
                  <p className={`text-2xl font-bold ${results.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {results.total_return_pct >= 0 ? '+' : ''}{results.total_return_pct?.toFixed(2)}%
                  </p>
                  <p className="text-xs text-white/40">${results.total_pnl?.toFixed(2)}</p>
                </div>
                
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <InfoTooltip text={METRIC_TOOLTIPS.win_rate}>
                    <div className="flex items-center gap-2 mb-2">
                      <Target className="w-4 h-4 text-cyan-400" />
                      <span className="text-xs text-white/50">Win Rate</span>
                    </div>
                  </InfoTooltip>
                  <p className="text-2xl font-bold text-cyan-400">{((results.win_rate || 0) * 100).toFixed(1)}%</p>
                  <p className="text-xs text-white/40">{results.winning_trades}W / {results.losing_trades}L</p>
                </div>
                
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <InfoTooltip text={METRIC_TOOLTIPS.sharpe_ratio}>
                    <div className="flex items-center gap-2 mb-2">
                      <TrendingUp className="w-4 h-4 text-purple-400" />
                      <span className="text-xs text-white/50">Sharpe Ratio</span>
                    </div>
                  </InfoTooltip>
                  <p className="text-2xl font-bold text-purple-400">{results.sharpe_ratio?.toFixed(2) || '0.00'}</p>
                  <p className="text-xs text-white/40">Risk-adjusted return</p>
                </div>
                
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <InfoTooltip text={METRIC_TOOLTIPS.max_drawdown}>
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="w-4 h-4 text-orange-400" />
                      <span className="text-xs text-white/50">Max Drawdown</span>
                    </div>
                  </InfoTooltip>
                  <p className="text-2xl font-bold text-orange-400">-{((results.max_drawdown || 0) * 100).toFixed(2)}%</p>
                  <p className="text-xs text-white/40">Peak to trough</p>
                </div>
                
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-4 h-4 text-blue-400" />
                    <span className="text-xs text-white/50">Total Trades</span>
                  </div>
                  <p className="text-2xl font-bold text-blue-400">{results.total_trades || 0}</p>
                  <p className="text-xs text-white/40">{dateDiff} days</p>
                </div>
                
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <InfoTooltip text={METRIC_TOOLTIPS.profit_factor}>
                    <div className="flex items-center gap-2 mb-2">
                      <Award className={`w-4 h-4 ${results.profit_factor > 1.5 ? 'text-green-400' : 'text-yellow-400'}`} />
                      <span className="text-xs text-white/50">Profit Factor</span>
                    </div>
                  </InfoTooltip>
                  <p className={`text-2xl font-bold ${results.profit_factor > 1.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                    {results.profit_factor?.toFixed(2) || '0.00'}
                  </p>
                  <p className="text-xs text-white/40">{results.profit_factor > 1.5 ? 'Excellent' : 'Target: >1.5'}</p>
                </div>
              </div>

              {/* Strategy & Asset Class Tables Side by Side */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {/* Strategy Performance Table */}
                <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Zap className="w-5 h-5 text-yellow-400" />
                    Strategy Performance
                  </h3>
                  {results.strategy_results && Object.keys(results.strategy_results).length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-white/10">
                            <th className="text-left text-xs text-white/50 font-medium py-2 px-2">Strategy</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">P&L</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Trades</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Win Rate</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">PF</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(results.strategy_results || {}).map(([strategy, data]) => {
                            const info = STRATEGY_INFO[strategy] || { name: strategy, color: '#666' };
                            const isPositive = data.pnl >= 0;
                            return (
                              <tr key={strategy} className="border-b border-white/5 hover:bg-white/5">
                                <td className="py-2 px-2">
                                  <div className="flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: info.color }} />
                                    <span className="text-sm text-white">{info.name}</span>
                                  </div>
                                </td>
                                <td className={`text-right py-2 px-2 font-bold text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                  {isPositive ? '+' : ''}${data.pnl?.toFixed(2)}
                                </td>
                                <td className="text-right text-sm text-white/70 py-2 px-2">{data.trades}</td>
                                <td className={`text-right text-sm py-2 px-2 ${(data.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                                  {((data.win_rate || 0) * 100).toFixed(1)}%
                                </td>
                                <td className={`text-right text-sm py-2 px-2 ${(data.profit_factor || 0) >= 1.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                                  {(data.profit_factor || 0).toFixed(2)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="h-32 flex items-center justify-center text-white/40">No strategy data</div>
                  )}
                </div>

                {/* Asset Class Performance Table */}
                <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-purple-400" />
                    Asset Class Performance
                  </h3>
                  {results.asset_class_results && Object.keys(results.asset_class_results).length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-white/10">
                            <th className="text-left text-xs text-white/50 font-medium py-2 px-2">Asset Class</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">P&L</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Trades</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">Win Rate</th>
                            <th className="text-right text-xs text-white/50 font-medium py-2 px-2">PF</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(results.asset_class_results || {})
                            .sort((a, b) => b[1].pnl - a[1].pnl)
                            .map(([category, data]) => {
                              const isPositive = data.pnl >= 0;
                              return (
                                <tr key={category} className="border-b border-white/5 hover:bg-white/5">
                                  <td className="py-2 px-2">
                                    <span className="text-sm text-white capitalize">{category}</span>
                                  </td>
                                  <td className={`text-right py-2 px-2 font-bold text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                                    {isPositive ? '+' : ''}${data.pnl?.toFixed(2)}
                                  </td>
                                  <td className="text-right text-sm text-white/70 py-2 px-2">{data.trades}</td>
                                  <td className={`text-right text-sm py-2 px-2 ${(data.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-red-400'}`}>
                                    {((data.win_rate || 0) * 100).toFixed(1)}%
                                  </td>
                                  <td className={`text-right text-sm py-2 px-2 ${(data.profit_factor || 0) >= 1.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                                    {(data.profit_factor || 0).toFixed(2)}
                                  </td>
                                </tr>
                              );
                            })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="h-32 flex items-center justify-center text-white/40">No asset class data</div>
                  )}
                </div>
              </div>

              {/* Equity Curve - Full Width */}
              <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="equity-curve">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-cyan-400" />
                  Equity Curve
                  <span className="text-xs text-white/40 ml-2">({results.equity_curve?.length || 0} data points)</span>
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={results.equity_curve || []}>
                    <defs>
                      <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis dataKey="trade_num" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} label={{ value: 'Trade #', position: 'insideBottom', offset: -5, fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} />
                    <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} domain={['dataMin - 10', 'dataMax + 10']} />
                    <Tooltip 
                      contentStyle={{backgroundColor: 'rgba(0,0,0,0.95)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px', padding: '12px'}}
                      labelStyle={{color: 'rgba(255,255,255,0.7)', marginBottom: '4px'}}
                      formatter={(value, name) => [`$${Number(value).toFixed(2)}`, name === 'equity' ? 'Equity' : name]}
                      labelFormatter={(label) => `Trade #${label}`}
                    />
                    <Area type="monotone" dataKey="equity" stroke="#06b6d4" strokeWidth={2} fill="url(#equityGradient)" name="Equity" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Returns Distribution */}
              {results.returns_distribution && results.returns_distribution.bins && results.returns_distribution.bins.length > 0 && (
                <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="returns-distribution">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                      <BarChart3 className="w-5 h-5 text-purple-400" />
                      Returns Distribution
                    </h3>
                    {results.returns_distribution.stats && (
                      <div className="flex items-center gap-4 text-xs">
                        <span className="text-white/50">Mean: <span className={results.returns_distribution.stats.mean >= 0 ? 'text-green-400' : 'text-red-400'}>{results.returns_distribution.stats.mean?.toFixed(2)}%</span></span>
                        <span className="text-white/50">Median: <span className="text-cyan-400">{results.returns_distribution.stats.median?.toFixed(2)}%</span></span>
                        <span className="text-white/50">Std Dev: <span className="text-purple-400">{results.returns_distribution.stats.std?.toFixed(2)}%</span></span>
                      </div>
                    )}
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={results.returns_distribution.bins}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis dataKey="range" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 9 }} />
                      <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
                      <Tooltip 
                        contentStyle={{backgroundColor: 'rgba(0,0,0,0.95)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px'}}
                        formatter={(value) => [value, 'Trades']}
                      />
                      <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* AI Model Learning Stats - Enhanced */}
              <div className="rounded-xl bg-gradient-to-br from-purple-500/10 to-indigo-500/10 border border-purple-500/20 p-6">
                <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                  <Brain className="w-5 h-5 text-purple-400" />
                  AI Model Learning
                  <span className="text-xs text-white/40 ml-2">(Reinforcement Learning Engine)</span>
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <InfoTooltip text={METRIC_TOOLTIPS.training_iterations}>
                      <p className="text-xs text-white/50 mb-1">Training Iterations</p>
                    </InfoTooltip>
                    <p className="text-xl font-bold text-purple-400">{results.rl_learning_stats?.total_iterations || 0}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <InfoTooltip text={METRIC_TOOLTIPS.exploration_rate}>
                      <p className="text-xs text-white/50 mb-1">Exploration Rate</p>
                    </InfoTooltip>
                    <p className="text-xl font-bold text-purple-400">{((results.rl_learning_stats?.epsilon || 0.15) * 100).toFixed(1)}%</p>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <InfoTooltip text={METRIC_TOOLTIPS.avg_reward}>
                      <p className="text-xs text-white/50 mb-1">Avg Reward (Last 100)</p>
                    </InfoTooltip>
                    <p className={`text-xl font-bold ${(results.rl_learning_stats?.avg_reward_100 || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(results.rl_learning_stats?.avg_reward_100 || 0).toFixed(4)}
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <InfoTooltip text={METRIC_TOOLTIPS.experience_buffer}>
                      <p className="text-xs text-white/50 mb-1">Experience Buffer</p>
                    </InfoTooltip>
                    <p className="text-xl font-bold text-cyan-400">{results.rl_learning_stats?.buffer_size || 0}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <InfoTooltip text={METRIC_TOOLTIPS.q_table_usage}>
                      <p className="text-xs text-white/50 mb-1">Q-Table Usage</p>
                    </InfoTooltip>
                    <p className="text-xl font-bold text-yellow-400">{(results.rl_learning_stats?.q_table_nonzero_pct || 0).toFixed(1)}%</p>
                  </div>
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <InfoTooltip text="Probability of positive reward from recent actions">
                      <p className="text-xs text-white/50 mb-1">Positive Rate</p>
                    </InfoTooltip>
                    <p className="text-xl font-bold text-green-400">{((results.rl_learning_stats?.positive_rate || 0) * 100).toFixed(1)}%</p>
                  </div>
                </div>
                
                {/* Action Distribution */}
                {results.rl_learning_stats?.action_distribution && (
                  <div className="mt-4 p-4 rounded-lg bg-white/5 border border-white/10">
                    <InfoTooltip text={METRIC_TOOLTIPS.action_distribution}>
                      <p className="text-xs text-white/50 mb-3">Action Distribution (Q-Table Preferred Actions)</p>
                    </InfoTooltip>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(results.rl_learning_stats.action_distribution).map(([action, count]) => (
                        <div key={action} className="px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/20">
                          <span className="text-xs text-purple-300">{action}: </span>
                          <span className="text-sm font-bold text-purple-400">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* AI Signals Integration Stats - Enhanced with Tooltips */}
              {results.ai_signals_stats && (
                <div className="rounded-xl bg-gradient-to-br from-cyan-500/10 to-blue-500/10 border border-cyan-500/20 p-6" data-testid="ai-signals-stats">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Activity className="w-5 h-5 text-cyan-400" />
                    AI Signal Integration
                    <span className="text-xs text-white/40 ml-2">(Sentiment & Whale Tracking)</span>
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <InfoTooltip text={METRIC_TOOLTIPS.sentiment_signals}>
                        <p className="text-xs text-white/50 mb-1">Sentiment Signals</p>
                      </InfoTooltip>
                      <p className="text-xl font-bold text-cyan-400">{results.ai_signals_stats.sentiment_signals_used || 0}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <InfoTooltip text={METRIC_TOOLTIPS.whale_signals}>
                        <p className="text-xs text-white/50 mb-1">Whale Signals</p>
                      </InfoTooltip>
                      <p className="text-xl font-bold text-orange-400">{results.ai_signals_stats.whale_signals_used || 0}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <InfoTooltip text={METRIC_TOOLTIPS.avg_sentiment}>
                        <p className="text-xs text-white/50 mb-1">Avg Sentiment</p>
                      </InfoTooltip>
                      <p className={`text-xl font-bold ${(results.ai_signals_stats.avg_sentiment || 0.5) > 0.5 ? 'text-green-400' : 'text-yellow-400'}`}>
                        {((results.ai_signals_stats.avg_sentiment || 0.5) * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <InfoTooltip text={METRIC_TOOLTIPS.avg_whale_activity}>
                        <p className="text-xs text-white/50 mb-1">Avg Whale Activity</p>
                      </InfoTooltip>
                      <p className="text-xl font-bold text-orange-400">
                        {((results.ai_signals_stats.avg_whale_activity || 0) * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <InfoTooltip text={METRIC_TOOLTIPS.bullish_whales}>
                        <p className="text-xs text-white/50 mb-1">Bullish Whales</p>
                      </InfoTooltip>
                      <p className="text-xl font-bold text-green-400">{results.ai_signals_stats.bullish_whale_markets || 0}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <InfoTooltip text={METRIC_TOOLTIPS.bearish_whales}>
                        <p className="text-xs text-white/50 mb-1">Bearish Whales</p>
                      </InfoTooltip>
                      <p className="text-xl font-bold text-red-400">{results.ai_signals_stats.bearish_whale_markets || 0}</p>
                    </div>
                  </div>
                </div>
              )}
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
        </>
      )}

      {/* HISTORY TAB */}
      {activeTab === 'history' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white">Backtest History</h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-white/60">{selectedBacktests.length} selected</span>
              <button
                onClick={compareSelectedBacktests}
                disabled={selectedBacktests.length === 0}
                className="px-4 py-2 rounded-lg bg-gradient-to-r from-purple-500 to-indigo-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                data-testid="analyze-selected-btn"
              >
                <GitCompare className="w-4 h-4" />
                Analyze Selected
              </button>
            </div>
          </div>

          {history.length === 0 ? (
            <div className="rounded-xl bg-white/5 border border-white/10 p-12 text-center">
              <History className="w-16 h-16 text-white/20 mx-auto mb-4" />
              <p className="text-white/60 text-lg">No backtest history</p>
              <p className="text-white/40 text-sm mt-2">Run backtests to build your history for comparison</p>
            </div>
          ) : (
            <div className="space-y-3">
              {history.map((bt, idx) => (
                <div
                  key={bt.backtest_id}
                  data-testid={`history-item-${idx}`}
                  onClick={() => openDeepDive(bt.backtest_id)}
                  className={`rounded-xl border p-4 transition-all cursor-pointer ${
                    selectedBacktests.includes(bt.backtest_id)
                      ? 'bg-purple-500/10 border-purple-500/30'
                      : 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-cyan-500/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleBacktestSelection(bt.backtest_id); }}
                        className={`w-6 h-6 rounded border-2 flex items-center justify-center ${
                          selectedBacktests.includes(bt.backtest_id)
                            ? 'border-purple-500 bg-purple-500'
                            : 'border-white/30 hover:border-white/50'
                        }`}
                      >
                        {selectedBacktests.includes(bt.backtest_id) && (
                          <CheckCircle className="w-4 h-4 text-white" />
                        )}
                      </button>
                      <div>
                        <p className="text-sm text-white font-medium">
                          {new Date(bt.completed_at).toLocaleString()}
                        </p>
                        <p className="text-xs text-white/50">
                          {bt.data_summary?.total_snapshots?.toLocaleString() || 0} snapshots | {bt.total_trades || 0} trades
                          {bt.data_quality?.data_source_mode && (
                            <span className="ml-2 px-1.5 py-0.5 rounded bg-white/10 text-white/60">
                              {bt.data_quality.data_source_mode}
                            </span>
                          )}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-6">
                      <div className="text-right">
                        <p className={`text-lg font-bold ${bt.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {bt.total_pnl >= 0 ? '+' : ''}${bt.total_pnl?.toFixed(2)}
                        </p>
                        <p className="text-xs text-white/50">{bt.total_return_pct?.toFixed(2)}% return</p>
                      </div>
                      
                      <div className="text-center px-4 border-l border-white/10">
                        <p className="text-sm font-medium text-cyan-400">{((bt.win_rate || 0) * 100).toFixed(1)}%</p>
                        <p className="text-xs text-white/50">Win Rate</p>
                      </div>
                      
                      <div className="text-center px-4 border-l border-white/10">
                        <p className="text-sm font-medium text-purple-400">{bt.sharpe_ratio?.toFixed(2)}</p>
                        <p className="text-xs text-white/50">Sharpe</p>
                      </div>
                      
                      <div className="flex items-center gap-2 pl-4 border-l border-white/10">
                        <button
                          onClick={(e) => { e.stopPropagation(); viewBacktestResult(bt.backtest_id); }}
                          className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-white/70 hover:text-white transition"
                          title="View in Results Tab"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteBacktest(bt.backtest_id); }}
                          className="p-2 rounded-lg bg-white/5 hover:bg-red-500/20 text-white/70 hover:text-red-400 transition"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* DEEP DIVE MODAL */}
      {deepDiveBacktest && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={closeDeepDive}>
          <div 
            className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl border border-white/10 w-full max-w-5xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="sticky top-0 bg-slate-900/95 backdrop-blur-sm border-b border-white/10 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">Backtest Deep Dive</h2>
                <p className="text-sm text-white/50">
                  {new Date(deepDiveBacktest.completed_at).toLocaleString()} • ID: {deepDiveBacktest.backtest_id?.slice(0, 8)}...
                </p>
              </div>
              <button
                onClick={closeDeepDive}
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-white/70 hover:text-white transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-6">
              {/* Key Metrics Row */}
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-xs text-white/50 mb-1">Total Return</p>
                  <p className={`text-2xl font-bold ${deepDiveBacktest.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {deepDiveBacktest.total_return_pct >= 0 ? '+' : ''}{deepDiveBacktest.total_return_pct?.toFixed(2)}%
                  </p>
                  <p className="text-xs text-white/40">${deepDiveBacktest.total_pnl?.toFixed(2)}</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-xs text-white/50 mb-1">Total Trades</p>
                  <p className="text-2xl font-bold text-white">{deepDiveBacktest.total_trades}</p>
                  <p className="text-xs text-green-400">{deepDiveBacktest.winning_trades} wins</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-xs text-white/50 mb-1">Win Rate</p>
                  <p className="text-2xl font-bold text-cyan-400">{((deepDiveBacktest.win_rate || 0) * 100).toFixed(1)}%</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-xs text-white/50 mb-1">Sharpe Ratio</p>
                  <p className="text-2xl font-bold text-purple-400">{deepDiveBacktest.sharpe_ratio?.toFixed(2)}</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-xs text-white/50 mb-1">Profit Factor</p>
                  <p className="text-2xl font-bold text-yellow-400">{deepDiveBacktest.profit_factor?.toFixed(2)}</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-xs text-white/50 mb-1">Max Drawdown</p>
                  <p className="text-2xl font-bold text-red-400">-{((deepDiveBacktest.max_drawdown || 0) * 100).toFixed(2)}%</p>
                </div>
              </div>

              {/* Strategy Breakdown */}
              {deepDiveBacktest.strategy_results && Object.keys(deepDiveBacktest.strategy_results).length > 0 && (
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <h3 className="text-lg font-semibold text-white mb-4">Strategy Performance</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                    {Object.entries(deepDiveBacktest.strategy_results).map(([strategy, data]) => {
                      const info = STRATEGY_INFO[strategy] || { name: strategy, color: '#666' };
                      return (
                        <div key={strategy} className={`p-3 rounded-lg border ${data.pnl >= 0 ? 'bg-green-500/5 border-green-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
                          <div className="flex items-center gap-2 mb-2">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: info.color }} />
                            <span className="text-sm text-white font-medium">{info.name}</span>
                          </div>
                          <div className={`text-xl font-bold ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {data.pnl >= 0 ? '+' : ''}${data.pnl?.toFixed(2)}
                          </div>
                          <div className="flex justify-between text-xs text-white/50 mt-1">
                            <span>{data.trades} trades</span>
                            <span className={(data.win_rate || 0) >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                              {((data.win_rate || 0) * 100).toFixed(1)}% WR
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Asset Class Breakdown */}
              {deepDiveBacktest.asset_class_results && Object.keys(deepDiveBacktest.asset_class_results).length > 0 && (
                <div className="rounded-xl bg-white/5 border border-white/10 p-4">
                  <h3 className="text-lg font-semibold text-white mb-4">Asset Class Performance</h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                    {Object.entries(deepDiveBacktest.asset_class_results).map(([category, data]) => (
                      <div key={category} className={`p-3 rounded-lg border ${data.pnl >= 0 ? 'bg-green-500/5 border-green-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
                        <span className="text-sm text-white font-medium capitalize">{category}</span>
                        <div className={`text-lg font-bold ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {data.pnl >= 0 ? '+' : ''}${data.pnl?.toFixed(2)}
                        </div>
                        <div className="text-xs text-white/50">{data.trades} trades</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Signals Stats */}
              {deepDiveBacktest.ai_signals_stats && (
                <div className="rounded-xl bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border border-cyan-500/20 p-4">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Brain className="w-5 h-5 text-cyan-400" />
                    AI Signal Usage
                  </h3>
                  <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
                    <div className="text-center">
                      <p className="text-2xl font-bold text-cyan-400">{deepDiveBacktest.ai_signals_stats.sentiment_signals_used}</p>
                      <p className="text-xs text-white/50">Sentiment Signals</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-orange-400">{deepDiveBacktest.ai_signals_stats.whale_signals_used}</p>
                      <p className="text-xs text-white/50">Whale Signals</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-white">{((deepDiveBacktest.ai_signals_stats.avg_sentiment || 0) * 100).toFixed(0)}%</p>
                      <p className="text-xs text-white/50">Avg Sentiment</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-white">{((deepDiveBacktest.ai_signals_stats.avg_whale_activity || 0) * 100).toFixed(0)}%</p>
                      <p className="text-xs text-white/50">Avg Whale Activity</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-green-400">{deepDiveBacktest.ai_signals_stats.bullish_whale_markets}</p>
                      <p className="text-xs text-white/50">Bullish Whales</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-red-400">{deepDiveBacktest.ai_signals_stats.bearish_whale_markets}</p>
                      <p className="text-xs text-white/50">Bearish Whales</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Data Quality */}
              {deepDiveBacktest.data_quality && (
                <div className={`rounded-xl border p-4 ${
                  deepDiveBacktest.data_quality.data_source === 'real' 
                    ? 'bg-green-500/10 border-green-500/20'
                    : 'bg-yellow-500/10 border-yellow-500/20'
                }`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Database className={`w-5 h-5 ${deepDiveBacktest.data_quality.data_source === 'real' ? 'text-green-400' : 'text-yellow-400'}`} />
                      <div>
                        <h4 className="text-sm font-semibold text-white">
                          Data Source: {deepDiveBacktest.data_quality.data_source_mode || deepDiveBacktest.data_quality.data_source}
                        </h4>
                        <p className="text-xs text-white/60">
                          {deepDiveBacktest.data_quality.real_price_data_points?.toLocaleString()} real | {deepDiveBacktest.data_quality.simulated_price_data_points?.toLocaleString()} simulated
                        </p>
                      </div>
                    </div>
                    <div className={`text-2xl font-bold ${deepDiveBacktest.data_quality.real_data_percentage > 50 ? 'text-green-400' : 'text-yellow-400'}`}>
                      {deepDiveBacktest.data_quality.real_data_percentage}% Real
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* COMPARISON TAB */}
      {activeTab === 'compare' && (
        <div className="space-y-6">
          {!comparisonData ? (
            <div className="rounded-xl bg-white/5 border border-white/10 p-12 text-center">
              <GitCompare className="w-16 h-16 text-white/20 mx-auto mb-4" />
              <p className="text-white/60 text-lg">No comparison data</p>
              <p className="text-white/40 text-sm mt-2">Select backtests from History tab and click &quot;Analyze Selected&quot;</p>
              <button
                onClick={() => setActiveTab('history')}
                className="mt-4 px-4 py-2 rounded-lg bg-purple-500/20 text-purple-400 text-sm font-medium hover:bg-purple-500/30 transition"
              >
                Go to History
              </button>
            </div>
          ) : (
            <>
              {/* Quality Score */}
              {comparisonData.educational_analysis?.strategy_quality_score && (
                <div className="rounded-xl bg-gradient-to-r from-purple-500/10 to-indigo-500/10 border border-purple-500/20 p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                      <Award className="w-5 h-5 text-purple-400" />
                      Strategy Quality Score
                    </h3>
                    <div className="text-right">
                      <span className={`text-4xl font-bold ${
                        comparisonData.educational_analysis.strategy_quality_score.grade === 'A' ? 'text-green-400' :
                        comparisonData.educational_analysis.strategy_quality_score.grade === 'B' ? 'text-cyan-400' :
                        comparisonData.educational_analysis.strategy_quality_score.grade === 'C' ? 'text-yellow-400' :
                        'text-red-400'
                      }`}>
                        {comparisonData.educational_analysis.strategy_quality_score.grade}
                      </span>
                      <p className="text-sm text-white/60">
                        {comparisonData.educational_analysis.strategy_quality_score.total_score}/100
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {comparisonData.educational_analysis.strategy_quality_score.breakdown?.map((item, idx) => (
                      <div key={idx} className="p-3 rounded-lg bg-white/5">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-white/60">{item.component}</span>
                          <span className="text-xs text-cyan-400">{item.score}/{item.max}</span>
                        </div>
                        <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-cyan-500 to-purple-500 rounded-full"
                            style={{ width: `${(item.score / item.max) * 100}%` }}
                          />
                        </div>
                        <p className="text-xs text-white/40 mt-1">{item.note}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Improvement Insights */}
              {comparisonData.improvement_insights && comparisonData.improvement_insights.length > 0 && (
                <div className="rounded-xl bg-white/5 border border-white/10 p-6">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Lightbulb className="w-5 h-5 text-yellow-400" />
                    Improvement Insights
                  </h3>
                  <div className="space-y-3">
                    {comparisonData.improvement_insights.map((insight, idx) => (
                      <div
                        key={idx}
                        className={`p-4 rounded-lg border ${
                          insight.severity === 'critical' ? 'bg-red-500/10 border-red-500/30' :
                          insight.severity === 'high' ? 'bg-orange-500/10 border-orange-500/30' :
                          insight.severity === 'medium' ? 'bg-yellow-500/10 border-yellow-500/30' :
                          'bg-blue-500/10 border-blue-500/30'
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <AlertTriangle className={`w-5 h-5 flex-shrink-0 ${
                            insight.severity === 'critical' ? 'text-red-400' :
                            insight.severity === 'high' ? 'text-orange-400' :
                            insight.severity === 'medium' ? 'text-yellow-400' :
                            'text-blue-400'
                          }`} />
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded uppercase ${
                                insight.severity === 'critical' ? 'bg-red-500/30 text-red-400' :
                                insight.severity === 'high' ? 'bg-orange-500/30 text-orange-400' :
                                insight.severity === 'medium' ? 'bg-yellow-500/30 text-yellow-400' :
                                'bg-blue-500/30 text-blue-400'
                              }`}>
                                {insight.severity}
                              </span>
                              <span className="text-sm text-white font-medium">{insight.area}</span>
                            </div>
                            <p className="text-sm text-white/80 mb-2">{insight.issue}</p>
                            <p className="text-sm text-white/60 mb-1"><strong>Recommendation:</strong> {insight.recommendation}</p>
                            <p className="text-sm text-cyan-400"><strong>Action:</strong> {insight.action}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations Summary */}
              {comparisonData.educational_analysis?.recommendations_summary && (
                <div className="rounded-xl bg-white/5 border border-white/10 p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Priority Actions</h3>
                  <ul className="space-y-2">
                    {comparisonData.educational_analysis.recommendations_summary.map((rec, idx) => (
                      <li key={idx} className="text-sm text-white/80 flex items-start gap-2">
                        <span className="text-lg">{rec.charAt(0)}</span>
                        <span>{rec.substring(2)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Comparison Metrics */}
              {comparisonData.comparison_metrics && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {Object.entries(comparisonData.comparison_metrics).map(([key, data]) => (
                    <div key={key} className="rounded-xl bg-white/5 border border-white/10 p-4">
                      <h4 className="text-sm font-semibold text-white capitalize mb-3">
                        {key.replace(/_/g, ' ')}
                      </h4>
                      <div className="grid grid-cols-3 gap-2 text-center mb-3">
                        <div>
                          <p className="text-xs text-white/50">Best</p>
                          <p className="text-sm font-bold text-green-400">
                            {typeof data.best === 'number' ? (key.includes('rate') || key.includes('drawdown') ? `${(data.best * 100).toFixed(1)}%` : data.best.toFixed(2)) : data.best}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-white/50">Avg</p>
                          <p className="text-sm font-bold text-cyan-400">
                            {typeof data.avg === 'number' ? (key.includes('rate') || key.includes('drawdown') ? `${(data.avg * 100).toFixed(1)}%` : data.avg.toFixed(2)) : data.avg}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-white/50">Worst</p>
                          <p className="text-sm font-bold text-red-400">
                            {typeof data.worst === 'number' ? (key.includes('rate') || key.includes('drawdown') ? `${(data.worst * 100).toFixed(1)}%` : data.worst.toFixed(2)) : data.worst}
                          </p>
                        </div>
                      </div>
                      {data.target && (
                        <p className="text-xs text-white/40">Target: {typeof data.target === 'number' ? (key.includes('rate') || key.includes('drawdown') ? `${(data.target * 100).toFixed(0)}%` : data.target) : data.target}</p>
                      )}
                      {data.interpretation && (
                        <p className="text-xs text-white/50 mt-2">{data.interpretation}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Strategy Comparison */}
              {comparisonData.strategy_comparison && Object.keys(comparisonData.strategy_comparison).length > 0 && (
                <div className="rounded-xl bg-white/5 border border-white/10 p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Strategy Comparison</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {Object.entries(comparisonData.strategy_comparison).map(([strat, data]) => {
                      const info = STRATEGY_INFO[strat] || { name: strat, color: '#666' };
                      return (
                        <div
                          key={strat}
                          className={`p-4 rounded-lg border ${
                            data.is_profitable
                              ? 'bg-green-500/5 border-green-500/20'
                              : 'bg-red-500/5 border-red-500/20'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: info.color }} />
                              <span className="text-sm font-medium text-white">{info.name}</span>
                            </div>
                            <span className={`text-sm font-bold ${data.is_profitable ? 'text-green-400' : 'text-red-400'}`}>
                              {data.total_pnl >= 0 ? '+' : ''}${data.total_pnl?.toFixed(2)}
                            </span>
                          </div>
                          <div className="grid grid-cols-3 gap-2 text-center text-xs">
                            <div>
                              <p className="text-white/50">Avg P&L</p>
                              <p className={`font-medium ${data.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                ${data.avg_pnl?.toFixed(2)}
                              </p>
                            </div>
                            <div>
                              <p className="text-white/50">Win Rate</p>
                              <p className="font-medium text-cyan-400">{((data.avg_win_rate || 0) * 100).toFixed(1)}%</p>
                            </div>
                            <div>
                              <p className="text-white/50">Total Trades</p>
                              <p className="font-medium text-white">{data.total_trades}</p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Asset Class Comparison */}
              {comparisonData.asset_class_comparison && Object.keys(comparisonData.asset_class_comparison).length > 0 && (
                <div className="rounded-xl bg-white/5 border border-white/10 p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Asset Class Comparison</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {Object.entries(comparisonData.asset_class_comparison).map(([asset, data], idx) => {
                      const colors = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444'];
                      return (
                        <div
                          key={asset}
                          className={`p-4 rounded-lg ${
                            data.is_profitable ? 'bg-green-500/5' : 'bg-red-500/5'
                          }`}
                        >
                          <div className="flex items-center gap-2 mb-2">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: colors[idx % colors.length] }} />
                            <span className="text-sm text-white capitalize">{asset}</span>
                          </div>
                          <p className={`text-lg font-bold ${data.is_profitable ? 'text-green-400' : 'text-red-400'}`}>
                            {data.total_pnl >= 0 ? '+' : ''}${data.total_pnl?.toFixed(2)}
                          </p>
                          <p className="text-xs text-white/50">{data.total_trades} trades | {((data.avg_win_rate || 0) * 100).toFixed(0)}% win</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* LEARN TAB */}
      {activeTab === 'learn' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/20 p-6">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <BookOpen className="w-6 h-6 text-blue-400" />
              Understanding Trading Metrics
            </h2>
            <p className="text-white/70">
              Learn how to interpret your backtest results and improve your trading strategy.
            </p>
          </div>

          {/* Key Concepts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ConceptCard
              title="Sharpe Ratio"
              description="Measures excess return per unit of risk (volatility)"
              formula="(Return - Risk-Free Rate) / Standard Deviation"
              interpretation={{
                'Below 0': 'Strategy is losing money on a risk-adjusted basis',
                '0 to 1': 'Positive but not compelling risk/reward',
                '1 to 2': 'Good risk-adjusted performance',
                'Above 2': 'Excellent - but verify if sustainable'
              }}
              color="purple"
            />
            <ConceptCard
              title="Max Drawdown"
              description="Largest peak-to-trough decline in equity"
              formula="(Peak Value - Trough Value) / Peak Value"
              interpretation={{
                '< 5%': 'Conservative - excellent risk control',
                '5-10%': 'Moderate - acceptable for most strategies',
                '10-20%': 'Aggressive - higher risk tolerance needed',
                '> 20%': 'Dangerous - may indicate poor risk management'
              }}
              color="orange"
            />
            <ConceptCard
              title="Profit Factor"
              description="Ratio of gross profits to gross losses"
              formula="Gross Profit / Gross Loss"
              interpretation={{
                '< 1.0': 'Losing money - losses exceed profits',
                '1.0 - 1.5': 'Marginal - high risk of turning negative',
                '1.5 - 2.0': 'Good - reasonable profitability buffer',
                '> 2.0': 'Strong - but verify sample size'
              }}
              color="green"
            />
            <ConceptCard
              title="Win Rate"
              description="Percentage of trades that are profitable"
              formula="Winning Trades / Total Trades"
              interpretation={{
                '< 40%': 'Low - need high avg win vs loss ratio',
                '40-50%': 'Below average - optimize entry/exit',
                '50-60%': 'Good - solid foundation',
                '> 60%': 'Excellent - but watch for small wins'
              }}
              color="cyan"
            />
          </div>

          {/* Pro Tips */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-yellow-400" />
              Pro Tips
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-white/5">
                <h4 className="text-sm font-medium text-white mb-2">Win Rate vs Profit Factor</h4>
                <p className="text-xs text-white/60">
                  A 90% win rate with a 0.8 profit factor means many small wins but devastating losses. 
                  A 30% win rate with a 2.5 profit factor can be more profitable - few wins but they&apos;re big.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-white/5">
                <h4 className="text-sm font-medium text-white mb-2">Sample Size Matters</h4>
                <p className="text-xs text-white/60">
                  Don&apos;t trust results from &lt;100 trades. Statistical significance requires enough data.
                  Run multiple backtests across different time periods.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-white/5">
                <h4 className="text-sm font-medium text-white mb-2">Drawdown Psychology</h4>
                <p className="text-xs text-white/60">
                  Can you handle a 20% drawdown emotionally? If not, target lower. 
                  Your actual trading will always feel worse than backtest drawdowns.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-white/5">
                <h4 className="text-sm font-medium text-white mb-2">Overfitting Warning</h4>
                <p className="text-xs text-white/60">
                  If results are &quot;too good&quot; (Sharpe &gt; 3), you may be overfitting to historical data.
                  Test on out-of-sample data before going live.
                </p>
              </div>
            </div>
          </div>
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

// Concept Card Component
const ConceptCard = ({ title, description, formula, interpretation, color }) => {
  const colorMap = {
    purple: 'border-purple-500/20 from-purple-500/10',
    orange: 'border-orange-500/20 from-orange-500/10',
    green: 'border-green-500/20 from-green-500/10',
    cyan: 'border-cyan-500/20 from-cyan-500/10'
  };
  const textColorMap = {
    purple: 'text-purple-400',
    orange: 'text-orange-400',
    green: 'text-green-400',
    cyan: 'text-cyan-400'
  };

  return (
    <div className={`rounded-xl bg-gradient-to-br ${colorMap[color]} to-transparent border p-6`}>
      <h3 className={`text-lg font-semibold ${textColorMap[color]} mb-2`}>{title}</h3>
      <p className="text-sm text-white/70 mb-3">{description}</p>
      <div className="p-2 rounded bg-black/30 mb-4">
        <code className="text-xs text-white/60">{formula}</code>
      </div>
      <div className="space-y-1">
        {Object.entries(interpretation).map(([key, value]) => (
          <div key={key} className="flex items-start gap-2 text-xs">
            <span className="text-white/50 w-20 flex-shrink-0">{key}:</span>
            <span className="text-white/70">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Backtest; 
