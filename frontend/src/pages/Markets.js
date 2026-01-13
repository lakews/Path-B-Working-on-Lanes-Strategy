import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Search, TrendingUp, TrendingDown } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Markets = () => {
  const [markets, setMarkets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    fetchMarkets();
    const interval = setInterval(fetchMarkets, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchMarkets = async () => {
    try {
      const response = await axios.get(`${API}/markets?limit=100`);
      setMarkets(response.data.markets);
      setLoading(false);
    } catch (e) {
      console.error('Error fetching markets:', e);
    }
  };

  const filteredMarkets = markets.filter(m => 
    m.question?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    m.category?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="markets-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="markets-page">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Active Markets</h2>
        <div className="relative w-96">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-white/40" />
          <input
            type="text"
            placeholder="Search markets..."
            data-testid="market-search-input"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-white/40 focus:outline-none focus:border-cyan-500 transition"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredMarkets.map((market, idx) => (
          <div 
            key={idx} 
            data-testid={`market-card-${idx}`}
            className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-5 hover:border-white/20 hover:bg-white/10 transition-all cursor-pointer"
          >
            <div className="flex items-start justify-between mb-3">
              <span className="px-2 py-1 rounded text-xs font-medium bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
                {market.category}
              </span>
              <div className="flex items-center gap-2">
                {market.yes_price > 0.5 ? (
                  <TrendingUp className="w-4 h-4 text-green-400" />
                ) : (
                  <TrendingDown className="w-4 h-4 text-red-400" />
                )}
              </div>
            </div>

            <h3 className="text-sm font-semibold text-white mb-3 line-clamp-2 min-h-[40px]">
              {market.question}
            </h3>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-white/60">YES Price</span>
                <span className="text-sm font-semibold text-green-400">${market.yes_price?.toFixed(3)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-white/60">NO Price</span>
                <span className="text-sm font-semibold text-red-400">${market.no_price?.toFixed(3)}</span>
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-white/10">
                <span className="text-xs text-white/60">Volume</span>
                <span className="text-sm font-medium text-white">${(market.volume || 0).toFixed(0)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-white/60">Liquidity</span>
                <span className="text-sm font-medium text-white">${(market.liquidity || 0).toFixed(0)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {filteredMarkets.length === 0 && (
        <div className="text-center py-16" data-testid="no-markets-message">
          <p className="text-white/60">No markets found</p>
        </div>
      )}
    </div>
  );
};

export default Markets;