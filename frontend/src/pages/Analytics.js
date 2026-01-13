import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, AreaChart, Area, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis } from 'recharts';
import { TrendingUp, TrendingDown, Target, Activity, AlertCircle, Award, Zap, Shield, PieChart as PieIcon, BarChart3, Trophy, Flame, Droplet, DollarSign } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#ec4899'];
const STRATEGY_COLORS = {
  'Delta Neutral': '#06b6d4',
  'Volatility Exploitation': '#8b5cf6',
  'Alpha Directional': '#f59e0b',
  'Arbitrage': '#10b981'
};

const Analytics = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

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
      setLoading(false);
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
      winRate: (data.win_rate * 100),
      trades: data.total_trades,
      pnl: data.total_pnl,
      classification: data.classification
    })) : [];

  const assetClassData = analytics?.asset_class_performance ?
    Object.entries(analytics.asset_class_performance).map(([name, data]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value: data.total_trades,
      winRate: (data.win_rate * 100),
      pnl: data.total_pnl
    })) : [];

  // Radar chart data for strategy comparison
  const radarData = strategyData.map(s => ({
    strategy: s.name.split(' ')[0],
    winRate: s.winRate,
    trades: Math.min(s.trades * 10, 100),
    pnl: Math.max(Math.min((s.pnl + 50) * 2, 100), 0)
  }));

  const winRate = (analytics?.overall_win_rate || 0) * 100;
  const totalPnL = analytics?.realized_pnl || 0;

  return (
    <div className="space-y-6" data-testid="analytics-page">
      
      {/* Page Header with Tabs */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Performance Analytics</h1>
          <p className="text-white/60 text-sm mt-1">Comprehensive trading performance analysis</p>
        </div>
        
        {/* Tab Navigation */}
        <div className="flex gap-2 bg-white/5 p-1 rounded-xl">
          {['overview', 'strategies', 'assets'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab 
                  ? 'bg-cyan-500 text-white' 
                  : 'text-white/60 hover:text-white hover:bg-white/10'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Hero Stats Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Win Rate Hero */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-500/30 p-6">
          <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 rounded-full -mr-16 -mt-16" />
          <div className="relative">
            <div className="flex items-center gap-2 mb-3">
              <Target className="w-5 h-5 text-cyan-400" />
              <span className="text-sm text-cyan-400 font-medium">Win Rate</span>
            </div>
            <div className="flex items-end gap-2">
              <span className="text-5xl font-bold text-white">{winRate.toFixed(1)}</span>
              <span className="text-2xl text-white/60 mb-1">%</span>
            </div>
            <div className="mt-3 flex items-center gap-4 text-sm">
              <span className="text-green-400">{analytics?.winning_trades || 0} wins</span>
              <span className="text-white/30">•</span>
              <span className="text-red-400">{analytics?.losing_trades || 0} losses</span>
            </div>
          </div>
        </div>

        {/* Total P&L Hero */}
        <div className={`relative overflow-hidden rounded-2xl border p-6 ${
          totalPnL >= 0 
            ? 'bg-gradient-to-br from-green-500/20 to-emerald-600/20 border-green-500/30'
            : 'bg-gradient-to-br from-red-500/20 to-rose-600/20 border-red-500/30'
        }`}>
          <div className={`absolute top-0 right-0 w-32 h-32 rounded-full -mr-16 -mt-16 ${
            totalPnL >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'
          }`} />
          <div className="relative">
            <div className="flex items-center gap-2 mb-3">
              <DollarSign className={`w-5 h-5 ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`} />
              <span className={`text-sm font-medium ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>Total P&L</span>
            </div>
            <div className="flex items-end gap-2">
              <span className={`text-5xl font-bold ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {totalPnL >= 0 ? '+' : ''}{totalPnL.toFixed(2)}
              </span>
              <span className="text-xl text-white/60 mb-1">USD</span>
            </div>
            <div className="mt-3 flex items-center gap-4 text-sm">
              <span className="text-white/60">Unrealized: ${(analytics?.unrealized_pnl || 0).toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Sharpe Ratio Hero */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-purple-500/20 to-indigo-600/20 border border-purple-500/30 p-6">
          <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 rounded-full -mr-16 -mt-16" />
          <div className="relative">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp className="w-5 h-5 text-purple-400" />
              <span className="text-sm text-purple-400 font-medium">Sharpe Ratio</span>
            </div>
            <div className="flex items-end gap-2">
              <span className="text-5xl font-bold text-white">{(analytics?.sharpe_ratio || 0).toFixed(2)}</span>
            </div>
            <div className="mt-3 text-sm">
              <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                (analytics?.sharpe_ratio || 0) >= 2 ? 'bg-green-500/20 text-green-400' :
                (analytics?.sharpe_ratio || 0) >= 1 ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}>
                {(analytics?.sharpe_ratio || 0) >= 2 ? 'Excellent' : (analytics?.sharpe_ratio || 0) >= 1 ? 'Good' : 'Needs Improvement'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Overview Tab Content */}
      {activeTab === 'overview' && (
        <>
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <MetricCard icon={Activity} label="Profit Factor" value={(analytics?.profit_factor || 0).toFixed(2)} color="green" />
            <MetricCard icon={TrendingUp} label="Sortino" value={(analytics?.sortino_ratio || 0).toFixed(2)} color="purple" />
            <MetricCard icon={Target} label="Expectancy" value={`$${(analytics?.expectancy || 0).toFixed(2)}`} color="cyan" />
            <MetricCard icon={Shield} label="Max Drawdown" value={`${((analytics?.max_drawdown || 0) * 100).toFixed(1)}%`} color="red" />
            <MetricCard icon={Zap} label="Win/Loss" value={(analytics?.win_loss_ratio || 0).toFixed(2)} color="orange" />
            <MetricCard icon={Award} label="Recovery" value={(analytics?.recovery_factor || 0).toFixed(2)} color="blue" />
          </div>

          {/* Streaks & Averages */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="rounded-xl bg-gradient-to-br from-green-500/10 to-green-600/5 border border-green-500/20 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-green-400/80 uppercase tracking-wide">Win Streak</p>
                  <p className="text-3xl font-bold text-green-400 mt-1">{analytics?.max_consecutive_wins || 0}</p>
                </div>
                <Trophy className="w-10 h-10 text-green-500/30" />
              </div>
            </div>
            
            <div className="rounded-xl bg-gradient-to-br from-red-500/10 to-red-600/5 border border-red-500/20 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-red-400/80 uppercase tracking-wide">Loss Streak</p>
                  <p className="text-3xl font-bold text-red-400 mt-1">{analytics?.max_consecutive_losses || 0}</p>
                </div>
                <Flame className="w-10 h-10 text-red-500/30" />
              </div>
            </div>

            <div className="rounded-xl bg-white/5 border border-white/10 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-white/60 uppercase tracking-wide">Avg Win</p>
                  <p className="text-3xl font-bold text-green-400 mt-1">${(analytics?.avg_win || 0).toFixed(2)}</p>
                </div>
                <TrendingUp className="w-10 h-10 text-green-500/30" />
              </div>
            </div>

            <div className="rounded-xl bg-white/5 border border-white/10 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-white/60 uppercase tracking-wide">Avg Loss</p>
                  <p className="text-3xl font-bold text-red-400 mt-1">${(analytics?.avg_loss || 0).toFixed(2)}</p>
                </div>
                <TrendingDown className="w-10 h-10 text-red-500/30" />
              </div>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Strategy Comparison Radar */}
            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Strategy Comparison</h3>
              {strategyData.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="rgba(255,255,255,0.1)" />
                    <PolarAngleAxis dataKey="strategy" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 12 }} />
                    <PolarRadiusAxis stroke="rgba(255,255,255,0.2)" />
                    <Radar name="Win Rate" dataKey="winRate" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.3} />
                  </RadarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-64 flex items-center justify-center text-white/40">No strategy data yet</div>
              )}
            </div>

            {/* Asset Distribution */}
            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Asset Class Distribution</h3>
              {assetClassData.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={assetClassData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={2}
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
                      formatter={(value, name) => [`${value} trades`, name]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-64 flex items-center justify-center text-white/40">No asset data yet</div>
              )}
              {/* Legend */}
              <div className="flex flex-wrap justify-center gap-4 mt-4">
                {assetClassData.map((item, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }} />
                    <span className="text-xs text-white/60">{item.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Strategies Tab Content */}
      {activeTab === 'strategies' && (
        <>
          {/* Strategy Performance Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {strategyData.length > 0 ? strategyData.map((strategy, idx) => (
              <div key={idx} className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6 hover:border-white/20 transition-all" data-testid={`strategy-card-${idx}`}>
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{strategy.name}</h3>
                    <span className={`inline-block mt-1 px-2 py-1 rounded text-xs font-medium ${
                      strategy.classification === 'Excellent' ? 'bg-green-500/20 text-green-400' :
                      strategy.classification === 'Good' ? 'bg-blue-500/20 text-blue-400' :
                      strategy.classification === 'Moderate' ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-red-500/20 text-red-400'
                    }`}>
                      {strategy.classification || 'N/A'}
                    </span>
                  </div>
                  <div className={`text-2xl font-bold ${strategy.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {strategy.pnl >= 0 ? '+' : ''}${strategy.pnl.toFixed(2)}
                  </div>
                </div>
                
                {/* Win Rate Progress Bar */}
                <div className="mb-4">
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-white/60">Win Rate</span>
                    <span className="text-cyan-400 font-medium">{strategy.winRate.toFixed(1)}%</span>
                  </div>
                  <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all"
                      style={{ width: `${Math.min(strategy.winRate, 100)}%` }}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between text-sm text-white/60">
                  <span>{strategy.trades} total trades</span>
                  <span>Avg: ${strategy.trades > 0 ? (strategy.pnl / strategy.trades).toFixed(2) : '0.00'}/trade</span>
                </div>
              </div>
            )) : (
              <div className="col-span-2 text-center py-16 text-white/40">
                No strategy performance data available yet. Start trading to see analytics.
              </div>
            )}
          </div>

          {/* Strategy Bar Chart */}
          {strategyData.length > 0 && (
            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-6">Win Rate by Strategy</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={strategyData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} stroke="rgba(255,255,255,0.5)" />
                  <YAxis dataKey="name" type="category" stroke="rgba(255,255,255,0.5)" width={150} />
                  <Tooltip 
                    contentStyle={{
                      backgroundColor: 'rgba(0,0,0,0.9)', 
                      border: '1px solid rgba(255,255,255,0.1)', 
                      borderRadius: '8px'
                    }}
                    formatter={(value) => [`${value.toFixed(1)}%`, 'Win Rate']}
                  />
                  <Bar dataKey="winRate" fill="#06b6d4" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      {/* Assets Tab Content */}
      {activeTab === 'assets' && (
        <>
          {/* Asset Class Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {assetClassData.length > 0 ? assetClassData.map((asset, idx) => (
              <div key={idx} className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-5 hover:border-white/20 transition-all" data-testid={`asset-card-${idx}`}>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${COLORS[idx % COLORS.length]}20` }}>
                    <PieIcon className="w-5 h-5" style={{ color: COLORS[idx % COLORS.length] }} />
                  </div>
                  <div>
                    <h3 className="text-white font-semibold">{asset.name}</h3>
                    <p className="text-xs text-white/40">{asset.value} trades</p>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-white/60">Win Rate</span>
                    <span className={`font-semibold ${asset.winRate >= 60 ? 'text-green-400' : asset.winRate >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                      {asset.winRate.toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                    <div 
                      className="h-full rounded-full transition-all"
                      style={{ 
                        width: `${Math.min(asset.winRate, 100)}%`,
                        backgroundColor: COLORS[idx % COLORS.length]
                      }}
                    />
                  </div>
                  <div className="flex justify-between items-center pt-2 border-t border-white/10">
                    <span className="text-sm text-white/60">P&L</span>
                    <span className={`font-bold ${asset.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {asset.pnl >= 0 ? '+' : ''}${asset.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>
            )) : (
              <div className="col-span-3 text-center py-16 text-white/40">
                No asset class data available yet. Start trading to see analytics.
              </div>
            )}
          </div>

          {/* Asset Performance Chart */}
          {assetClassData.length > 0 && (
            <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-6">P&L by Asset Class</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={assetClassData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" />
                  <YAxis stroke="rgba(255,255,255,0.5)" />
                  <Tooltip 
                    contentStyle={{
                      backgroundColor: 'rgba(0,0,0,0.9)', 
                      border: '1px solid rgba(255,255,255,0.1)', 
                      borderRadius: '8px'
                    }}
                    formatter={(value) => [`$${value.toFixed(2)}`, 'P&L']}
                  />
                  <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                    {assetClassData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#10b981' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      {/* Bottom Stats Bar */}
      <div className="rounded-xl bg-gradient-to-r from-slate-800/50 to-slate-900/50 border border-white/10 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <div className="text-center">
              <p className="text-xs text-white/40 uppercase">Total Trades</p>
              <p className="text-xl font-bold text-white">{analytics?.total_trades || 0}</p>
            </div>
            <div className="w-px h-8 bg-white/10" />
            <div className="text-center">
              <p className="text-xs text-white/40 uppercase">Volatility</p>
              <p className="text-xl font-bold text-purple-400">{((analytics?.portfolio_volatility || 0) * 100).toFixed(1)}%</p>
            </div>
            <div className="w-px h-8 bg-white/10" />
            <div className="text-center">
              <p className="text-xs text-white/40 uppercase">Calmar Ratio</p>
              <p className="text-xl font-bold text-cyan-400">{(analytics?.calmar_ratio || 0).toFixed(2)}</p>
            </div>
          </div>
          <div className="text-xs text-white/40">
            Last updated: {new Date(analytics?.timestamp || Date.now()).toLocaleTimeString()}
          </div>
        </div>
      </div>
    </div>
  );
};

// Metric Card Component
const MetricCard = ({ icon: Icon, label, value, color }) => {
  const colorMap = {
    green: 'text-green-400',
    purple: 'text-purple-400',
    cyan: 'text-cyan-400',
    red: 'text-red-400',
    orange: 'text-orange-400',
    blue: 'text-blue-400'
  };

  return (
    <div className="rounded-xl bg-white/5 border border-white/10 p-4 hover:bg-white/10 transition-all">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${colorMap[color]}`} />
        <span className="text-xs text-white/50 uppercase tracking-wide">{label}</span>
      </div>
      <p className={`text-xl font-bold ${colorMap[color]}`}>{value}</p>
    </div>
  );
};

export default Analytics;
