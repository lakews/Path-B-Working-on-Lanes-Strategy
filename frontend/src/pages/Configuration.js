import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Settings, Save, RefreshCw, DollarSign, Percent, Activity, Shield, Zap, AlertTriangle, Target, Clock, Info, Sliders, Layers, TrendingUp, Landmark, Trophy, Film, Bitcoin, Globe, Check, X, BarChart3, GitBranch, Crosshair, Scale } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Asset class definitions with metadata
const ASSET_CLASSES = [
  { id: 'finance', label: 'Finance', icon: TrendingUp, color: 'emerald', description: 'Interest rates, economic indicators, market indices' },
  { id: 'politics', label: 'Politics', icon: Landmark, color: 'blue', description: 'Elections, policy decisions, government actions' },
  { id: 'sports', label: 'Sports', icon: Trophy, color: 'orange', description: 'Game outcomes, championships, player performance' },
  { id: 'crypto', label: 'Crypto', icon: Bitcoin, color: 'yellow', description: 'Bitcoin price, crypto events, blockchain milestones' },
  { id: 'entertainment', label: 'Entertainment', icon: Film, color: 'purple', description: 'Awards, box office, celebrity events' },
  { id: 'science', label: 'Science & Tech', icon: Globe, color: 'cyan', description: 'Scientific discoveries, tech launches, AI developments' },
];

// Trading strategies with metadata
const STRATEGIES = [
  { id: 'delta_neutral', label: 'Delta-Neutral', icon: Scale, color: 'cyan', description: 'Market making with zero directional exposure, captures spreads', risk: 'Low', expectedReturn: '5-15%' },
  { id: 'volatility_exploitation', label: 'Volatility Exploitation', icon: Zap, color: 'yellow', description: 'Buy at extreme prices during volatility spikes', risk: 'High', expectedReturn: '30-100x' },
  { id: 'alpha_directional', label: 'Alpha-Directional', icon: TrendingUp, color: 'green', description: 'Directional bets based on ML signals and sentiment', risk: 'Medium', expectedReturn: '10-30%' },
  { id: 'arbitrage', label: 'Multi-Market Arbitrage', icon: GitBranch, color: 'purple', description: 'Exploit price discrepancies across similar markets', risk: 'Low', expectedReturn: '2-5%' },
];

