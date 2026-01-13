import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';
import { TrendingUp, Target, Activity, AlertCircle } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#ec4899'];

const Analytics = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
    const interval = setInterval(fetchAnalytics, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchAnalytics = async () => {
    try {
      const response = await axios.get(`${API}/analytics`);
      setAnalytics(response.data);
      setLoading(false);
    } catch (e) {
      console.error('Error fetching analytics:', e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="analytics-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  const strategyData = analytics?.strategy_performance ? 
    Object.entries(analytics.strategy_performance).map(([name, data]) => ({
      name: name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      winRate: (data.win_rate * 100).toFixed(1),
      trades: data.total_trades,
      pnl: data.total_pnl,
      classification: data.classification
    })) : [];

  const assetClassData = analytics?.asset_class_performance ?
    Object.entries(analytics.asset_class_performance).map(([name, data]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value: data.total_trades,
      winRate: (data.win_rate * 100).toFixed(1),
      pnl: data.total_pnl
    })) : [];

  return (
    <div className="space-y-6" data-testid="analytics-page">
      {/* Header Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="overall-win-rate-card">
          <div className="flex items-center gap-3 mb-2">
            <Target className="w-8 h-8 text-cyan-400" />
            <h3 className="text-sm text-white/60">Overall Win Rate</h3>
          </div>
          <p className="text-3xl font-bold text-white">
            {((analytics?.overall_win_rate || 0) * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-cyan-400 mt-1">
            {analytics?.winning_trades || 0}W / {analytics?.losing_trades || 0}L
          </p>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="sortino-ratio-card">
          <div className="flex items-center gap-3 mb-2">
            <TrendingUp className="w-8 h-8 text-purple-400" />
            <h3 className="text-sm text-white/60">Sortino Ratio</h3>
          </div>
          <p className="text-3xl font-bold text-white">
            {(analytics?.sortino_ratio || 0).toFixed(2)}
          </p>
          <p className="text-xs text-purple-400 mt-1">Downside risk-adjusted</p>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="profit-factor-card">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="w-8 h-8 text-green-400" />
            <h3 className="text-sm text-white/60">Profit Factor</h3>
          </div>
          <p className="text-3xl font-bold text-white">
            {(analytics?.profit_factor || 0).toFixed(2)}
          </p>
          <p className="text-xs text-green-400 mt-1">{(analytics?.profit_factor || 0) > 1.5 ? 'Excellent' : 'Target: >1.5'}</p>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="expectancy-card">
          <div className="flex items-center gap-3 mb-2">
            <AlertCircle className="w-8 h-8 text-orange-400" />
            <h3 className="text-sm text-white/60">Expectancy</h3>
          </div>
          <p className={`text-3xl font-bold ${(analytics?.expectancy || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${(analytics?.expectancy || 0).toFixed(2)}
          </p>
          <p className="text-xs text-orange-400 mt-1">Per trade average</p>
        </div>
      </div>

      {/* Additional Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-4">
          <h3 className="text-xs text-white/60 mb-1">Win/Loss Ratio</h3>
          <p className="text-2xl font-bold text-white">{(analytics?.win_loss_ratio || 0).toFixed(2)}</p>
          <p className="text-xs text-cyan-400 mt-1">Avg win / Avg loss</p>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-4">
          <h3 className="text-xs text-white/60 mb-1">Recovery Factor</h3>
          <p className="text-2xl font-bold text-white">{(analytics?.recovery_factor || 0).toFixed(2)}</p>
          <p className="text-xs text-purple-400 mt-1">Profit / Max DD</p>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-4">
          <h3 className="text-xs text-white/60 mb-1">Avg Win</h3>
          <p className="text-2xl font-bold text-green-400">${(analytics?.avg_win || 0).toFixed(2)}</p>
          <p className="text-xs text-green-400/60 mt-1">Per winning trade</p>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-4">
          <h3 className="text-xs text-white/60 mb-1">Avg Loss</h3>
          <p className="text-2xl font-bold text-red-400">${(analytics?.avg_loss || 0).toFixed(2)}</p>
          <p className="text-xs text-red-400/60 mt-1">Per losing trade</p>
        </div>
      </div>

      {/* Streaks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="rounded-xl bg-gradient-to-br from-green-500/10 to-green-500/5 border border-green-500/20 p-6">
          <h3 className="text-sm text-green-400 mb-2 font-semibold">Max Winning Streak</h3>
          <p className="text-4xl font-bold text-green-400">{analytics?.max_consecutive_wins || 0}</p>
          <p className="text-xs text-green-400/60 mt-2">Consecutive profitable trades</p>
        </div>

        <div className="rounded-xl bg-gradient-to-br from-red-500/10 to-red-500/5 border border-red-500/20 p-6">
          <h3 className="text-sm text-red-400 mb-2 font-semibold">Max Losing Streak</h3>
          <p className="text-4xl font-bold text-red-400">{analytics?.max_consecutive_losses || 0}</p>
          <p className="text-xs text-red-400/60 mt-2">Consecutive losing trades</p>
        </div>
      </div>

      {/* Original Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
          <h3 className="text-lg font-semibold text-white mb-2">Portfolio Volatility</h3>
          <p className="text-4xl font-bold text-purple-400">{((analytics?.portfolio_volatility || 0) * 100).toFixed(2)}%</p>
          <p className="text-sm text-white/60 mt-2">Annualized standard deviation</p>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
          <h3 className="text-lg font-semibold text-white mb-2">Total Performance</h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-white/60">Total Trades:</span>
              <span className="text-white font-semibold">{analytics?.total_trades || 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/60">Realized P&L:</span>
              <span className={`font-semibold ${(analytics?.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${(analytics?.realized_pnl || 0).toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/60">Unrealized P&L:</span>
              <span className={`font-semibold ${(analytics?.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${(analytics?.unrealized_pnl || 0).toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Strategy Performance */}
      <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="strategy-performance-section">
        <h3 className="text-xl font-semibold text-white mb-6">Performance by Strategy</h3>
        
        {strategyData.length > 0 ? (
          <>
            <div className="mb-6">
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={strategyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" />
                  <YAxis stroke="rgba(255,255,255,0.5)" />
                  <Tooltip 
                    contentStyle={{
                      backgroundColor: 'rgba(0,0,0,0.9)', 
                      border: '1px solid rgba(255,255,255,0.1)', 
                      borderRadius: '8px'
                    }}
                  />
                  <Bar dataKey="winRate" fill="#06b6d4" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-sm font-medium text-white/60 pb-3">Strategy</th>
                    <th className="text-right text-sm font-medium text-white/60 pb-3">Trades</th>
                    <th className="text-right text-sm font-medium text-white/60 pb-3">Win Rate</th>
                    <th className="text-right text-sm font-medium text-white/60 pb-3">P&L</th>
                    <th className="text-right text-sm font-medium text-white/60 pb-3">Classification</th>
                  </tr>
                </thead>
                <tbody>
                  {strategyData.map((strategy, idx) => (
                    <tr key={idx} className="border-b border-white/5" data-testid={`strategy-row-${idx}`}>
                      <td className="py-3 text-sm text-white">{strategy.name}</td>
                      <td className="py-3 text-sm text-right text-white/80">{strategy.trades}</td>
                      <td className="py-3 text-sm text-right">
                        <span className={`font-semibold ${parseFloat(strategy.winRate) >= 70 ? 'text-green-400' : 'text-yellow-400'}`}>
                          {strategy.winRate}%
                        </span>
                      </td>
                      <td className={`py-3 text-sm text-right font-semibold ${strategy.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${strategy.pnl.toFixed(2)}
                      </td>
                      <td className="py-3 text-sm text-right">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          strategy.classification === 'Excellent' ? 'bg-green-500/20 text-green-400' :
                          strategy.classification === 'Good' ? 'bg-blue-500/20 text-blue-400' :
                          strategy.classification === 'Moderate' ? 'bg-yellow-500/20 text-yellow-400' :
                          'bg-red-500/20 text-red-400'
                        }`}>
                          {strategy.classification}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="text-center text-white/60 py-8">No strategy data available yet</p>
        )}
      </div>

      {/* Asset Class Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="asset-class-distribution">
          <h3 className="text-lg font-semibold text-white mb-4">Asset Class Distribution</h3>
          {assetClassData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={assetClassData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {assetClassData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{
                    backgroundColor: 'rgba(0,0,0,0.9)', 
                    border: '1px solid rgba(255,255,255,0.1)', 
                    borderRadius: '8px'
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-center text-white/60 py-16">No data available</p>
          )}
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="asset-class-performance">
          <h3 className="text-lg font-semibold text-white mb-4">Asset Class Performance</h3>
          {assetClassData.length > 0 ? (
            <div className="space-y-3">
              {assetClassData.map((asset, idx) => (
                <div key={idx} className="p-4 rounded-lg bg-white/5" data-testid={`asset-class-${idx}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white font-medium">{asset.name}</span>
                    <span className={`text-sm font-semibold ${parseFloat(asset.winRate) >= 60 ? 'text-green-400' : 'text-yellow-400'}`}>
                      {asset.winRate}% Win Rate
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-white/60">{asset.value} trades</span>
                    <span className={`font-semibold ${asset.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${asset.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-white/60 py-16">No data available</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Analytics;
