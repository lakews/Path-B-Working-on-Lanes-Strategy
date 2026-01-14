import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { 
  Sliders, Play, Square, TrendingUp, Target, BarChart3, Zap, Scale, GitBranch,
  RefreshCw, CheckCircle, XCircle, Clock, Award, Activity, Loader2
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Legend } from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STRATEGIES = [
  { id: 'delta_neutral', name: 'Delta-Neutral', icon: Scale, color: '#06b6d4' },
  { id: 'volatility_exploitation', name: 'Volatility Exploitation', icon: Zap, color: '#f59e0b' },
  { id: 'alpha_directional', name: 'Alpha-Directional', icon: TrendingUp, color: '#10b981' },
  { id: 'arbitrage', name: 'Multi-Market Arbitrage', icon: GitBranch, color: '#8b5cf6' },
];

// Define the parameter grids for transparency
const PARAMETER_GRIDS = {
  delta_neutral: {
    profit_target: { range: [0.003, 0.005, 0.008, 0.01], desc: 'Target profit %' },
    stop_loss: { range: [0.01, 0.015, 0.02, 0.025], desc: 'Stop loss %' },
    bank_profit_threshold: { range: [0.0005, 0.001, 0.0015, 0.002], desc: 'Bank small profits at %' },
    timeout_snapshots: { range: [8, 12, 16, 20], desc: 'Max hold time (snapshots)' },
    spread_threshold: { range: [0.008, 0.01, 0.012, 0.015], desc: 'Spread capture threshold' }
  },
  volatility_exploitation: {
    profit_target: { range: [0.02, 0.03, 0.04, 0.05], desc: 'Target profit %' },
    stop_loss: { range: [0.01, 0.015, 0.02, 0.025], desc: 'Stop loss %' },
    min_volatility: { range: [0.02, 0.03, 0.04], desc: 'Min volatility to enter' },
    max_volatility: { range: [0.08, 0.1, 0.15], desc: 'Max volatility cap' },
    trend_threshold: { range: [0.005, 0.01, 0.015], desc: 'Trend strength threshold' }
  },
  alpha_directional: {
    profit_target: { range: [0.02, 0.03, 0.05, 0.08], desc: 'Target profit %' },
    stop_loss: { range: [0.01, 0.02, 0.03], desc: 'Stop loss %' },
    trend_threshold: { range: [0.005, 0.01, 0.02], desc: 'Trend threshold to enter' },
    trailing_stop_activation: { range: [0.01, 0.015, 0.02], desc: 'Trailing stop activation %' },
    trailing_stop_distance: { range: [0.005, 0.008, 0.01], desc: 'Trailing stop distance %' }
  },
  arbitrage: {
    profit_target: { range: [0.005, 0.008, 0.01, 0.015], desc: 'Target profit %' },
    stop_loss: { range: [0.005, 0.008, 0.01, 0.015], desc: 'Stop loss %' },
    min_spread: { range: [0.005, 0.008, 0.01], desc: 'Min spread to enter' },
    position_timeout: { range: [5, 10, 15, 20], desc: 'Position timeout (snapshots)' }
  }
};

