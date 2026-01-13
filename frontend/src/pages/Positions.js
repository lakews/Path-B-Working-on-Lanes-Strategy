import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { X } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Positions = () => {
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchPositions = async () => {
    try {
      const response = await axios.get(`${API}/positions`);
      setPositions(response.data.positions);
      setLoading(false);
    } catch (e) {
      console.error('Error fetching positions:', e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="positions-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  const totalUnrealizedPnL = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0);
  const totalValue = positions.reduce((sum, p) => sum + (p.shares * p.current_price), 0);

  return (
    <div className="space-y-6" data-testid="positions-page">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Open Positions</h2>
          <p className="text-white/60 text-sm mt-1">{positions.length} active position{positions.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="flex gap-4">
          <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 px-6 py-3">
            <p className="text-xs text-white/60 mb-1">Total Position Value</p>
            <p className="text-xl font-bold text-white">${totalValue.toFixed(2)}</p>
          </div>
          <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 px-6 py-3">
            <p className="text-xs text-white/60 mb-1">Unrealized P&L</p>
            <p className={`text-xl font-bold ${totalUnrealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {totalUnrealizedPnL >= 0 ? '+' : ''}${totalUnrealizedPnL.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-16 text-center" data-testid="no-positions-message">
          <X className="w-16 h-16 text-white/20 mx-auto mb-4" />
          <p className="text-white/60 text-lg">No open positions</p>
          <p className="text-white/40 text-sm mt-2">Start the trading bot to open positions</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {positions.map((position, idx) => {
            const pnlPct = ((position.current_price - position.avg_price) / position.avg_price * 100);
            const isProfit = position.unrealized_pnl >= 0;

            return (
              <div 
                key={idx} 
                data-testid={`position-card-${idx}`}
                className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6 hover:border-white/20 transition"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="px-2 py-1 rounded text-xs font-medium bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
                        {position.strategy}
                      </span>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        position.side === 'BUY' 
                          ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                          : 'bg-red-500/20 text-red-400 border border-red-500/30'
                      }`}>
                        {position.side}
                      </span>
                    </div>
                    <p className="text-sm text-white/60 font-mono">{position.market_id}</p>
                  </div>
                  <div className="text-right">
                    <p className={`text-2xl font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                      {isProfit ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
                    </p>
                    <p className={`text-sm ${isProfit ? 'text-green-400/60' : 'text-red-400/60'}`}>
                      {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/10">
                  <div>
                    <p className="text-xs text-white/60 mb-1">Shares</p>
                    <p className="text-sm font-semibold text-white">{position.shares.toFixed(4)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-white/60 mb-1">Entry Price</p>
                    <p className="text-sm font-semibold text-white">${position.avg_price.toFixed(4)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-white/60 mb-1">Current Price</p>
                    <p className="text-sm font-semibold text-white">${position.current_price.toFixed(4)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-white/60 mb-1">Position Value</p>
                    <p className="text-sm font-semibold text-white">${(position.shares * position.current_price).toFixed(2)}</p>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-white/10">
                  <p className="text-xs text-white/40">Opened: {new Date(position.opened_at).toLocaleString()}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Positions;