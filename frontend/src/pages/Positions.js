import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { AreaChart, Area, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { 
  X, TrendingUp, TrendingDown, DollarSign, Target, Shield, 
  Clock, Activity, Layers, AlertTriangle, ChevronDown, ChevronUp,
  Briefcase, PieChart as PieIcon, BarChart3, Percent, Zap, Timer,
  Wifi, WifiOff
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const COLORS = ['#06b6d4', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#ec4899'];
const STRATEGY_COLORS = {
  'delta_neutral': '#06b6d4',
  'volatility_exploitation': '#8b5cf6',
  'alpha_directional': '#f59e0b',
  'arbitrage': '#10b981'
};

// All available strategies and asset classes (Current Architecture)
const ALL_STRATEGIES = [
  { value: 'hft_maker', label: 'HFT Market Making', shortLabel: 'HFT-MM', color: '#06b6d4' },
  { value: 'hft_gamma_scalp', label: 'HFT Gamma Scalp', shortLabel: 'HFT-G', color: '#f59e0b' },
  { value: 'alpha_directional', label: 'Alpha Directional', shortLabel: 'Alpha', color: '#10b981' },
  { value: 'gamma_scalp', label: 'Gamma (Whale Zone)', shortLabel: 'Gamma', color: '#8b5cf6' },
  { value: 'sports_arbitrage', label: 'Sports Arbitrage', shortLabel: 'Sports', color: '#ec4899' },
  { value: 'delta_neutral', label: 'Delta-Neutral', shortLabel: 'Delta', color: '#64748b' }
];

const ALL_ASSET_CLASSES = [
  { value: 'politics', label: 'Politics', color: '#ef4444' },
  { value: 'crypto', label: 'Crypto', color: '#f59e0b' },
  { value: 'finance', label: 'Finance', color: '#10b981' },
  { value: 'entertainment', label: 'Entertainment', color: '#ec4899' },
  { value: 'science', label: 'Science', color: '#06b6d4' },
  { value: 'sports', label: 'Sports', color: '#8b5cf6' }
];

// ============================================================================
// POLYMORPHIC DATA HELPERS (Task: Hybrid Data Visualization)
// ============================================================================
// Sports markets use probability-based data (fair_value, edge)
// Sentiment markets use sentiment-based data (sentiment_score, llm_explanation)

const isSportsPosition = (position) => {
  const category = (position.category || position.asset_class || '').toLowerCase();
  const strategy = (position.strategy || '').toLowerCase();
  const lane = (position.lane || '').toUpperCase();
  return category === 'sports' || strategy === 'sports_arbitrage' || lane === 'SPORTS';
};

const getSignalStrengthDisplay = (position) => {
  // Polymorphic column: Edge for Sports, Sentiment for others
  if (isSportsPosition(position)) {
    const edgePct = (position.edge_pct || position.edge || 0) * 100;
    return {
      value: `Edge: ${edgePct.toFixed(1)}%`,
      color: edgePct > 5 ? 'text-green-400' : edgePct > 2 ? 'text-yellow-400' : 'text-white/60',
      bgColor: edgePct > 5 ? 'bg-green-500/20' : edgePct > 2 ? 'bg-yellow-500/20' : 'bg-white/5',
      type: 'sports'
    };
  } else {
    const sentimentScore = position.sentiment_score || position.confidence || 0;
    const displayScore = sentimentScore > 1 ? sentimentScore : sentimentScore * 100; // Handle 0-1 or 0-100
    return {
      value: `Sentiment: ${displayScore.toFixed(0)}/100`,
      color: displayScore > 75 ? 'text-blue-400' : displayScore > 50 ? 'text-cyan-400' : 'text-white/60',
      bgColor: displayScore > 75 ? 'bg-blue-500/20' : displayScore > 50 ? 'bg-cyan-500/20' : 'bg-white/5',
      type: 'sentiment'
    };
  }
};

// Sports Allocation Limit (from SSOT)
const SPORTS_ALLOCATION_LIMIT = 0.15; // 15% hard cap

const Positions = () => {
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState('pnl');
  const [sortOrder, setSortOrder] = useState('desc');
  // Multi-select arrays instead of single values
  const [selectedStrategies, setSelectedStrategies] = useState([]);
  const [selectedAssetClasses, setSelectedAssetClasses] = useState([]);
  const [expandedPosition, setExpandedPosition] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);

  // Toggle strategy selection
  const toggleStrategy = (strategyValue) => {
    setSelectedStrategies(prev => 
      prev.includes(strategyValue) 
        ? prev.filter(s => s !== strategyValue)
        : [...prev, strategyValue]
    );
  };

  // Toggle asset class selection
  const toggleAssetClass = (assetValue) => {
    setSelectedAssetClasses(prev => 
      prev.includes(assetValue) 
        ? prev.filter(a => a !== assetValue)
        : [...prev, assetValue]
    );
  };

  // Clear all filters
  const clearAllFilters = () => {
    setSelectedStrategies([]);
    setSelectedAssetClasses([]);
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket connection for real-time position updates
  useEffect(() => {
    let ws = null;
    let reconnectTimeout = null;
    
    const connectWs = () => {
      try {
        const wsUrl = BACKEND_URL.replace('https', 'wss').replace('http', 'ws') + '/ws';
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
          console.log('Positions WebSocket connected');
          setWsConnected(true);
        };
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'position_update' || data.positions) {
              setPositions(data.positions || []);
            } else if (data.type === 'trade' && data.trade) {
              setTrades(prev => [data.trade, ...prev].slice(0, 100));
            }
          } catch (e) {
            console.error('Error parsing WebSocket message:', e);
          }
        };
        
        ws.onclose = () => {
          setWsConnected(false);
          reconnectTimeout = setTimeout(connectWs, 5000);
        };
        
        ws.onerror = () => setWsConnected(false);
      } catch (e) {
        console.error('WS connection error:', e);
      }
    };
    
    connectWs();
    return () => {
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const fetchData = async () => {
    try {
      const [posRes, tradesRes, perfRes] = await Promise.all([
        axios.get(`${API}/positions`),
        axios.get(`${API}/trades?limit=100`),
        axios.get(`${API}/performance`)
      ]);
      setPositions(posRes.data.positions || []);
      setTrades(tradesRes.data.trades || []);
      setPerformance(perfRes.data);
      setLoading(false);
    } catch (e) {
      console.error('Error fetching data:', e);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="positions-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  // Calculate aggregate metrics
  const totalUnrealizedPnL = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0);
  const totalValue = positions.reduce((sum, p) => sum + ((p.shares || 0) * (p.current_price || 0)), 0);
  const totalCost = positions.reduce((sum, p) => sum + ((p.shares || 0) * (p.avg_price || 0)), 0);
  const overallPnLPct = totalCost > 0 ? ((totalValue - totalCost) / totalCost * 100) : 0;
  
  // Group by strategy
  const strategyBreakdown = positions.reduce((acc, p) => {
    const strategy = p.strategy || 'unknown';
    if (!acc[strategy]) {
      acc[strategy] = { count: 0, value: 0, pnl: 0 };
    }
    acc[strategy].count++;
    acc[strategy].value += (p.shares || 0) * (p.current_price || 0);
    acc[strategy].pnl += p.unrealized_pnl || 0;
    return acc;
  }, {});

  const strategyChartData = Object.entries(strategyBreakdown).map(([name, data]) => ({
    name: name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
    value: data.value,
    count: data.count
  }));

  // ============================================================================
  // SPORTS ALLOCATION TRACKING (Task: Polymorphic UI)
  // ============================================================================
  // Calculate sports allocation vs SSOT limit
  const sportsPositions = positions.filter(p => isSportsPosition(p));
  const sportsValue = sportsPositions.reduce((sum, p) => sum + ((p.shares || 0) * (p.current_price || 0)), 0);
  const sportsAllocationPct = totalValue > 0 ? (sportsValue / totalValue) : 0;
  const sportsOverLimit = sportsAllocationPct > SPORTS_ALLOCATION_LIMIT;

  // Category breakdown for sector chart
  const categoryBreakdown = positions.reduce((acc, p) => {
    const category = (p.category || p.asset_class || 'unknown').toLowerCase();
    if (!acc[category]) {
      acc[category] = { count: 0, value: 0, pnl: 0 };
    }
    acc[category].count++;
    acc[category].value += (p.shares || 0) * (p.current_price || 0);
    acc[category].pnl += p.unrealized_pnl || 0;
    return acc;
  }, {});

  const categoryChartData = Object.entries(categoryBreakdown).map(([name, data]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: data.value,
    count: data.count,
    isOverLimit: name === 'sports' && sportsOverLimit
  }));

  // Group by side (long/short)
  const longPositions = positions.filter(p => p.side === 'BUY');
  const shortPositions = positions.filter(p => p.side === 'SELL');
  const longValue = longPositions.reduce((sum, p) => sum + ((p.shares || 0) * (p.current_price || 0)), 0);
  const shortValue = shortPositions.reduce((sum, p) => sum + ((p.shares || 0) * (p.current_price || 0)), 0);

  // Risk metrics
  const largestPosition = positions.length > 0 ? 
    Math.max(...positions.map(p => (p.shares || 0) * (p.current_price || 0))) : 0;
  const concentrationRisk = totalValue > 0 ? (largestPosition / totalValue * 100) : 0;
  const avgPositionSize = positions.length > 0 ? totalValue / positions.length : 0;

  // Filter and sort positions - support multi-select filtering
  const filteredPositions = positions
    .filter(p => {
      // If no strategies selected, show all; otherwise check if position's strategy is in selected list
      const strategyMatch = selectedStrategies.length === 0 || selectedStrategies.includes(p.strategy);
      // If no asset classes selected, show all; otherwise check if position's category is in selected list
      const assetMatch = selectedAssetClasses.length === 0 || 
        selectedAssetClasses.includes(p.category) || 
        selectedAssetClasses.includes(p.asset_class);
      return strategyMatch && assetMatch;
    })
    .sort((a, b) => {
      let aVal, bVal;
      switch (sortBy) {
        case 'pnl':
          aVal = a.unrealized_pnl || 0;
          bVal = b.unrealized_pnl || 0;
          break;
        case 'value':
          aVal = (a.shares || 0) * (a.current_price || 0);
          bVal = (b.shares || 0) * (b.current_price || 0);
          break;
        case 'pnlPct':
          aVal = (a.unrealized_pnl_pct || 0) * 100;  // Use API value
          bVal = (b.unrealized_pnl_pct || 0) * 100;
          break;
        case 'time':
          aVal = new Date(a.opened_at).getTime();
          bVal = new Date(b.opened_at).getTime();
          break;
        default:
          aVal = 0;
          bVal = 0;
      }
      return sortOrder === 'desc' ? bVal - aVal : aVal - bVal;
    });

  const uniqueStrategies = [...new Set(positions.map(p => p.strategy).filter(Boolean))];
  const uniqueAssetClasses = [...new Set(positions.map(p => p.category || p.asset_class).filter(Boolean))];
  
  const hasActiveFilters = selectedStrategies.length > 0 || selectedAssetClasses.length > 0;

  return (
    <div className="space-y-6" data-testid="positions-page">
      
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Open Positions</h1>
          <p className="text-white/60 text-sm mt-1">
            {positions.length} active position{positions.length !== 1 ? 's' : ''} across {uniqueStrategies.length} strategies
          </p>
        </div>
        
        {/* Quick Actions - Sort Only */}
        <div className="flex items-center gap-3">
          {/* WebSocket Status */}
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${wsConnected ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
            {wsConnected ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
            <span className="text-xs font-medium">{wsConnected ? 'Live' : 'Offline'}</span>
          </div>
          
          {/* Sort By */}
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="appearance-none bg-slate-800 border border-white/20 rounded-lg px-4 py-2 pr-10 text-sm text-white focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50 cursor-pointer min-w-[140px]"
              style={{ colorScheme: 'dark' }}
              data-testid="sort-filter"
            >
              <option value="pnl" className="bg-slate-800 text-white py-2">Sort by P&L</option>
              <option value="value" className="bg-slate-800 text-white py-2">Sort by Value</option>
              <option value="pnlPct" className="bg-slate-800 text-white py-2">Sort by P&L %</option>
              <option value="time" className="bg-slate-800 text-white py-2">Sort by Time</option>
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/50 pointer-events-none" />
          </div>
          
          {/* Sort Order Toggle */}
          <button
            onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
            className="bg-slate-800 border border-white/20 rounded-lg p-2 text-white hover:bg-slate-700 hover:border-white/30 transition"
            title={sortOrder === 'desc' ? 'Descending' : 'Ascending'}
          >
            {sortOrder === 'desc' ? <ChevronDown className="w-5 h-5" /> : <ChevronUp className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Multi-Select Filters - Pill/Tag Style */}
      <div className="rounded-xl bg-white/5 border border-white/10 p-4 space-y-4">
        {/* Strategy Multi-Select */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-white/70">Filter by Strategy</span>
            {selectedStrategies.length > 0 && (
              <button 
                onClick={() => setSelectedStrategies([])}
                className="text-xs text-cyan-400 hover:text-cyan-300"
              >
                Clear ({selectedStrategies.length})
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2" data-testid="strategy-pills">
            {ALL_STRATEGIES.map(strategy => {
              const isSelected = selectedStrategies.includes(strategy.value);
              return (
                <button
                  key={strategy.value}
                  onClick={() => toggleStrategy(strategy.value)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    isSelected 
                      ? 'text-white shadow-lg' 
                      : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-white/10'
                  }`}
                  style={isSelected ? { backgroundColor: strategy.color, boxShadow: `0 0 12px ${strategy.color}40` } : {}}
                  data-testid={`strategy-pill-${strategy.value}`}
                >
                  {strategy.label}
                  {isSelected && <span className="ml-1.5">✓</span>}
                </button>
              );
            })}
          </div>
        </div>

        {/* Asset Class Multi-Select */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-white/70">Filter by Asset Class</span>
            {selectedAssetClasses.length > 0 && (
              <button 
                onClick={() => setSelectedAssetClasses([])}
                className="text-xs text-purple-400 hover:text-purple-300"
              >
                Clear ({selectedAssetClasses.length})
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2" data-testid="asset-class-pills">
            {ALL_ASSET_CLASSES.map(asset => {
              const isSelected = selectedAssetClasses.includes(asset.value);
              return (
                <button
                  key={asset.value}
                  onClick={() => toggleAssetClass(asset.value)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    isSelected 
                      ? 'text-white shadow-lg' 
                      : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-white/10'
                  }`}
                  style={isSelected ? { backgroundColor: asset.color, boxShadow: `0 0 12px ${asset.color}40` } : {}}
                  data-testid={`asset-pill-${asset.value}`}
                >
                  {asset.label}
                  {isSelected && <span className="ml-1.5">✓</span>}
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Filters Summary & Clear All */}
        {hasActiveFilters && (
          <div className="flex items-center justify-between pt-3 border-t border-white/10">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-white/50">Showing:</span>
              <span className="text-white font-medium">{filteredPositions.length}</span>
              <span className="text-white/50">of {positions.length} positions</span>
              {selectedStrategies.length > 0 && (
                <span className="text-cyan-400">• {selectedStrategies.length} strateg{selectedStrategies.length === 1 ? 'y' : 'ies'}</span>
              )}
              {selectedAssetClasses.length > 0 && (
                <span className="text-purple-400">• {selectedAssetClasses.length} asset class{selectedAssetClasses.length === 1 ? '' : 'es'}</span>
              )}
            </div>
            <button
              onClick={clearAllFilters}
              className="px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 text-xs font-medium hover:bg-red-500/30 transition flex items-center gap-1"
            >
              <X className="w-3 h-3" />
              Clear All Filters
            </button>
          </div>
        )}
      </div>

      {/* Portfolio Overview Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {/* Total Value */}
        <div className="col-span-1 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-500/30 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Briefcase className="w-4 h-4 text-cyan-400" />
            <span className="text-xs text-cyan-400/80 uppercase">Total Value</span>
          </div>
          <p className="text-2xl font-bold text-white">${totalValue.toFixed(2)}</p>
        </div>

        {/* Unrealized P&L */}
        <div className={`col-span-1 rounded-xl border p-4 ${
          totalUnrealizedPnL >= 0 
            ? 'bg-gradient-to-br from-green-500/20 to-emerald-600/20 border-green-500/30'
            : 'bg-gradient-to-br from-red-500/20 to-rose-600/20 border-red-500/30'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className={`w-4 h-4 ${totalUnrealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`} />
            <span className={`text-xs uppercase ${totalUnrealizedPnL >= 0 ? 'text-green-400/80' : 'text-red-400/80'}`}>Unrealized P&L</span>
          </div>
          <p className={`text-2xl font-bold ${totalUnrealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {totalUnrealizedPnL >= 0 ? '+' : ''}${totalUnrealizedPnL.toFixed(2)}
          </p>
          <p className={`text-xs mt-1 ${overallPnLPct >= 0 ? 'text-green-400/60' : 'text-red-400/60'}`}>
            {overallPnLPct >= 0 ? '+' : ''}{overallPnLPct.toFixed(2)}%
          </p>
        </div>

        {/* Long Exposure */}
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-green-400" />
            <span className="text-xs text-white/60 uppercase">Long</span>
          </div>
          <p className="text-xl font-bold text-green-400">${longValue.toFixed(2)}</p>
          <p className="text-xs text-white/40 mt-1">{longPositions.length} positions</p>
        </div>

        {/* Short Exposure */}
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown className="w-4 h-4 text-red-400" />
            <span className="text-xs text-white/60 uppercase">Short</span>
          </div>
          <p className="text-xl font-bold text-red-400">${shortValue.toFixed(2)}</p>
          <p className="text-xs text-white/40 mt-1">{shortPositions.length} positions</p>
        </div>

        {/* Avg Position Size */}
        <div className="rounded-xl bg-white/5 border border-white/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-white/60 uppercase">Avg Size</span>
          </div>
          <p className="text-xl font-bold text-white">${avgPositionSize.toFixed(2)}</p>
        </div>

        {/* Concentration Risk */}
        <div className={`rounded-xl border p-4 ${
          concentrationRisk > 50 
            ? 'bg-gradient-to-br from-red-500/10 to-orange-500/10 border-red-500/30'
            : 'bg-white/5 border-white/10'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className={`w-4 h-4 ${concentrationRisk > 50 ? 'text-red-400' : 'text-yellow-400'}`} />
            <span className="text-xs text-white/60 uppercase">Concentration</span>
          </div>
          <p className={`text-xl font-bold ${concentrationRisk > 50 ? 'text-red-400' : 'text-white'}`}>
            {concentrationRisk.toFixed(1)}%
          </p>
          <p className="text-xs text-white/40 mt-1">
            {concentrationRisk > 50 ? 'High risk' : concentrationRisk > 25 ? 'Moderate' : 'Diversified'}
          </p>
        </div>
      </div>

      {/* Strategy Breakdown & Chart Row */}
      {positions.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Strategy Allocation Pie */}
          <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
            <h3 className="text-sm font-semibold text-white mb-4">Strategy Allocation</h3>
            {strategyChartData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={strategyChartData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={75}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {strategyChartData.map((entry, index) => (
                        <Cell 
                          key={`cell-${index}`} 
                          fill={entry.name.toLowerCase().includes('sports') ? '#ec4899' : COLORS[index % COLORS.length]} 
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-3 space-y-2">
                  {strategyChartData.map((item, idx) => {
                    const isSports = item.name.toLowerCase().includes('sports');
                    return (
                      <div key={idx} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <div 
                            className="w-2 h-2 rounded-full" 
                            style={{ backgroundColor: isSports ? '#ec4899' : COLORS[idx % COLORS.length] }} 
                          />
                          <span className="text-white/70">{item.name}</span>
                          {isSports && (
                            <span className="px-1.5 py-0.5 rounded text-xs bg-pink-500/20 text-pink-400">SPORTS</span>
                          )}
                        </div>
                        <span className="text-white font-medium">${item.value.toFixed(2)}</span>
                      </div>
                    );
                  })}
                </div>
                
                {/* Sports Allocation Alert */}
                {sportsOverLimit && (
                  <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 flex items-center gap-2" data-testid="sports-allocation-warning">
                    <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                    <p className="text-xs text-red-400">
                      Sports allocation ({(sportsAllocationPct * 100).toFixed(1)}%) exceeds {(SPORTS_ALLOCATION_LIMIT * 100).toFixed(0)}% limit
                    </p>
                  </div>
                )}
              </>
            ) : (
              <div className="h-48 flex items-center justify-center text-white/40">No data</div>
            )}
          </div>

          {/* Sector/Category Allocation (Shows SSOT Limits) */}
          <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6" data-testid="sector-allocation">
            <h3 className="text-sm font-semibold text-white mb-4">Sector Allocation</h3>
            {categoryChartData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={categoryChartData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={75}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {categoryChartData.map((entry, index) => {
                        const colorMap = {
                          'politics': '#ef4444',
                          'crypto': '#f59e0b',
                          'finance': '#10b981',
                          'entertainment': '#ec4899',
                          'science': '#06b6d4',
                          'sports': '#8b5cf6'
                        };
                        return (
                          <Cell 
                            key={`sector-${index}`} 
                            fill={colorMap[entry.name.toLowerCase()] || COLORS[index % COLORS.length]}
                            stroke={entry.isOverLimit ? '#ef4444' : 'none'}
                            strokeWidth={entry.isOverLimit ? 2 : 0}
                          />
                        );
                      })}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-3 space-y-2">
                  {categoryChartData.map((item, idx) => {
                    const colorMap = {
                      'politics': '#ef4444',
                      'crypto': '#f59e0b',
                      'finance': '#10b981',
                      'entertainment': '#ec4899',
                      'science': '#06b6d4',
                      'sports': '#8b5cf6'
                    };
                    const pct = totalValue > 0 ? (item.value / totalValue * 100) : 0;
                    return (
                      <div key={idx} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <div 
                            className={`w-2 h-2 rounded-full ${item.isOverLimit ? 'ring-2 ring-red-400' : ''}`}
                            style={{ backgroundColor: colorMap[item.name.toLowerCase()] || COLORS[idx % COLORS.length] }} 
                          />
                          <span className={`text-white/70 ${item.isOverLimit ? 'text-red-400' : ''}`}>
                            {item.name}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-white/50 text-xs">{pct.toFixed(1)}%</span>
                          <span className="text-white font-medium">${item.value.toFixed(2)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <div className="h-48 flex items-center justify-center text-white/40">No positions</div>
            )}
          </div>

          {/* Strategy Performance Table */}
          <div className="lg:col-span-2 rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-6">
            <h3 className="text-sm font-semibold text-white mb-4">Strategy Performance</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs font-medium text-white/60 pb-3">Strategy</th>
                    <th className="text-right text-xs font-medium text-white/60 pb-3">Positions</th>
                    <th className="text-right text-xs font-medium text-white/60 pb-3">Value</th>
                    <th className="text-right text-xs font-medium text-white/60 pb-3">Unrealized P&L</th>
                    <th className="text-right text-xs font-medium text-white/60 pb-3">% of Portfolio</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(strategyBreakdown).map(([strategy, data], idx) => (
                    <tr key={strategy} className="border-b border-white/5">
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }} />
                          <span className="text-sm text-white">{strategy.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                        </div>
                      </td>
                      <td className="py-3 text-right text-sm text-white/80">{data.count}</td>
                      <td className="py-3 text-right text-sm text-white">${data.value.toFixed(2)}</td>
                      <td className={`py-3 text-right text-sm font-medium ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {data.pnl >= 0 ? '+' : ''}${data.pnl.toFixed(2)}
                      </td>
                      <td className="py-3 text-right text-sm text-cyan-400">
                        {totalValue > 0 ? ((data.value / totalValue) * 100).toFixed(1) : 0}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Positions Grid */}
      {filteredPositions.length === 0 ? (
        <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-16 text-center" data-testid="no-positions-message">
          <Layers className="w-16 h-16 text-white/20 mx-auto mb-4" />
          <p className="text-white/60 text-lg">No open positions</p>
          <p className="text-white/40 text-sm mt-2">Start the trading bot to open positions</p>
        </div>
      ) : (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-white">Position Details ({filteredPositions.length})</h3>
          
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {filteredPositions.map((position, idx) => {
              const pnlPct = (position.unrealized_pnl_pct || 0) * 100;  // Use API value, convert from decimal
              const isProfit = (position.unrealized_pnl || 0) >= 0;
              const positionValue = (position.shares || 0) * (position.current_price || 0);
              const portfolioPct = totalValue > 0 ? (positionValue / totalValue * 100) : 0;
              const holdTime = position.opened_at ? 
                Math.floor((Date.now() - new Date(position.opened_at).getTime()) / (1000 * 60)) : 0;
              const isExpanded = expandedPosition === idx;

              return (
                <div 
                  key={idx} 
                  data-testid={`position-card-${idx}`}
                  className={`rounded-xl backdrop-blur-xl border transition-all cursor-pointer ${
                    isProfit 
                      ? 'bg-gradient-to-br from-green-500/5 to-emerald-500/5 border-green-500/20 hover:border-green-500/40'
                      : 'bg-gradient-to-br from-red-500/5 to-rose-500/5 border-red-500/20 hover:border-red-500/40'
                  }`}
                  onClick={() => setExpandedPosition(isExpanded ? null : idx)}
                >
                  {/* Main Card Content */}
                  <div className="p-5">
                    {/* Header Row */}
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          {/* Strategy Badge */}
                          <span className={`px-2 py-1 rounded text-xs font-medium border ${
                            isSportsPosition(position)
                              ? 'bg-pink-500/20 text-pink-400 border-pink-500/30'
                              : 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
                          }`}>
                            {position.strategy?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </span>
                          
                          {/* Side Badge */}
                          <span className={`px-2 py-1 rounded text-xs font-medium ${
                            position.side === 'BUY' || position.side === 'YES'
                              ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                              : 'bg-red-500/20 text-red-400 border border-red-500/30'
                          }`}>
                            {position.side === 'BUY' || position.side === 'YES' ? 'LONG' : 'SHORT'}
                          </span>
                          
                          {/* Polymorphic Signal Strength Badge */}
                          {(() => {
                            const signalDisplay = getSignalStrengthDisplay(position);
                            return (
                              <span className={`px-2 py-1 rounded text-xs font-medium ${signalDisplay.bgColor} ${signalDisplay.color} border border-white/10`}
                                    data-testid={`signal-strength-${signalDisplay.type}`}>
                                {signalDisplay.value}
                              </span>
                            );
                          })()}
                          
                          {/* Sports Lane Indicator */}
                          {isSportsPosition(position) && (
                            <span className="px-2 py-1 rounded text-xs font-medium bg-purple-500/20 text-purple-400 border border-purple-500/30">
                              SPORTS
                            </span>
                          )}
                          
                          <span className="px-2 py-1 rounded text-xs font-medium bg-white/10 text-white/60">
                            {portfolioPct.toFixed(1)}% of portfolio
                          </span>
                        </div>
                        <p className="text-xs text-white/50 font-mono truncate max-w-[250px]">{position.market_id}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-2xl font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                          {isProfit ? '+' : ''}${(position.unrealized_pnl || 0).toFixed(2)}
                        </p>
                        <p className={`text-sm ${isProfit ? 'text-green-400/60' : 'text-red-400/60'}`}>
                          {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                        </p>
                      </div>
                    </div>

                    {/* Quick Stats Row */}
                    <div className="grid grid-cols-4 gap-3">
                      <div className="text-center p-2 rounded-lg bg-white/5">
                        <p className="text-xs text-white/50 mb-1">Shares</p>
                        <p className="text-sm font-semibold text-white">{(position.shares || 0).toFixed(2)}</p>
                      </div>
                      <div className="text-center p-2 rounded-lg bg-white/5">
                        <p className="text-xs text-white/50 mb-1">Entry</p>
                        <p className="text-sm font-semibold text-white">${(position.avg_price || position.entry_price || 0).toFixed(3)}</p>
                      </div>
                      <div className="text-center p-2 rounded-lg bg-white/5">
                        <p className="text-xs text-white/50 mb-1">Current</p>
                        <p className="text-sm font-semibold text-white">${(position.current_price || 0).toFixed(3)}</p>
                      </div>
                      <div className="text-center p-2 rounded-lg bg-white/5">
                        <p className="text-xs text-white/50 mb-1">Value</p>
                        <p className="text-sm font-semibold text-cyan-400">${positionValue.toFixed(2)}</p>
                      </div>
                    </div>

                    {/* Time Info */}
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-white/10">
                      <div className="flex items-center gap-2 text-xs text-white/40">
                        <Clock className="w-3 h-3" />
                        <span>Opened {position.opened_at ? new Date(position.opened_at).toLocaleString() : 'N/A'}</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-white/40">
                        <Timer className="w-3 h-3" />
                        <span>{holdTime < 60 ? `${holdTime}m` : `${Math.floor(holdTime/60)}h ${holdTime%60}m`} held</span>
                      </div>
                    </div>
                  </div>

                  {/* ================================================================
                      EXPANDED DETAILS - POLYMORPHIC RENDERING
                      Branch A: Sports Mode (Statistical Arbitrage)
                      Branch B: Legacy Mode (Sentiment-Based)
                      ================================================================ */}
                  {isExpanded && (
                    <div className="px-5 pb-5 pt-0 border-t border-white/10 mt-0">
                      {isSportsPosition(position) ? (
                        /* ============================================
                           BRANCH A: SPORTS MODE (Statistical Arbitrage)
                           ============================================ */
                        <div className="pt-4 space-y-4" data-testid="sports-detail-card">
                          {/* Header */}
                          <div className="flex items-center gap-2">
                            <Zap className="w-4 h-4 text-pink-400" />
                            <h4 className="text-sm font-semibold text-pink-400">Statistical Arbitrage Opportunity</h4>
                          </div>
                          
                          {/* Implied vs Fair Value */}
                          <div className="grid grid-cols-2 gap-4">
                            <div className="p-3 rounded-lg bg-white/5">
                              <p className="text-xs text-white/50 mb-1">Implied Probability</p>
                              <p className="text-lg font-bold text-white">
                                {((position.current_price || position.entry_price || 0) * 100).toFixed(1)}%
                              </p>
                              <p className="text-xs text-white/40">Market Price</p>
                            </div>
                            <div className="p-3 rounded-lg bg-pink-500/10 border border-pink-500/20">
                              <p className="text-xs text-pink-400/80 mb-1">Fair Value</p>
                              <p className="text-lg font-bold text-pink-400">
                                {((position.fair_value || 0) * 100).toFixed(1)}%
                              </p>
                              <p className="text-xs text-white/40">Real Odds</p>
                            </div>
                          </div>
                          
                          {/* Edge & Kelly Stake */}
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <p className="text-xs text-white/50 mb-1">Statistical Edge</p>
                              <p className={`text-sm font-semibold ${(position.edge || 0) > 0.05 ? 'text-green-400' : 'text-yellow-400'}`}>
                                {((position.edge || position.edge_pct || 0) * 100).toFixed(2)}%
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-white/50 mb-1">Kelly Stake</p>
                              <p className="text-sm font-semibold text-cyan-400">
                                ${(position.size || positionValue).toFixed(2)}
                              </p>
                            </div>
                          </div>
                          
                          {/* Arbitrage Explanation (replaces LLM reasoning) */}
                          <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                            <p className="text-xs text-white/50 mb-1">Arbitrage Analysis</p>
                            <p className="text-sm text-white/80">
                              {position.sports_matched_event ? (
                                <>
                                  Arbitrage detected vs <span className="text-cyan-400">{position.bookmakers_used || 'multiple'} bookmakers</span>.
                                  Market implies <span className="text-white">{((position.current_price || position.entry_price || 0) * 100).toFixed(1)}%</span>,
                                  Real odds are <span className="text-pink-400">{((position.fair_value || 0) * 100).toFixed(1)}%</span>.
                                  {position.sports_matched_event?.home_team && (
                                    <span className="text-white/60 block mt-1">
                                      Event: {position.sports_matched_event.home_team} vs {position.sports_matched_event.away_team}
                                    </span>
                                  )}
                                </>
                              ) : (
                                `Statistical edge of ${((position.edge || 0) * 100).toFixed(2)}% identified via sports odds aggregation.`
                              )}
                            </p>
                          </div>
                          
                          {/* Stop/Target */}
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <p className="text-xs text-white/50 mb-1">Stop Loss (25%)</p>
                              <p className="text-sm text-red-400">${((position.avg_price || position.entry_price || 0) * 0.75).toFixed(4)}</p>
                            </div>
                            <div>
                              <p className="text-xs text-white/50 mb-1">Take Profit (30%)</p>
                              <p className="text-sm text-green-400">${((position.avg_price || position.entry_price || 0) * 1.3).toFixed(4)}</p>
                            </div>
                          </div>
                        </div>
                      ) : (
                        /* ============================================
                           BRANCH B: LEGACY MODE (Sentiment-Based)
                           ============================================ */
                        <div className="pt-4 space-y-4" data-testid="sentiment-detail-card">
                          {/* Sentiment Gauge (existing) */}
                          {(position.sentiment_score || position.confidence) && (
                            <div className="mb-4">
                              <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-white/50">Sentiment Score</p>
                                <p className="text-sm font-semibold text-blue-400">
                                  {((position.sentiment_score || position.confidence || 0) * (position.sentiment_score > 1 ? 1 : 100)).toFixed(0)}/100
                                </p>
                              </div>
                              <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                                <div 
                                  className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full transition-all"
                                  style={{ width: `${Math.min(100, (position.sentiment_score || position.confidence || 0) * (position.sentiment_score > 1 ? 1 : 100))}%` }}
                                />
                              </div>
                            </div>
                          )}
                          
                          {/* LLM Reasoning */}
                          {position.llm_explanation && (
                            <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                              <p className="text-xs text-white/50 mb-1">AI Analysis</p>
                              <p className="text-sm text-white/80">{position.llm_explanation}</p>
                            </div>
                          )}
                          
                          {/* Legacy Stats */}
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <p className="text-xs text-white/50 mb-1">Cost Basis</p>
                              <p className="text-sm text-white">${((position.shares || 0) * (position.avg_price || position.entry_price || 0)).toFixed(2)}</p>
                            </div>
                            <div>
                              <p className="text-xs text-white/50 mb-1">Break Even</p>
                              <p className="text-sm text-white">${(position.avg_price || position.entry_price || 0).toFixed(4)}</p>
                            </div>
                            <div>
                              <p className="text-xs text-white/50 mb-1">Target (10% profit)</p>
                              <p className="text-sm text-green-400">${((position.avg_price || position.entry_price || 0) * 1.1).toFixed(4)}</p>
                            </div>
                            <div>
                              <p className="text-xs text-white/50 mb-1">Stop Loss (5%)</p>
                              <p className="text-sm text-red-400">${((position.avg_price || position.entry_price || 0) * 0.95).toFixed(4)}</p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Bottom Summary Bar */}
      <div className="rounded-xl bg-gradient-to-r from-slate-800/50 to-slate-900/50 border border-white/10 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <div className="text-center">
              <p className="text-xs text-white/40 uppercase">Net Exposure</p>
              <p className={`text-xl font-bold ${(longValue - shortValue) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${Math.abs(longValue - shortValue).toFixed(2)} {(longValue - shortValue) >= 0 ? 'Long' : 'Short'}
              </p>
            </div>
            <div className="w-px h-8 bg-white/10" />
            <div className="text-center">
              <p className="text-xs text-white/40 uppercase">Total Exposure</p>
              <p className="text-xl font-bold text-white">${(longValue + shortValue).toFixed(2)}</p>
            </div>
            <div className="w-px h-8 bg-white/10" />
            <div className="text-center">
              <p className="text-xs text-white/40 uppercase">Strategies</p>
              <p className="text-xl font-bold text-purple-400">{uniqueStrategies.length}</p>
            </div>
          </div>
          <div className="text-xs text-white/40">
            Auto-refreshing every 5s
          </div>
        </div>
      </div>
    </div>
  );
};

export default Positions;
