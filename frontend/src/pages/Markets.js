import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Search, TrendingUp, TrendingDown, Filter, RefreshCw, Clock, DollarSign, Droplet, BarChart3, Zap, PieChart } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const CATEGORY_COLORS = {
  sports: { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/30' },
  finance: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
  politics: { bg: 'bg-purple-500/20', text: 'text-purple-400', border: 'border-purple-500/30' },
  crypto: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/30' },
  entertainment: { bg: 'bg-pink-500/20', text: 'text-pink-400', border: 'border-pink-500/30' }
};

const Markets = () => {
  const [markets, setMarkets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [sortBy, setSortBy] = useState('volume');
  const [dataSource, setDataSource] = useState('');

  useEffect(() => {
    fetchMarkets();
    const interval = setInterval(fetchMarkets, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchMarkets = async () => {
    try {
      setRefreshing(true);
      const response = await axios.get(`${API}/markets?limit=100`);
      setMarkets(response.data.markets || []);
      setDataSource(response.data.source || 'unknown');
      setLoading(false);
      setRefreshing(false);
    } catch (e) {
      console.error('Error fetching markets:', e);
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Get unique categories
  const categories = ['all', ...new Set(markets.map(m => m.category).filter(Boolean))];

  // Calculate category stats
  const categoryStats = markets.reduce((acc, m) => {
    const cat = m.category || 'other';
    if (!acc[cat]) acc[cat] = { count: 0, volume: 0 };
    acc[cat].count++;
    acc[cat].volume += m.volume || 0;
    return acc;
  }, {});

  // Filter and sort markets
  const filteredMarkets = markets
    .filter(m => {
      const matchesSearch = m.question?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        m.category?.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCategory = selectedCategory === 'all' || m.category === selectedCategory;
      return matchesSearch && matchesCategory;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'volume': return (b.volume || 0) - (a.volume || 0);
        case 'liquidity': return (b.liquidity || 0) - (a.liquidity || 0);
        case 'price_high': return (b.yes_price || 0) - (a.yes_price || 0);
        case 'price_low': return (a.yes_price || 0) - (b.yes_price || 0);
        default: return 0;
      }
    });

  // Total stats
  const totalVolume = markets.reduce((sum, m) => sum + (m.volume || 0), 0);
  const totalLiquidity = markets.reduce((sum, m) => sum + (m.liquidity || 0), 0);
  const avgPrice = markets.length > 0 ? 
    markets.reduce((sum, m) => sum + (m.yes_price || 0.5), 0) / markets.length : 0.5;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="markets-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="markets-page">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Active Markets</h1>
          <p className="text-white/60 text-sm mt-1">
            {markets.length} markets from <span className="text-cyan-400">{dataSource === 'polymarket_api' ? 'Polymarket Live' : 'Historical Data'}</span>
          </p>
        </div>
        
        <button 
          onClick={fetchMarkets}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-4 h-4 text-cyan-400" />
            <span className="text-xs text-white/60 uppercase">Total Volume</span>
          </div>
          <p className="text-xl font-bold text-white">${(totalVolume / 1000000).toFixed(2)}M</p>
        </div>
        
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Droplet className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-white/60 uppercase">Total Liquidity</span>
          </div>
          <p className="text-xl font-bold text-white">${(totalLiquidity / 1000000).toFixed(2)}M</p>
        </div>
        
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <PieChart className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-white/60 uppercase">Avg YES Price</span>
          </div>
          <p className="text-xl font-bold text-white">${avgPrice.toFixed(3)}</p>
        </div>
        
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-yellow-400" />
            <span className="text-xs text-white/60 uppercase">Categories</span>
          </div>
          <p className="text-xl font-bold text-white">{Object.keys(categoryStats).length}</p>
        </div>
      </div>

      {/* Category Pills */}
      <div className="flex flex-wrap gap-2">
        {categories.map(cat => {
          const colors = CATEGORY_COLORS[cat] || { bg: 'bg-white/10', text: 'text-white', border: 'border-white/20' };
          const stats = categoryStats[cat];
          const isSelected = selectedCategory === cat;
          
          return (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                isSelected 
                  ? `${colors.bg} ${colors.text} ${colors.border} border scale-105`
                  : 'bg-white/5 text-white/60 border border-white/10 hover:bg-white/10'
              }`}
            >
              {cat === 'all' ? 'All' : cat.charAt(0).toUpperCase() + cat.slice(1)}
              {cat !== 'all' && stats && (
                <span className="ml-2 text-xs opacity-60">({stats.count})</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Search & Sort */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-white/40" />
          <input
            type="text"
            placeholder="Search markets..."
            data-testid="market-search-input"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/40 focus:outline-none focus:border-cyan-500 transition"
          />
        </div>
        
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white focus:outline-none focus:border-cyan-500"
        >
          <option value="volume">Sort by Volume</option>
          <option value="liquidity">Sort by Liquidity</option>
          <option value="price_high">Price: High to Low</option>
          <option value="price_low">Price: Low to High</option>
        </select>
      </div>

      {/* Markets Grid */}
      {filteredMarkets.length === 0 ? (
        <div className="text-center py-16 rounded-xl bg-white/5 border border-white/10" data-testid="no-markets-message">
          <Search className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <p className="text-white/60 text-lg">No markets found</p>
          <p className="text-white/40 text-sm mt-2">Try adjusting your search or filters</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredMarkets.map((market, idx) => {
            const colors = CATEGORY_COLORS[market.category] || CATEGORY_COLORS.finance;
            const yesPrice = market.yes_price || 0.5;
            const noPrice = market.no_price || 0.5;
            const isYesFavored = yesPrice > 0.5;
            const spread = Math.abs(yesPrice - noPrice);
            
            return (
              <div 
                key={idx} 
                data-testid={`market-card-${idx}`}
                className="group rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-5 hover:border-cyan-500/50 hover:bg-white/10 transition-all cursor-pointer"
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${colors.bg} ${colors.text} border ${colors.border}`}>
                    {market.category || 'Other'}
                  </span>
                  <div className="flex items-center gap-1">
                    {isYesFavored ? (
                      <TrendingUp className="w-4 h-4 text-green-400" />
                    ) : (
                      <TrendingDown className="w-4 h-4 text-red-400" />
                    )}
                    <span className={`text-xs font-medium ${isYesFavored ? 'text-green-400' : 'text-red-400'}`}>
                      {(yesPrice * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                {/* Question */}
                <h3 className="text-sm font-semibold text-white mb-4 line-clamp-2 min-h-[40px] group-hover:text-cyan-400 transition">
                  {market.question || 'Unknown Market'}
                </h3>

                {/* Price Visualization */}
                <div className="mb-4">
                  <div className="flex justify-between text-xs text-white/60 mb-1">
                    <span>YES ${yesPrice.toFixed(3)}</span>
                    <span>NO ${noPrice.toFixed(3)}</span>
                  </div>
                  <div className="h-2 bg-white/10 rounded-full overflow-hidden flex">
                    <div 
                      className="h-full bg-gradient-to-r from-green-500 to-green-400 transition-all"
                      style={{ width: `${yesPrice * 100}%` }}
                    />
                    <div 
                      className="h-full bg-gradient-to-r from-red-400 to-red-500 transition-all"
                      style={{ width: `${noPrice * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-center mt-1">
                    <span className="text-xs text-white/40">Spread: {(spread * 100).toFixed(1)}%</span>
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-3 pt-3 border-t border-white/10">
                  <div>
                    <p className="text-xs text-white/50 mb-1">Volume</p>
                    <p className="text-sm font-semibold text-white">
                      ${market.volume >= 1000000 
                        ? `${(market.volume / 1000000).toFixed(2)}M` 
                        : market.volume >= 1000 
                          ? `${(market.volume / 1000).toFixed(1)}K`
                          : market.volume?.toFixed(0) || '0'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-white/50 mb-1">Liquidity</p>
                    <p className="text-sm font-semibold text-white">
                      ${market.liquidity >= 1000000 
                        ? `${(market.liquidity / 1000000).toFixed(2)}M` 
                        : market.liquidity >= 1000 
                          ? `${(market.liquidity / 1000).toFixed(1)}K`
                          : market.liquidity?.toFixed(0) || '0'}
                    </p>
                  </div>
                </div>

                {/* End Date */}
                {market.end_date && (
                  <div className="mt-3 pt-3 border-t border-white/10 flex items-center gap-2 text-xs text-white/40">
                    <Clock className="w-3 h-3" />
                    <span>Ends {new Date(market.end_date).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Bottom Info Bar */}
      <div className="rounded-xl bg-gradient-to-r from-slate-800/50 to-slate-900/50 border border-white/10 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4 text-sm text-white/60">
            <span>Showing {filteredMarkets.length} of {markets.length} markets</span>
            <span className="text-white/20">•</span>
            <span>Data from: <span className="text-cyan-400">{dataSource === 'polymarket_api' ? 'Polymarket API' : 'Historical Cache'}</span></span>
          </div>
          <div className="text-xs text-white/40">
            Auto-refreshes every 30s
          </div>
        </div>
      </div>
    </div>
  );
};

export default Markets;
