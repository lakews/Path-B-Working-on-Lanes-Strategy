import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { TrendingUp, DollarSign, Activity, Target } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Dashboard = () => {
  const [performance, setPerformance] = useState(null);
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const [perfRes, posRes, tradesRes] = await Promise.all([
        axios.get(`${API}/performance`),
        axios.get(`${API}/positions`),
        axios.get(`${API}/trades?limit=20`)
      ]);
      
      setPerformance(perfRes.data);
      setPositions(posRes.data.positions);
      setTrades(tradesRes.data.trades);
      setLoading(false);
    } catch (e) {
      console.error('Error fetching data:', e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="dashboard-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  const statCards = [
    {
      title: 'Total Capital',
      value: `$${performance?.total_capital?.toFixed(2) || '0.00'}`,
      change: performance?.total_pnl >= 0 ? `+$${performance?.total_pnl?.toFixed(2)}` : `-$${Math.abs(performance?.total_pnl || 0).toFixed(2)}`,
      icon: DollarSign,
      color: 'from-green-400 to-emerald-600',
      testId: 'total-capital-card'
    },
    {
      title: 'Win Rate',
      value: `${((performance?.win_rate || 0) * 100).toFixed(1)}%`,
      change: `${performance?.num_trades || 0} trades`,
      icon: Target,
      color: 'from-blue-400 to-cyan-600',
      testId: 'win-rate-card'
    },
    {
      title: 'Sharpe Ratio',
      value: performance?.sharpe_ratio?.toFixed(2) || '0.00',
      change: `Max DD: ${((performance?.max_drawdown || 0) * 100).toFixed(1)}%`,
      icon: TrendingUp,
      color: 'from-purple-400 to-indigo-600',
      testId: 'sharpe-ratio-card'
    },
    {
      title: 'Active Positions',
      value: positions.length,
      change: `${performance?.num_trades || 0} total trades`,
      icon: Activity,
      color: 'from-orange-400 to-red-600',
      testId: 'active-positions-card'
    }
  ];

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div 
              key={idx} 
              data-testid={card.testId}
              className="relative overflow-hidden rounded-xl bg-gradient-to-br from-white/5 to-white/10 backdrop-blur-xl border border-white/10 p-6 hover:border-white/20 transition-all"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-white/60 mb-1">{card.title}</p>
                  <h3 className="text-3xl font-bold text-white mb-1">{card.value}</h3>
                  <p className="text-xs text-cyan-400">{card.change}</p>
                </div>
                <div className={`w-12 h-12 rounded-lg bg-gradient-to-br ${card.color} flex items-center justify-center`}>
                  <Icon className="w-6 h-6 text-white" />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="pnl-chart">
          <h3 className="text-lg font-semibold text-white mb-4">P&L Overview</h3>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={trades.slice(0, 10).reverse().map((t, i) => ({
              name: `T${i+1}`,
              pnl: (t.price * t.shares - t.fee)
            }))}>
              <defs>
                <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" />
              <YAxis stroke="rgba(255,255,255,0.5)" />
              <Tooltip 
                contentStyle={{backgroundColor: 'rgba(0,0,0,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px'}}
                labelStyle={{color: 'white'}}
              />
              <Area type="monotone" dataKey="pnl" stroke="#06b6d4" fillOpacity={1} fill="url(#colorPnl)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="recent-trades">
          <h3 className="text-lg font-semibold text-white mb-4">Recent Trades</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {trades.slice(0, 8).map((trade, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition" data-testid={`trade-item-${idx}`}>
                <div>
                  <p className="text-sm font-medium text-white">{trade.strategy}</p>
                  <p className="text-xs text-white/60">{trade.side} • {trade.shares.toFixed(2)} shares</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-cyan-400">${(trade.price * trade.shares).toFixed(2)}</p>
                  <p className="text-xs text-white/60">{trade.execution_latency_ms?.toFixed(1)}ms</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Open Positions */}
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
                  <th className="text-right text-sm font-medium text-white/60 pb-3">Current Price</th>
                  <th className="text-right text-sm font-medium text-white/60 pb-3">P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx} className="border-b border-white/5" data-testid={`position-row-${idx}`}>
                    <td className="py-3 text-sm text-white/80">{pos.market_id.substring(0, 12)}...</td>
                    <td className="py-3 text-sm text-cyan-400">{pos.strategy}</td>
                    <td className="py-3 text-sm text-right text-white/80">{pos.side}</td>
                    <td className="py-3 text-sm text-right text-white/80">{pos.shares.toFixed(2)}</td>
                    <td className="py-3 text-sm text-right text-white/80">${pos.avg_price.toFixed(3)}</td>
                    <td className="py-3 text-sm text-right text-white/80">${pos.current_price.toFixed(3)}</td>
                    <td className={`py-3 text-sm text-right font-semibold ${pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${pos.unrealized_pnl.toFixed(2)}
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

export default Dashboard;