const Configuration = () => {
  const [config, setConfig] = useState({
    trades_per_10min: 500,
    initial_capital: 100,
    capital_deployment_pct: 80,
    max_position_size_pct: 3,
    kelly_fraction: 0.25,
    max_drawdown_pct: 3,
    enabled_asset_classes: ['finance', 'politics', 'sports', 'crypto', 'entertainment', 'science'],
    enabled_strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']
  });
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('trading');

  useEffect(() => { fetchConfig(); }, []);

  const fetchConfig = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setStatus(response.data);
      setConfig(response.data.configuration || config);
      setLoading(false);
    } catch (e) { setLoading(false); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/config/update`, config);
      toast.success('Configuration updated!');
      fetchConfig();
    } catch (e) { toast.error('Failed to update'); }
    finally { setSaving(false); }
  };

  const resetToDefaults = () => {
    setConfig({ 
      trades_per_10min: 500, 
      initial_capital: 100, 
      capital_deployment_pct: 80, 
      max_position_size_pct: 3, 
      kelly_fraction: 0.25, 
      max_drawdown_pct: 3, 
      enabled_asset_classes: ['finance', 'politics', 'sports', 'crypto', 'entertainment', 'science'],
      enabled_strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage']
    });
    toast.info('Reset to defaults');
  };

  const toggleAssetClass = (assetId) => {
    setConfig(prev => {
      const current = prev.enabled_asset_classes || [];
      if (current.includes(assetId)) {
        if (current.length === 1) {
          toast.error('Must have at least one asset class enabled');
          return prev;
        }
        return { ...prev, enabled_asset_classes: current.filter(id => id !== assetId) };
      } else {
        return { ...prev, enabled_asset_classes: [...current, assetId] };
      }
    });
  };

  const toggleStrategy = (strategyId) => {
    setConfig(prev => {
      const current = prev.enabled_strategies || [];
      if (current.includes(strategyId)) {
        if (current.length === 1) {
          toast.error('Must have at least one strategy enabled');
          return prev;
        }
        return { ...prev, enabled_strategies: current.filter(id => id !== strategyId) };
      } else {
        return { ...prev, enabled_strategies: [...current, strategyId] };
      }
    });
  };

  const selectAllAssetClasses = () => {
    setConfig(prev => ({ ...prev, enabled_asset_classes: ASSET_CLASSES.map(a => a.id) }));
  };

  const selectAllStrategies = () => {
    setConfig(prev => ({ ...prev, enabled_strategies: STRATEGIES.map(s => s.id) }));
  };

  // Derived values - max position is % of DEPLOYED capital, not initial capital
  const deployedCapital = (config.initial_capital * (config.capital_deployment_pct || 80) / 100);
  const maxPositionValue = (deployedCapital * (config.max_position_size_pct || 3) / 100);  // % of deployed capital
  const circuitBreakerValue = (config.initial_capital * (config.max_drawdown_pct || 3) / 100);

  if (loading) return <div className="flex items-center justify-center h-96"><div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div></div>;

  return (
    <div className="space-y-6" data-testid="configuration-page">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
            <Settings className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Trading Configuration</h1>
            <p className="text-white/60 text-sm">Customize parameters and risk settings</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={resetToDefaults} className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white/60 hover:text-white hover:bg-white/10 transition flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />Reset
          </button>
          <button onClick={handleSave} disabled={saving} data-testid="save-config-button" className="px-6 py-2 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white font-medium transition-all disabled:opacity-50 flex items-center gap-2">
            <Save className="w-4 h-4" />{saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      {status?.bot_running && (
        <div className="rounded-xl bg-yellow-500/20 border border-yellow-500/30 p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-yellow-400" />
          <p className="text-sm text-yellow-400">Bot is running. Restart for changes to take effect.</p>
        </div>
      )}

      <div className="flex gap-2 bg-white/5 p-1 rounded-xl w-fit">
        {[{ id: 'trading', label: 'Trading', icon: Activity }, { id: 'capital', label: 'Capital', icon: DollarSign }, { id: 'risk', label: 'Risk', icon: Shield }, { id: 'assets', label: 'Asset Class - Strategy', icon: Layers }].map((tab) => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === tab.id ? 'bg-cyan-500 text-white' : 'text-white/60 hover:text-white hover:bg-white/10'}`}>
            <tab.icon className="w-4 h-4" />{tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'trading' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center"><Zap className="w-5 h-5 text-cyan-400" /></div>
              <div><h3 className="text-white font-semibold">Trading Frequency</h3><p className="text-xs text-white/50">Trades per 10 minutes</p></div>
            </div>
            <input type="number" value={config.trades_per_10min || ''} onChange={(e) => setConfig({...config, trades_per_10min: parseInt(e.target.value) || 0})} className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white text-lg font-semibold focus:outline-none focus:border-cyan-500" min="1" max="10000" />
            <div className="grid grid-cols-4 gap-2 mt-4">
              {[100, 250, 500, 1000].map((val) => (
                <button key={val} onClick={() => setConfig({...config, trades_per_10min: val})} className={`px-3 py-2 rounded-lg text-sm font-medium transition ${config.trades_per_10min === val ? 'bg-cyan-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}>{val}</button>
              ))}
            </div>
          </div>
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center"><Clock className="w-5 h-5 text-purple-400" /></div>
              <div><h3 className="text-white font-semibold">Performance Targets</h3><p className="text-xs text-white/50">Execution benchmarks</p></div>
            </div>
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-white/5"><div className="flex justify-between mb-2"><span className="text-sm text-white/60">Execution Latency</span><span className="text-white font-semibold">&lt;100ms</span></div><div className="h-2 bg-white/10 rounded-full"><div className="h-full w-3/4 bg-gradient-to-r from-green-500 to-emerald-400 rounded-full" /></div></div>
              <div className="p-4 rounded-lg bg-white/5"><div className="flex justify-between mb-2"><span className="text-sm text-white/60">ML Inference</span><span className="text-white font-semibold">&lt;50ms</span></div><div className="h-2 bg-white/10 rounded-full"><div className="h-full w-2/3 bg-gradient-to-r from-purple-500 to-indigo-400 rounded-full" /></div></div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'capital' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-green-500/20 flex items-center justify-center"><DollarSign className="w-5 h-5 text-green-400" /></div>
              <div><h3 className="text-white font-semibold">Initial Capital</h3><p className="text-xs text-white/50">Total trading capital (USD)</p></div>
            </div>
            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-white/40 text-lg">$</span>
              <input type="number" value={config.initial_capital || ''} onChange={(e) => setConfig({...config, initial_capital: parseFloat(e.target.value) || 0})} className="w-full pl-8 pr-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white text-lg font-semibold focus:outline-none focus:border-cyan-500" min="1" />
            </div>
            <div className="grid grid-cols-4 gap-2 mt-4">
              {[50, 100, 500, 1000].map((val) => (
                <button key={val} onClick={() => setConfig({...config, initial_capital: val})} className={`px-3 py-2 rounded-lg text-sm font-medium transition ${config.initial_capital === val ? 'bg-green-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}>${val}</button>
              ))}
            </div>
          </div>
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center"><Percent className="w-5 h-5 text-blue-400" /></div>
              <div><h3 className="text-white font-semibold">Capital Deployment</h3><p className="text-xs text-white/50">% of capital to actively use</p></div>
            </div>
            <div className="flex items-center gap-4">
              <input type="range" value={config.capital_deployment_pct || 0} onChange={(e) => setConfig({...config, capital_deployment_pct: parseInt(e.target.value)})} className="flex-1 h-2 bg-white/10 rounded-lg" min="10" max="100" step="5" />
              <span className="text-white font-bold text-xl w-16 text-right">{config.capital_deployment_pct}%</span>
            </div>
            <div className="p-4 rounded-lg bg-blue-500/10 border border-blue-500/20 mt-4">
              <div className="flex justify-between"><span className="text-sm text-white/60">Deployed</span><span className="text-xl font-bold text-blue-400">${deployedCapital.toFixed(2)}</span></div>
            </div>
          </div>
          <div className="lg:col-span-2 rounded-xl bg-slate-800/50 border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Capital Summary</h3>
            <div className="grid grid-cols-4 gap-4">
              <div className="text-center p-4 rounded-lg bg-white/5"><p className="text-xs text-white/50 mb-1">Total</p><p className="text-2xl font-bold text-white">${config.initial_capital.toFixed(2)}</p></div>
              <div className="text-center p-4 rounded-lg bg-white/5"><p className="text-xs text-white/50 mb-1">Deployed</p><p className="text-2xl font-bold text-blue-400">${deployedCapital.toFixed(2)}</p></div>
              <div className="text-center p-4 rounded-lg bg-white/5"><p className="text-xs text-white/50 mb-1">Max/Trade</p><p className="text-2xl font-bold text-cyan-400">${maxPositionValue.toFixed(2)}</p></div>
              <div className="text-center p-4 rounded-lg bg-white/5"><p className="text-xs text-white/50 mb-1">Circuit Breaker</p><p className="text-2xl font-bold text-red-400">-${circuitBreakerValue.toFixed(2)}</p></div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'risk' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center"><Target className="w-5 h-5 text-purple-400" /></div>
              <div><h3 className="text-white font-semibold">Kelly Fraction</h3><p className="text-xs text-white/50">Position sizing based on edge</p></div>
            </div>
            <div className="flex items-center gap-4">
              <input type="range" value={config.kelly_fraction || 0.25} onChange={(e) => setConfig({...config, kelly_fraction: parseFloat(e.target.value)})} className="flex-1 h-2 bg-white/10 rounded-lg" min="0.10" max="0.50" step="0.05" />
              <span className="text-white font-bold text-xl w-16 text-right">{(config.kelly_fraction * 100).toFixed(0)}%</span>
            </div>
            <div className="grid grid-cols-3 gap-2 mt-4">
              {[{ val: 0.15, label: 'Conservative' }, { val: 0.25, label: 'Moderate' }, { val: 0.50, label: 'Aggressive' }].map(({ val, label }) => (
                <button key={val} onClick={() => setConfig({...config, kelly_fraction: val})} className={`px-3 py-2 rounded-lg text-sm font-medium transition ${config.kelly_fraction === val ? 'bg-purple-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}>{label}</button>
              ))}
            </div>
          </div>
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center"><Sliders className="w-5 h-5 text-cyan-400" /></div>
              <div><h3 className="text-white font-semibold">Max Position Size</h3><p className="text-xs text-white/50">Max % per trade</p></div>
            </div>
            <div className="flex items-center gap-4">
              <input type="range" value={config.max_position_size_pct || 0} onChange={(e) => setConfig({...config, max_position_size_pct: parseFloat(e.target.value)})} className="flex-1 h-2 bg-white/10 rounded-lg" min="0.5" max="10" step="0.5" />
              <span className="text-white font-bold text-xl w-16 text-right">{config.max_position_size_pct}%</span>
            </div>
            <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/20 mt-4">
              <div className="flex justify-between"><span className="text-sm text-white/60">Max Trade</span><span className="text-xl font-bold text-cyan-400">${maxPositionValue.toFixed(2)}</span></div>
            </div>
          </div>
          <div className="lg:col-span-2 rounded-xl bg-red-500/10 border border-red-500/30 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-red-500/20 flex items-center justify-center"><AlertTriangle className="w-5 h-5 text-red-400" /></div>
              <div><h3 className="text-white font-semibold">Circuit Breaker (Max Drawdown)</h3><p className="text-xs text-white/50">Trading halts at this loss level</p></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <div className="flex items-center gap-4">
                  <input type="range" value={config.max_drawdown_pct || 3} onChange={(e) => setConfig({...config, max_drawdown_pct: parseFloat(e.target.value)})} className="flex-1 h-2 bg-white/10 rounded-lg" min="1" max="15" step="0.5" />
                  <span className="text-white font-bold text-xl w-16 text-right">{config.max_drawdown_pct}%</span>
                </div>
                <div className="grid grid-cols-4 gap-2 mt-4">
                  {[2, 3, 5, 10].map((val) => (
                    <button key={val} onClick={() => setConfig({...config, max_drawdown_pct: val})} className={`px-3 py-2 rounded-lg text-sm font-medium transition ${config.max_drawdown_pct === val ? 'bg-red-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}>{val}%</button>
                  ))}
                </div>
              </div>
              <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20">
                <div className="flex justify-between mb-3"><span className="text-sm text-white/60">Triggers At</span><span className="text-2xl font-bold text-red-400">-${circuitBreakerValue.toFixed(2)}</span></div>
                <p className="text-xs text-red-400">⚠️ Trading stops if losses exceed {config.max_drawdown_pct}%</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Asset Classes Tab */}
      {activeTab === 'assets' && (
        <div className="space-y-6">
          {/* Strategies Section */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
                  <BarChart3 className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Trading Strategies</h3>
                  <p className="text-xs text-white/50">Select strategies to use for live trading & backtesting</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-white/60">{config.enabled_strategies?.length || 0}/{STRATEGIES.length} enabled</span>
                <button onClick={selectAllStrategies} className="px-3 py-1 rounded-lg bg-white/10 text-white/60 text-xs hover:bg-white/20 transition">
                  Select All
                </button>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {STRATEGIES.map((strategy) => {
                const isEnabled = config.enabled_strategies?.includes(strategy.id);
                const Icon = strategy.icon;
                return (
                  <div
                    key={strategy.id}
                    onClick={() => toggleStrategy(strategy.id)}
                    data-testid={`strategy-${strategy.id}`}
                    className={`relative p-4 rounded-xl border-2 cursor-pointer transition-all ${
                      isEnabled
                        ? `bg-${strategy.color}-500/10 border-${strategy.color}-500/50 shadow-lg shadow-${strategy.color}-500/10`
                        : 'bg-white/5 border-white/10 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                        isEnabled ? `bg-${strategy.color}-500/20` : 'bg-white/10'
                      }`}>
                        <Icon className={`w-6 h-6 ${isEnabled ? `text-${strategy.color}-400` : 'text-white/40'}`} />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <h4 className={`font-semibold ${isEnabled ? 'text-white' : 'text-white/60'}`}>
                            {strategy.label}
                          </h4>
                          <div className={`w-6 h-6 rounded-full flex items-center justify-center ${
                            isEnabled ? 'bg-green-500' : 'bg-white/10'
                          }`}>
                            {isEnabled ? <Check className="w-4 h-4 text-white" /> : <X className="w-4 h-4 text-white/40" />}
                          </div>
                        </div>
                        <p className="text-xs text-white/50 mt-1">{strategy.description}</p>
                        <div className="flex items-center gap-4 mt-2">
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            strategy.risk === 'Low' ? 'bg-green-500/20 text-green-400' :
                            strategy.risk === 'Medium' ? 'bg-yellow-500/20 text-yellow-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {strategy.risk} Risk
                          </span>
                          <span className="text-xs text-white/40">Expected: {strategy.expectedReturn}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Asset Classes Section */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center">
                  <Layers className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Asset Classes</h3>
                  <p className="text-xs text-white/50">Select market categories to trade</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-white/60">{config.enabled_asset_classes?.length || 0}/{ASSET_CLASSES.length} enabled</span>
                <button onClick={selectAllAssetClasses} className="px-3 py-1 rounded-lg bg-white/10 text-white/60 text-xs hover:bg-white/20 transition">
                  Select All
                </button>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {ASSET_CLASSES.map((asset) => {
                const isEnabled = config.enabled_asset_classes?.includes(asset.id);
                const Icon = asset.icon;
                return (
                  <div
                    key={asset.id}
                    onClick={() => toggleAssetClass(asset.id)}
                    data-testid={`asset-${asset.id}`}
                    className={`relative p-4 rounded-xl border-2 cursor-pointer transition-all ${
                      isEnabled
                        ? `bg-${asset.color}-500/10 border-${asset.color}-500/50`
                        : 'bg-white/5 border-white/10 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        isEnabled ? `bg-${asset.color}-500/20` : 'bg-white/10'
                      }`}>
                        <Icon className={`w-5 h-5 ${isEnabled ? `text-${asset.color}-400` : 'text-white/40'}`} />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <h4 className={`font-semibold ${isEnabled ? 'text-white' : 'text-white/60'}`}>
                            {asset.label}
                          </h4>
                          <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
                            isEnabled ? 'bg-green-500' : 'bg-white/10'
                          }`}>
                            {isEnabled && <Check className="w-3 h-3 text-white" />}
                          </div>
                        </div>
                        <p className="text-xs text-white/50 mt-0.5">{asset.description}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Summary */}
          <div className="rounded-xl bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border border-white/10 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-6">
                <div>
                  <p className="text-xs text-white/50">Active Strategies</p>
                  <p className="text-lg font-bold text-cyan-400">{config.enabled_strategies?.length || 0}</p>
                </div>
                <div className="w-px h-8 bg-white/10" />
                <div>
                  <p className="text-xs text-white/50">Active Asset Classes</p>
                  <p className="text-lg font-bold text-purple-400">{config.enabled_asset_classes?.length || 0}</p>
                </div>
                <div className="w-px h-8 bg-white/10" />
                <div>
                  <p className="text-xs text-white/50">Trading Scope</p>
                  <p className="text-sm text-white/80">
                    {config.enabled_strategies?.join(', ').substring(0, 40)}...
                  </p>
                </div>
              </div>
              <div className="text-xs text-white/40">
                Changes apply to both Live Trading and Backtesting
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="rounded-xl bg-slate-800/50 border border-white/10 p-6">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Info className="w-4 h-4 text-cyan-400" />Configuration Tips</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="p-3 rounded-lg bg-white/5"><h4 className="text-cyan-400 font-medium mb-1">Conservative</h4><p className="text-white/50 text-xs">15% Kelly, 2% position, 3% drawdown</p></div>
          <div className="p-3 rounded-lg bg-white/5"><h4 className="text-yellow-400 font-medium mb-1">Balanced</h4><p className="text-white/50 text-xs">25% Kelly, 3% position, 5% drawdown</p></div>
          <div className="p-3 rounded-lg bg-white/5"><h4 className="text-red-400 font-medium mb-1">Aggressive</h4><p className="text-white/50 text-xs">50% Kelly, 5% position, 10% drawdown</p></div>
        </div>
      </div>
    </div>
  );
};

export default Configuration;