const StrategyTuning = () => {
  const [selectedStrategy, setSelectedStrategy] = useState('delta_neutral');
  const [tuning, setTuning] = useState(false);
  const [results, setResults] = useState(null);
  const [bestParams, setBestParams] = useState({});
  const [history, setHistory] = useState([]);
  const [maxCombinations, setMaxCombinations] = useState(30);

  useEffect(() => {
    fetchHistory();
    fetchBestParams();
  }, []);

  const fetchHistory = async () => {
    try {
      const response = await axios.get(`${API}/tuning/history?limit=10`);
      setHistory(response.data.history || []);
    } catch (e) {
      console.error('Error fetching history:', e);
    }
  };

  const fetchBestParams = async () => {
    try {
      const params = {};
      for (const strategy of STRATEGIES) {
        const response = await axios.get(`${API}/tuning/best/${strategy.id}`);
        if (response.data && response.data.parameters) {
          params[strategy.id] = response.data;
        }
      }
      setBestParams(params);
    } catch (e) {
      console.error('Error fetching best params:', e);
    }
  };

  const startTuning = async (strategyId) => {
    setTuning(true);
    setResults(null);
    toast.info(`Starting parameter tuning for ${strategyId}...`);

    try {
      const response = await axios.post(
        `${API}/tuning/strategy?strategy_name=${strategyId}&max_combinations=${maxCombinations}`
      );
      
      setResults(response.data);
      toast.success(`Tuning complete! Best score: ${(response.data.best_score * 100).toFixed(1)}%`);
      fetchHistory();
      fetchBestParams();
    } catch (e) {
      toast.error('Tuning failed: ' + (e.response?.data?.message || e.message));
    } finally {
      setTuning(false);
    }
  };

  const tuneAllStrategies = async () => {
    setTuning(true);
    setResults(null);
    toast.info('Starting full optimization (this may take a few minutes)...');

    try {
      const response = await axios.post(
        `${API}/tuning/all?max_combinations_per_strategy=20`
      );
      
      setResults(response.data);
      toast.success('Full optimization complete!');
      fetchHistory();
      fetchBestParams();
    } catch (e) {
      toast.error('Optimization failed: ' + (e.response?.data?.message || e.message));
    } finally {
      setTuning(false);
    }
  };

  const stopTuning = async () => {
    try {
      await axios.post(`${API}/tuning/stop`);
      setTuning(false);
      toast.info('Tuning stopped');
    } catch (e) {
      toast.error('Failed to stop tuning');
    }
  };

  const formatParams = (params) => {
    if (!params) return '-';
    return Object.entries(params)
      .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(3) : v}`)
      .join(', ');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center">
              <Sliders className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Strategy Tuning</h1>
              <p className="text-white/60 text-sm">Automatic parameter optimization using grid search</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={tuneAllStrategies}
              disabled={tuning}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-purple-500 to-pink-600 text-white font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center gap-2"
              data-testid="tune-all-btn"
            >
              {tuning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              Tune All Strategies
            </button>
            {tuning && (
              <button
                onClick={stopTuning}
                className="px-4 py-2 rounded-xl bg-red-500/20 border border-red-500/30 text-red-400 font-medium hover:bg-red-500/30 transition"
              >
                <Square className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Strategy Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {STRATEGIES.map((strategy) => {
            const Icon = strategy.icon;
            const best = bestParams[strategy.id];
            const isSelected = selectedStrategy === strategy.id;

            return (
              <div
                key={strategy.id}
                onClick={() => setSelectedStrategy(strategy.id)}
                className={`rounded-xl p-4 border-2 cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-white/10 border-cyan-500/50 shadow-lg shadow-cyan-500/10'
                    : 'bg-white/5 border-white/10 hover:border-white/20'
                }`}
                data-testid={`strategy-card-${strategy.id}`}
              >
                <div className="flex items-center gap-3 mb-3">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: `${strategy.color}20` }}
                  >
                    <Icon className="w-5 h-5" style={{ color: strategy.color }} />
                  </div>
                  <div>
                    <h3 className="text-white font-medium text-sm">{strategy.name}</h3>
                    {best && (
                      <p className="text-xs text-green-400">Score: {(best.score * 100).toFixed(1)}%</p>
                    )}
                  </div>
                </div>

                {best && best.metrics && (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2 rounded bg-white/5">
                      <p className="text-white/50">Win Rate</p>
                      <p className="text-white font-medium">{(best.metrics.win_rate * 100).toFixed(1)}%</p>
                    </div>
                    <div className="p-2 rounded bg-white/5">
                      <p className="text-white/50">Sharpe</p>
                      <p className="text-white font-medium">{best.metrics.sharpe_ratio?.toFixed(2) || '-'}</p>
                    </div>
                  </div>
                )}

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    startTuning(strategy.id);
                  }}
                  disabled={tuning}
                  className="mt-3 w-full py-2 rounded-lg bg-white/10 text-white text-xs font-medium hover:bg-white/20 transition disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {tuning && selectedStrategy === strategy.id ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Tuning...
                    </>
                  ) : (
                    <>
                      <Play className="w-3 h-3" />
                      Tune
                    </>
                  )}
                </button>
              </div>
            );
          })}
        </div>

        {/* Controls */}
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-xs text-white/50 mb-1">Max Combinations</p>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min="10"
                    max="100"
                    value={maxCombinations}
                    onChange={(e) => setMaxCombinations(parseInt(e.target.value))}
                    className="w-32"
                  />
                  <span className="text-white font-medium w-8">{maxCombinations}</span>
                </div>
              </div>
              <div className="w-px h-10 bg-white/10" />
              <div>
                <p className="text-xs text-white/50">Selected Strategy</p>
                <p className="text-white font-medium">{STRATEGIES.find(s => s.id === selectedStrategy)?.name}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs text-white/50">
              <Activity className="w-4 h-4" />
              {tuning ? 'Tuning in progress...' : 'Ready to tune'}
            </div>
          </div>
        </div>

        {/* Results */}
        {results && (
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Award className="w-5 h-5 text-yellow-400" />
              Tuning Results
            </h3>

            {results.best_parameters && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Best Parameters */}
                <div className="rounded-lg bg-gradient-to-br from-green-500/10 to-emerald-500/10 border border-green-500/20 p-4">
                  <h4 className="text-green-400 font-medium mb-3">Best Parameters</h4>
                  <div className="space-y-2">
                    {Object.entries(results.best_parameters).map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between">
                        <span className="text-white/60 text-sm">{key}</span>
                        <span className="text-white font-mono text-sm">
                          {typeof value === 'number' ? value.toFixed(4) : value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Best Metrics */}
                {results.best_metrics && (
                  <div className="rounded-lg bg-white/5 border border-white/10 p-4">
                    <h4 className="text-white font-medium mb-3">Performance Metrics</h4>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 rounded bg-white/5">
                        <p className="text-xs text-white/50">Return</p>
                        <p className={`text-lg font-bold ${results.best_metrics.total_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {results.best_metrics.total_return?.toFixed(2)}%
                        </p>
                      </div>
                      <div className="p-3 rounded bg-white/5">
                        <p className="text-xs text-white/50">Win Rate</p>
                        <p className="text-lg font-bold text-cyan-400">
                          {(results.best_metrics.win_rate * 100)?.toFixed(1)}%
                        </p>
                      </div>
                      <div className="p-3 rounded bg-white/5">
                        <p className="text-xs text-white/50">Sharpe Ratio</p>
                        <p className="text-lg font-bold text-purple-400">
                          {results.best_metrics.sharpe_ratio?.toFixed(2)}
                        </p>
                      </div>
                      <div className="p-3 rounded bg-white/5">
                        <p className="text-xs text-white/50">Profit Factor</p>
                        <p className="text-lg font-bold text-yellow-400">
                          {results.best_metrics.profit_factor?.toFixed(2)}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Top 5 Results Chart */}
            {results.top_5 && results.top_5.length > 0 && (
              <div className="mt-6">
                <h4 className="text-white font-medium mb-3">Top 5 Parameter Sets</h4>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={results.top_5.map((r, i) => ({
                    name: `Set ${i + 1}`,
                    score: r.score * 100,
                    return: r.metrics?.total_return || 0
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
                    <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                    />
                    <Bar dataKey="score" fill="#8b5cf6" name="Score %" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="mt-4 p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
              <p className="text-sm text-cyan-400">
                <CheckCircle className="w-4 h-4 inline mr-2" />
                Tested {results.combinations_tested} parameter combinations. Best score: {(results.best_score * 100).toFixed(1)}%
              </p>
            </div>
          </div>
        )}

        {/* History */}
        {history.length > 0 && (
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Clock className="w-5 h-5 text-white/60" />
              Recent Tuning History
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs text-white/50 font-medium py-2 px-3">Strategy</th>
                    <th className="text-left text-xs text-white/50 font-medium py-2 px-3">Combinations</th>
                    <th className="text-left text-xs text-white/50 font-medium py-2 px-3">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((item, idx) => (
                    <tr key={idx} className="border-b border-white/5">
                      <td className="py-2 px-3 text-sm text-white">{item.strategy || 'Full Optimization'}</td>
                      <td className="py-2 px-3 text-sm text-white/70">{item.total_tested || '-'}</td>
                      <td className="py-2 px-3 text-sm text-white/50">
                        {item.timestamp ? new Date(item.timestamp).toLocaleString() : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default StrategyTuning;
