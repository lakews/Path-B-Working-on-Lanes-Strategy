import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Settings, Save, RefreshCw, DollarSign, Percent, Activity, Shield, Zap, AlertTriangle, Target, Clock, Info, Sliders, Layers, TrendingUp, Landmark, Trophy, Film, Bitcoin, Globe, Check, X, BarChart3, GitBranch, Crosshair, Scale, Bell, BellOff, Sparkles, Brain, Database, Timer, Flame, Snowflake } from 'lucide-react';

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
  { id: 'delta_neutral', label: 'Delta-Neutral', icon: Scale, color: 'cyan', description: 'Market making with zero directional exposure, captures spreads', risk: 'Low', expectedReturn: '5-15%', riskMultiplier: 1.2, bestFor: 'High liquidity, wide spreads' },
  { id: 'volatility_exploitation', label: 'Volatility Exploitation', icon: Zap, color: 'yellow', description: 'Buy at extreme prices during volatility spikes', risk: 'High', expectedReturn: '30-100%+', riskMultiplier: 0.5, bestFor: 'Market panics, news events' },
  { id: 'alpha_directional', label: 'Alpha-Directional', icon: TrendingUp, color: 'green', description: 'Directional bets based on ML signals and sentiment', risk: 'Medium', expectedReturn: '10-30%', riskMultiplier: 0.8, bestFor: 'Clear sentiment, news-driven' },
  { id: 'arbitrage', label: 'Multi-Market Arbitrage', icon: GitBranch, color: 'purple', description: 'Exploit price discrepancies across similar markets', risk: 'Low', expectedReturn: '2-5%', riskMultiplier: 1.1, bestFor: 'Correlated markets, stale prices' },
];

const Configuration = () => {
  const [config, setConfig] = useState({
    trades_per_10min: 500,
    initial_capital: 10000,
    capital_deployment_pct: 80,
    max_position_size_pct: 3,
    kelly_fraction: 0.25,
    kelly_enabled: true,
    max_drawdown_pct: 5,
    min_liquidity: 100,
    max_liquidity: 1000000,
    min_volume_24h: 1000,
    max_spread: 0.25,
    max_open_positions: 50,
    stuck_price_multiplier: 2.0,
    enabled_asset_classes: ['finance', 'politics', 'sports', 'crypto', 'entertainment', 'science'],
    enabled_strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage'],
    // Exit parameters per strategy
    exit_params: {
      delta_neutral: { take_profit: 0.02, stop_loss: -0.02, max_hours: 4 },
      volatility_exploitation: { take_profit: 0.05, stop_loss: -0.05, max_hours: 8 },
      alpha_directional: { take_profit: 0.08, stop_loss: -0.05, max_hours: 12 },
      arbitrage: { take_profit: 0.03, stop_loss: -0.03, max_hours: 6 }
    },
    // Asset class exit multipliers
    asset_class_exit_multipliers: {
      crypto: { tp_mult: 1.5, sl_mult: 1.3, time_mult: 0.5 },
      politics: { tp_mult: 1.2, sl_mult: 1.0, time_mult: 1.5 },
      sports: { tp_mult: 1.0, sl_mult: 0.8, time_mult: 0.25 },
      finance: { tp_mult: 0.8, sl_mult: 0.8, time_mult: 1.0 },
      entertainment: { tp_mult: 1.0, sl_mult: 1.0, time_mult: 1.0 },
      science: { tp_mult: 1.0, sl_mult: 1.0, time_mult: 2.0 }
    },
    // Advanced position sizing
    min_kelly_fraction: 0.10,
    max_kelly_fraction: 0.50,
    min_position_size: 5,
    min_liquidity_for_full_size: 10000,
    // Market alerts
    alerts_enabled: false,
    alert_volume_threshold: 2.0,
    // Position Sizer
    use_polymarket_sizer: true,
    polymarket_fee_pct: 0.02,
    sector_caps: {
      crypto: 0.20, politics: 0.25, sports: 0.30, finance: 0.20,
      entertainment: 0.15, science: 0.15, conflict: 0.10, social: 0.10, unknown: 0.15
    },
    oracle_multipliers: null,
    // Event Caps
    event_caps: {
      max_event_exposure_pct: 0.15,
      similarity_threshold: 0.60
    },
    // HFT vs Alpha Capital Allocation (Two-Speed Architecture)
    hft_allocation_pct: 40,       // % of deployed capital to HFT path
    alpha_allocation_pct: 60,     // % of deployed capital to Alpha path
    hft_max_position_pct: 10,     // Max position size as % of HFT capital
    alpha_max_position_pct: 25,   // Max position size as % of Alpha capital
    hft_positions_pct: 5,         // % of global max positions for HFT per market
    alpha_positions_pct: 2,       // % of global max positions for Alpha per market
  });
  const [oracleMultipliersDefault, setOracleMultipliersDefault] = useState({});
  const [eventCapsDefault, setEventCapsDefault] = useState({
    max_event_exposure_pct: 0.15,
    similarity_threshold: 0.60
  });
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('trading');
  const [useDynamicExit, setUseDynamicExit] = useState(true);
  
  // LLM Cache state
  const [llmStats, setLlmStats] = useState(null);
  const [llmConfig, setLlmConfig] = useState({
    hot_market_ttl_seconds: 600,
    cold_market_ttl_seconds: 3600,
    hot_market_volume_threshold: 50000,
    llm_timeout_seconds: 10,
    estimated_cost_per_call: 0.002
  });
  const [llmConfigInfo, setLlmConfigInfo] = useState({});
  const [savingLlmConfig, setSavingLlmConfig] = useState(false);


  useEffect(() => { fetchConfig(); fetchStatus(); fetchExitMode(); fetchLlmStats(); }, []);
  
  // Fetch exit mode from API
  const fetchExitMode = async () => {
    try {
      const response = await axios.get(`${API}/paper/exit-mode`);
      setUseDynamicExit(response.data?.use_dynamic_exit ?? true);
    } catch (e) { console.error('Error fetching exit mode:', e); }
  };
  
  // Fetch LLM cache stats and config
  const fetchLlmStats = async () => {
    try {
      const [statsRes, configRes] = await Promise.all([
        axios.get(`${API}/sentiment/llm/stats`),
        axios.get(`${API}/sentiment/llm/config`)
      ]);
      setLlmStats(statsRes.data);
      if (configRes.data?.config) {
        setLlmConfig(configRes.data.config);
      }
      if (configRes.data?.config_info) {
        setLlmConfigInfo(configRes.data.config_info);
      }
    } catch (e) { console.error('Error fetching LLM stats:', e); }
  };
  
  // Save LLM config
  const saveLlmConfig = async () => {
    setSavingLlmConfig(true);
    try {
      const response = await axios.post(`${API}/sentiment/llm/config`, llmConfig);
      toast.success(response.data?.message || 'LLM config saved');
      fetchLlmStats(); // Refresh stats
    } catch (e) { 
      toast.error('Failed to save LLM config');
    } finally {
      setSavingLlmConfig(false);
    }
  };
  
  // Toggle exit mode
  const toggleExitMode = async () => {
    try {
      const newMode = !useDynamicExit;
      const response = await axios.post(`${API}/paper/exit-mode?use_dynamic=${newMode}`);
      setUseDynamicExit(newMode);
      toast.success(response.data?.message || `Exit mode: ${newMode ? 'Dynamic' : 'Simple'}`);
    } catch (e) { 
      toast.error('Failed to toggle exit mode. Start a paper trading session first.'); 
    }
  };

  const fetchStatus = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setStatus(response.data);
    } catch (e) { console.error('Error fetching status:', e); }
  };

  const fetchConfig = async () => {
    try {
      // Fetch saved config from server
      const response = await axios.get(`${API}/config`);
      const savedConfig = response.data;
      
      // Store default oracle multipliers
      if (savedConfig.oracle_multipliers_default) {
        setOracleMultipliersDefault(savedConfig.oracle_multipliers_default);
      }
      
      // Store default event caps
      if (savedConfig.event_caps_default) {
        setEventCapsDefault(savedConfig.event_caps_default);
      }
      
      // Merge saved config with current state - DB is source of truth
      setConfig(prev => ({
        ...prev,
        trades_per_10min: savedConfig.trades_per_10min ?? prev.trades_per_10min,
        initial_capital: savedConfig.initial_capital ?? prev.initial_capital,
        capital_deployment_pct: savedConfig.capital_deployment_pct ?? prev.capital_deployment_pct,
        max_position_size_pct: savedConfig.max_position_size_pct ?? prev.max_position_size_pct,
        kelly_fraction: savedConfig.kelly_fraction ?? prev.kelly_fraction,
        kelly_enabled: savedConfig.kelly_enabled ?? prev.kelly_enabled,
        max_drawdown_pct: savedConfig.max_drawdown_pct ?? prev.max_drawdown_pct,
        min_liquidity: savedConfig.min_liquidity ?? prev.min_liquidity,
        max_liquidity: savedConfig.max_liquidity ?? prev.max_liquidity,
        min_volume_24h: savedConfig.min_volume_24h ?? prev.min_volume_24h,
        max_spread: savedConfig.max_spread ?? prev.max_spread,
        max_open_positions: savedConfig.max_open_positions ?? prev.max_open_positions,
        stuck_price_multiplier: savedConfig.stuck_price_multiplier ?? prev.stuck_price_multiplier,
        enabled_asset_classes: savedConfig.enabled_asset_classes ?? prev.enabled_asset_classes,
        enabled_strategies: savedConfig.enabled_strategies ?? prev.enabled_strategies,
        exit_params: savedConfig.exit_params ?? prev.exit_params,
        asset_class_exit_multipliers: savedConfig.asset_class_exit_multipliers ?? prev.asset_class_exit_multipliers,
        min_kelly_fraction: savedConfig.min_kelly_fraction ?? prev.min_kelly_fraction,
        max_kelly_fraction: savedConfig.max_kelly_fraction ?? prev.max_kelly_fraction,
        min_position_size: savedConfig.min_position_size ?? prev.min_position_size,
        min_liquidity_for_full_size: savedConfig.min_liquidity_for_full_size ?? prev.min_liquidity_for_full_size,
        alerts_enabled: savedConfig.alerts_enabled ?? prev.alerts_enabled,
        alert_volume_threshold: savedConfig.alert_volume_threshold ?? prev.alert_volume_threshold,
        // Position Sizer fields
        use_polymarket_sizer: savedConfig.use_polymarket_sizer ?? prev.use_polymarket_sizer,
        polymarket_fee_pct: savedConfig.polymarket_fee_pct ?? prev.polymarket_fee_pct,
        sector_caps: savedConfig.sector_caps ?? prev.sector_caps,
        oracle_multipliers: savedConfig.oracle_multipliers ?? prev.oracle_multipliers,
        // Event Caps
        event_caps: savedConfig.event_caps ?? prev.event_caps,
        // HFT vs Alpha Capital Allocation
        hft_allocation_pct: savedConfig.hft_allocation_pct ?? prev.hft_allocation_pct,
        alpha_allocation_pct: savedConfig.alpha_allocation_pct ?? prev.alpha_allocation_pct,
        hft_max_position_pct: savedConfig.hft_max_position_pct ?? prev.hft_max_position_pct,
        alpha_max_position_pct: savedConfig.alpha_max_position_pct ?? prev.alpha_max_position_pct,
        hft_positions_pct: savedConfig.hft_positions_pct ?? prev.hft_positions_pct,
        alpha_positions_pct: savedConfig.alpha_positions_pct ?? prev.alpha_positions_pct,
      }));
      setLoading(false);
    } catch (e) { 
      console.error('Error fetching config:', e);
      setLoading(false); 
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/config/update`, config);
      toast.success('Configuration updated!');
      fetchConfig();  // Refresh config after save
    } catch (e) { toast.error('Failed to update'); }
    finally { setSaving(false); }
  };

  const resetToDefaults = () => {
    setConfig({
      trades_per_10min: 500,
      initial_capital: 10000,
      capital_deployment_pct: 80,
      max_position_size_pct: 3,
      kelly_fraction: 0.25,
      kelly_enabled: true,
      max_drawdown_pct: 5,
      min_liquidity: 100,
      max_liquidity: 1000000,
      min_volume_24h: 1000,
      max_spread: 0.25,
      max_open_positions: 50,
      stuck_price_multiplier: 2.0,
      enabled_asset_classes: ['finance', 'politics', 'sports', 'crypto', 'entertainment', 'science'],
      enabled_strategies: ['delta_neutral', 'volatility_exploitation', 'alpha_directional', 'arbitrage'],
      exit_params: {
        delta_neutral: { take_profit: 0.02, stop_loss: -0.02, max_hours: 4 },
        volatility_exploitation: { take_profit: 0.05, stop_loss: -0.05, max_hours: 8 },
        alpha_directional: { take_profit: 0.08, stop_loss: -0.05, max_hours: 12 },
        arbitrage: { take_profit: 0.03, stop_loss: -0.03, max_hours: 6 }
      },
      asset_class_exit_multipliers: {
        crypto: { tp_mult: 1.5, sl_mult: 1.3, time_mult: 0.5 },
        politics: { tp_mult: 1.2, sl_mult: 1.0, time_mult: 1.5 },
        sports: { tp_mult: 1.0, sl_mult: 0.8, time_mult: 0.25 },
        finance: { tp_mult: 0.8, sl_mult: 0.8, time_mult: 1.0 },
        entertainment: { tp_mult: 1.0, sl_mult: 1.0, time_mult: 1.0 },
        science: { tp_mult: 1.0, sl_mult: 1.0, time_mult: 2.0 }
      },
      min_kelly_fraction: 0.10,
      max_kelly_fraction: 0.50,
      min_position_size: 5,
      min_liquidity_for_full_size: 10000,
      alerts_enabled: false,
      alert_volume_threshold: 2.0,
      // Position Sizer
      use_polymarket_sizer: true,
      polymarket_fee_pct: 0.02,
      sector_caps: {
        crypto: 0.20, politics: 0.25, sports: 0.30, finance: 0.20,
        entertainment: 0.15, science: 0.15, conflict: 0.10, social: 0.10, unknown: 0.15
      },
      // Event Caps
      event_caps: {
        max_event_exposure_pct: 0.15,
        similarity_threshold: 0.60
      },
      // HFT vs Alpha Capital Allocation
      hft_allocation_pct: 40,
      alpha_allocation_pct: 60,
      hft_max_position_pct: 10,
      alpha_max_position_pct: 25,
      hft_positions_pct: 5,
      alpha_positions_pct: 2,
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

      <div className="flex gap-2 bg-white/5 p-1 rounded-xl w-fit flex-wrap">
        {[{ id: 'trading', label: 'Trading', icon: Activity }, { id: 'capital', label: 'Capital', icon: DollarSign }, { id: 'risk', label: 'Risk', icon: Shield }, { id: 'sizer', label: 'Position Sizer', icon: Scale }, { id: 'llm', label: 'LLM Cache', icon: Brain }, { id: 'markets', label: 'Market Selection', icon: Target }, { id: 'exits', label: 'Exit Parameters', icon: Target }, { id: 'assetmult', label: 'Asset Multipliers', icon: Sliders }, { id: 'thresholds', label: 'Strategy Thresholds', icon: Crosshair }, { id: 'advanced', label: 'Advanced', icon: Settings }, { id: 'alerts', label: 'Alerts', icon: Bell }, { id: 'assets', label: 'Asset Class - Strategy', icon: Layers }].map((tab) => (
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

          {/* HFT vs Alpha Capital Allocation - Two Speed Architecture */}
          <div className="lg:col-span-2 rounded-xl bg-gradient-to-br from-orange-500/10 to-purple-500/10 border border-orange-500/30 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-orange-500/30 to-purple-500/30 flex items-center justify-center">
                <Zap className="w-5 h-5 text-orange-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Two-Speed Architecture</h3>
                <p className="text-xs text-white/50">Split capital between HFT (Fast) and Alpha (Slow) paths</p>
              </div>
            </div>
            
            {/* Info note about per-market vs global */}
            <div className="mb-4 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-start gap-2">
              <Info className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-blue-300">
                <strong>Per-Market Limits</strong> control positions within each market. 
                <strong> Global Caps</strong> (Risk tab: {config.max_position_size_pct}% = ${maxPositionValue.toFixed(2)}/trade, Market Selection: {config.max_open_positions} total) override strategy limits.
              </p>
            </div>
            
            {/* Main Allocation Slider */}
            <div className="mb-6">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-orange-400 font-medium flex items-center gap-1"><Flame className="w-4 h-4" /> HFT (Fast Path)</span>
                <span className="text-purple-400 font-medium flex items-center gap-1"><Snowflake className="w-4 h-4" /> Alpha (Slow Path)</span>
              </div>
              <div className="relative">
                <input 
                  type="range" 
                  value={config.hft_allocation_pct || 40} 
                  onChange={(e) => {
                    const hft = parseInt(e.target.value);
                    setConfig({...config, hft_allocation_pct: hft, alpha_allocation_pct: 100 - hft});
                  }} 
                  className="w-full h-3 bg-gradient-to-r from-orange-500/30 to-purple-500/30 rounded-lg appearance-none cursor-pointer" 
                  min="0" max="100" step="5" 
                />
                <div className="flex justify-between mt-1">
                  <span className="text-orange-400 font-bold text-lg">{config.hft_allocation_pct}%</span>
                  <span className="text-purple-400 font-bold text-lg">{config.alpha_allocation_pct}%</span>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-2 mt-3">
                {[{hft: 0, label: 'Alpha Only'}, {hft: 25, label: '25/75'}, {hft: 40, label: '40/60'}, {hft: 60, label: '60/40'}, {hft: 100, label: 'HFT Only'}].map(({hft, label}) => (
                  <button 
                    key={hft} 
                    onClick={() => setConfig({...config, hft_allocation_pct: hft, alpha_allocation_pct: 100 - hft})} 
                    className={`px-2 py-1 rounded-lg text-xs font-medium transition ${config.hft_allocation_pct === hft ? 'bg-gradient-to-r from-orange-500 to-purple-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* HFT and Alpha Details Side by Side */}
            <div className="grid grid-cols-2 gap-4">
              {/* HFT Column */}
              <div className="p-4 rounded-lg bg-orange-500/10 border border-orange-500/20">
                <div className="flex items-center gap-2 mb-3">
                  <Flame className="w-4 h-4 text-orange-400" />
                  <span className="text-orange-400 font-semibold text-sm">HFT Path (Fast)</span>
                </div>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-white/50 mb-1">Capital</p>
                    <p className="text-lg font-bold text-orange-400">${(deployedCapital * (config.hft_allocation_pct || 40) / 100).toFixed(2)}</p>
                  </div>
                  <div>
                    <div className="flex justify-between text-xs text-white/50 mb-1">
                      <span>Max Position %</span>
                      <span className="text-orange-300">{config.hft_max_position_pct}%</span>
                    </div>
                    <input 
                      type="range" 
                      value={config.hft_max_position_pct || 10} 
                      onChange={(e) => setConfig({...config, hft_max_position_pct: parseInt(e.target.value)})} 
                      className="w-full h-1.5 bg-white/10 rounded-lg" 
                      min="1" max="50" step="1" 
                    />
                    {(() => {
                      const hftCapital = deployedCapital * (config.hft_allocation_pct || 40) / 100;
                      const strategyMax = hftCapital * (config.hft_max_position_pct || 10) / 100;
                      const globalMax = maxPositionValue;
                      const effectiveMax = Math.min(strategyMax, globalMax);
                      const isCapped = strategyMax > globalMax;
                      return (
                        <div className="mt-1">
                          <p className={`text-xs ${isCapped ? 'text-yellow-400' : 'text-white/40'}`}>
                            {isCapped 
                              ? `Capped by global: $${effectiveMax.toFixed(2)} (global ${config.max_position_size_pct}% = $${globalMax.toFixed(2)})`
                              : `Max: $${effectiveMax.toFixed(2)}/trade`
                            }
                          </p>
                        </div>
                      );
                    })()}
                  </div>
                  <div>
                    <div className="flex justify-between text-xs text-white/50 mb-1">
                      <span>Positions Per Market</span>
                      <span className="text-orange-300">{config.hft_positions_pct}% = <strong>{Math.max(1, Math.round((config.max_open_positions || 50) * (config.hft_positions_pct || 5) / 100))}</strong></span>
                    </div>
                    <input 
                      type="range" 
                      value={config.hft_positions_pct || 5} 
                      onChange={(e) => setConfig({...config, hft_positions_pct: parseInt(e.target.value)})} 
                      className="w-full h-1.5 bg-white/10 rounded-lg" 
                      min="1" max="50" step="1" 
                    />
                    <p className="text-xs text-white/40 mt-1">{config.hft_positions_pct}% of {config.max_open_positions || 50} global max</p>
                  </div>
                </div>
                <div className="mt-3 p-2 rounded bg-orange-500/10 text-xs text-orange-300">
                  <p>Market making, inventory skew, OFI-based quotes</p>
                </div>
              </div>

              {/* Alpha Column */}
              <div className="p-4 rounded-lg bg-purple-500/10 border border-purple-500/20">
                <div className="flex items-center gap-2 mb-3">
                  <Snowflake className="w-4 h-4 text-purple-400" />
                  <span className="text-purple-400 font-semibold text-sm">Alpha Path (Slow)</span>
                </div>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-white/50 mb-1">Capital</p>
                    <p className="text-lg font-bold text-purple-400">${(deployedCapital * (config.alpha_allocation_pct || 60) / 100).toFixed(2)}</p>
                  </div>
                  <div>
                    <div className="flex justify-between text-xs text-white/50 mb-1">
                      <span>Max Position %</span>
                      <span className="text-purple-300">{config.alpha_max_position_pct}%</span>
                    </div>
                    <input 
                      type="range" 
                      value={config.alpha_max_position_pct || 25} 
                      onChange={(e) => setConfig({...config, alpha_max_position_pct: parseInt(e.target.value)})} 
                      className="w-full h-1.5 bg-white/10 rounded-lg" 
                      min="1" max="100" step="1" 
                    />
                    {(() => {
                      const alphaCapital = deployedCapital * (config.alpha_allocation_pct || 60) / 100;
                      const strategyMax = alphaCapital * (config.alpha_max_position_pct || 25) / 100;
                      const globalMax = maxPositionValue;
                      const effectiveMax = Math.min(strategyMax, globalMax);
                      const isCapped = strategyMax > globalMax;
                      return (
                        <div className="mt-1">
                          <p className={`text-xs ${isCapped ? 'text-yellow-400' : 'text-white/40'}`}>
                            {isCapped 
                              ? `Capped by global: $${effectiveMax.toFixed(2)} (global ${config.max_position_size_pct}% = $${globalMax.toFixed(2)})`
                              : `Max: $${effectiveMax.toFixed(2)}/trade`
                            }
                          </p>
                        </div>
                      );
                    })()}
                  </div>
                  <div>
                    <div className="flex justify-between text-xs text-white/50 mb-1">
                      <span>Positions Per Market</span>
                      <span className="text-purple-300">{config.alpha_positions_pct}% = <strong>{Math.max(1, Math.round((config.max_open_positions || 50) * (config.alpha_positions_pct || 2) / 100))}</strong></span>
                    </div>
                    <input 
                      type="range" 
                      value={config.alpha_positions_pct || 2} 
                      onChange={(e) => setConfig({...config, alpha_positions_pct: parseInt(e.target.value)})} 
                      className="w-full h-1.5 bg-white/10 rounded-lg" 
                      min="1" max="25" step="1" 
                    />
                    <p className="text-xs text-white/40 mt-1">{config.alpha_positions_pct}% of {config.max_open_positions || 50} global max</p>
                  </div>
                </div>
                <div className="mt-3 p-2 rounded bg-purple-500/10 text-xs text-purple-300">
                  <p>ML/LLM sentiment, Bayesian posterior, directional</p>
                </div>
              </div>
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
          {/* Kelly Criterion Section with Toggle */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center"><Target className="w-5 h-5 text-purple-400" /></div>
                <div><h3 className="text-white font-semibold">Kelly Criterion</h3><p className="text-xs text-white/50">Position sizing based on edge</p></div>
              </div>
              {/* Kelly Enable Toggle */}
              <button
                onClick={() => setConfig({...config, kelly_enabled: !config.kelly_enabled})}
                data-testid="kelly-toggle"
                className={`relative w-14 h-7 rounded-full transition-colors ${config.kelly_enabled ? 'bg-purple-500' : 'bg-white/20'}`}
              >
                <div className={`absolute w-5 h-5 bg-white rounded-full top-1 transition-transform ${config.kelly_enabled ? 'translate-x-8' : 'translate-x-1'}`} />
              </button>
            </div>
            {config.kelly_enabled ? (
              <>
                <p className="text-xs text-purple-400 mb-3">Kelly Fraction determines position sizing based on historical win rate</p>
                <div className="flex items-center gap-4">
                  <input type="range" value={config.kelly_fraction || 0.25} onChange={(e) => setConfig({...config, kelly_fraction: parseFloat(e.target.value)})} className="flex-1 h-2 bg-white/10 rounded-lg" min="0.10" max="0.50" step="0.05" />
                  <span className="text-white font-bold text-xl w-16 text-right">{(config.kelly_fraction * 100).toFixed(0)}%</span>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-4">
                  {[{ val: 0.15, label: 'Conservative' }, { val: 0.25, label: 'Moderate' }, { val: 0.50, label: 'Aggressive' }].map(({ val, label }) => (
                    <button key={val} onClick={() => setConfig({...config, kelly_fraction: val})} className={`px-3 py-2 rounded-lg text-sm font-medium transition ${config.kelly_fraction === val ? 'bg-purple-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}>{label}</button>
                  ))}
                </div>
              </>
            ) : (
              <div className="p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                <p className="text-sm text-yellow-400">Kelly disabled - using fixed position sizing</p>
                <p className="text-xs text-white/50 mt-1">Positions will be sized at 30% of max position without adaptive edge-based scaling</p>
              </div>
            )}
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

      {/* Position Sizer Tab - NEW */}
      {activeTab === 'sizer' && (
        <div className="space-y-6">
          {/* Sizer Mode Toggle */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-xl bg-gradient-to-br from-cyan-500/10 to-purple-500/10 border border-cyan-500/30 p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center">
                    <Scale className="w-5 h-5 text-cyan-400" />
                  </div>
                  <div>
                    <h3 className="text-white font-semibold">Position Sizer Mode</h3>
                    <p className="text-xs text-white/50">Dynamic vs Simple sizing</p>
                  </div>
                </div>
                <button
                  onClick={() => setConfig({...config, use_polymarket_sizer: !config.use_polymarket_sizer})}
                  data-testid="sizer-mode-toggle"
                  className={`relative w-16 h-8 rounded-full transition-colors ${config.use_polymarket_sizer ? 'bg-cyan-500' : 'bg-white/20'}`}
                >
                  <div className={`absolute w-6 h-6 bg-white rounded-full top-1 transition-transform ${config.use_polymarket_sizer ? 'translate-x-9' : 'translate-x-1'}`} />
                </button>
              </div>
              <div className={`p-4 rounded-lg ${config.use_polymarket_sizer ? 'bg-cyan-500/10 border border-cyan-500/20' : 'bg-gray-500/10 border border-gray-500/20'}`}>
                <p className="text-sm font-semibold text-white mb-2">{config.use_polymarket_sizer ? '🚀 Dynamic Sizer (Recommended)' : '📏 Simple Sizer (Legacy)'}</p>
                <p className="text-xs text-white/60">
                  {config.use_polymarket_sizer 
                    ? 'Uses Binary Kelly, Utilization Brake, Oracle Risk, Time Penalty, Correlation Dampening, and Sector Caps.'
                    : 'Fixed position sizing based on max_position_size_pct without adaptive factors.'}
                </p>
              </div>
            </div>

            {/* Fee Configuration */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
                  <Percent className="w-5 h-5 text-amber-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Polymarket Fee</h3>
                  <p className="text-xs text-white/50">Exit fee for effective price calculation</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <input 
                  type="range" 
                  value={(config.polymarket_fee_pct || 0.02) * 100} 
                  onChange={(e) => setConfig({...config, polymarket_fee_pct: parseFloat(e.target.value) / 100})} 
                  className="flex-1 h-2 bg-white/10 rounded-lg" 
                  min="0" max="5" step="0.5" 
                />
                <span className="text-white font-bold text-xl w-16 text-right">{((config.polymarket_fee_pct || 0.02) * 100).toFixed(1)}%</span>
              </div>
              <p className="text-xs text-white/40 mt-2">Effective Price = Ask + (Ask × Fee%). Default: 2%</p>
            </div>
          </div>

          {/* Oracle Risk Multipliers */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Oracle Risk Multipliers</h3>
                  <p className="text-xs text-white/50">Size reduction by market category (higher = less risk)</p>
                </div>
              </div>
              <button 
                onClick={() => setConfig({...config, oracle_multipliers: null})}
                className="px-3 py-1.5 rounded-lg bg-white/5 text-white/60 hover:text-white hover:bg-white/10 transition text-xs"
              >
                Reset to Defaults
              </button>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {Object.entries(oracleMultipliersDefault).map(([category, defaultVal]) => {
                const currentVal = config.oracle_multipliers?.[category] ?? defaultVal;
                const isModified = config.oracle_multipliers?.[category] !== undefined;
                const riskColor = currentVal >= 0.9 ? 'emerald' : currentVal >= 0.7 ? 'yellow' : currentVal >= 0.5 ? 'orange' : 'red';
                
                return (
                  <div key={category} className={`p-3 rounded-lg ${isModified ? 'bg-purple-500/10 border border-purple-500/30' : 'bg-white/5 border border-white/10'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-white/60 capitalize">{category.replace('_', ' ')}</span>
                      <span className={`text-xs font-mono text-${riskColor}-400`}>×{currentVal.toFixed(2)}</span>
                    </div>
                    <input 
                      type="range" 
                      value={currentVal * 100} 
                      onChange={(e) => {
                        const newVal = parseFloat(e.target.value) / 100;
                        setConfig(prev => ({
                          ...prev,
                          oracle_multipliers: {
                            ...(prev.oracle_multipliers || oracleMultipliersDefault),
                            [category]: newVal
                          }
                        }));
                      }}
                      className="w-full h-1.5 bg-white/10 rounded-lg" 
                      min="10" max="100" step="5" 
                    />
                    <div className="flex justify-between mt-1">
                      <span className="text-[9px] text-white/30">Risky</span>
                      <span className="text-[9px] text-white/30">Safe</span>
                    </div>
                  </div>
                );
              })}
            </div>
            
            <div className="mt-4 p-3 rounded-lg bg-white/5 border border-white/10">
              <p className="text-xs text-white/50">
                <strong className="text-white/80">How it works:</strong> Lower multipliers (0.4-0.6) heavily reduce position sizes for ambiguous markets like conflict/social. 
                Higher multipliers (0.9-1.0) allow full sizing for clear-cut markets like sports/crypto with oracle-resolvable outcomes.
              </p>
            </div>
          </div>

          {/* Sector Caps */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Sector Caps</h3>
                <p className="text-xs text-white/50">Maximum portfolio allocation per category</p>
              </div>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              {Object.entries(config.sector_caps || {}).map(([sector, cap]) => (
                <div key={sector} className="p-3 rounded-lg bg-white/5 border border-white/10">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-white/60 capitalize">{sector}</span>
                    <span className="text-xs font-mono text-blue-400">{(cap * 100).toFixed(0)}%</span>
                  </div>
                  <input 
                    type="range" 
                    value={(cap || 0.15) * 100} 
                    onChange={(e) => {
                      const newVal = parseFloat(e.target.value) / 100;
                      setConfig(prev => ({
                        ...prev,
                        sector_caps: {
                          ...prev.sector_caps,
                          [sector]: newVal
                        }
                      }));
                    }}
                    className="w-full h-1.5 bg-white/10 rounded-lg" 
                    min="5" max="50" step="5" 
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Event Caps */}
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                  <Layers className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Event Caps</h3>
                  <p className="text-xs text-white/50">Limit exposure to correlated markets (same event)</p>
                </div>
              </div>
              <button
                onClick={() => setConfig(prev => ({
                  ...prev,
                  event_caps: { ...eventCapsDefault }
                }))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/70 hover:text-white text-xs transition"
                title="Reset to defaults"
              >
                <RefreshCw className="w-3 h-3" />
                Reset
              </button>
            </div>
            
            {/* Info box explaining event caps */}
            <div className="rounded-lg bg-purple-500/10 border border-purple-500/20 p-3 mb-4">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-white/70">
                  <p className="mb-1">Event caps prevent over-concentration in correlated markets.</p>
                  <p className="text-white/50">Example: "Bitcoin $100k" and "Bitcoin $150k" are the same event - exposure is combined.</p>
                </div>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Max Event Exposure */}
              <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <span className="text-sm text-white/80 font-medium">Max Per Event</span>
                    <p className="text-xs text-white/40 mt-0.5">Maximum exposure to correlated markets</p>
                  </div>
                  <span className="text-lg font-mono text-purple-400">
                    {((config.event_caps?.max_event_exposure_pct || 0.15) * 100).toFixed(0)}%
                  </span>
                </div>
                <input 
                  type="range" 
                  value={(config.event_caps?.max_event_exposure_pct || 0.15) * 100} 
                  onChange={(e) => {
                    const newVal = parseFloat(e.target.value) / 100;
                    setConfig(prev => ({
                      ...prev,
                      event_caps: {
                        ...prev.event_caps,
                        max_event_exposure_pct: newVal
                      }
                    }));
                  }}
                  className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer" 
                  min="5" max="30" step="1" 
                />
                <div className="flex justify-between text-xs text-white/30 mt-1">
                  <span>5%</span>
                  <span>Conservative</span>
                  <span>30%</span>
                </div>
              </div>
              
              {/* Similarity Threshold */}
              <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <span className="text-sm text-white/80 font-medium">Similarity Threshold</span>
                    <p className="text-xs text-white/40 mt-0.5">Word overlap % to group as same event</p>
                  </div>
                  <span className="text-lg font-mono text-purple-400">
                    {((config.event_caps?.similarity_threshold || 0.60) * 100).toFixed(0)}%
                  </span>
                </div>
                <input 
                  type="range" 
                  value={(config.event_caps?.similarity_threshold || 0.60) * 100} 
                  onChange={(e) => {
                    const newVal = parseFloat(e.target.value) / 100;
                    setConfig(prev => ({
                      ...prev,
                      event_caps: {
                        ...prev.event_caps,
                        similarity_threshold: newVal
                      }
                    }));
                  }}
                  className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer" 
                  min="40" max="80" step="5" 
                />
                <div className="flex justify-between text-xs text-white/30 mt-1">
                  <span>40%</span>
                  <span>Broad matching</span>
                  <span>80%</span>
                </div>
              </div>
            </div>
            
            {/* Current settings summary */}
            <div className="mt-4 p-3 rounded-lg bg-white/5 border border-white/5">
              <div className="flex items-center gap-2 text-xs text-white/50">
                <Target className="w-3 h-3" />
                <span>
                  Markets with &gt;{((config.event_caps?.similarity_threshold || 0.60) * 100).toFixed(0)}% question similarity share a combined {((config.event_caps?.max_event_exposure_pct || 0.15) * 100).toFixed(0)}% exposure limit
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* LLM Cache Analytics Tab */}
      {activeTab === 'llm' && (
        <div className="space-y-6">
          {/* Header with refresh button */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center">
                <Brain className="w-6 h-6 text-purple-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">LLM Smart-Cache Analytics</h2>
                <p className="text-sm text-white/50">Hybrid caching based on market activity</p>
              </div>
            </div>
            <button onClick={fetchLlmStats} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm transition">
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>

          {/* How it works info box */}
          <div className="rounded-xl bg-gradient-to-r from-purple-500/20 to-cyan-500/20 border border-purple-500/30 p-4">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-purple-400 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-white/80">
                <p className="font-semibold text-purple-300 mb-1">Hybrid Smart-Cache Strategy</p>
                <ul className="space-y-1 text-white/70">
                  <li className="flex items-center gap-2">
                    <Flame className="w-3 h-3 text-orange-400" />
                    <span><strong className="text-orange-400">Hot Markets</strong> (high volume): Shorter cache TTL to catch breaking news</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Snowflake className="w-3 h-3 text-cyan-400" />
                    <span><strong className="text-cyan-400">Cold Markets</strong> (low volume): Longer cache TTL to save API costs</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Shield className="w-3 h-3 text-green-400" />
                    <span><strong className="text-green-400">Safety</strong>: Returns neutral (0.5, 0.0) on errors → zero weight in fusion</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Cache Hit Rate */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Database className="w-4 h-4 text-cyan-400" />
                <span className="text-xs text-white/50">Cache Hit Rate</span>
              </div>
              <div className="text-2xl font-bold text-white">
                {llmStats?.stats?.hit_rate !== undefined ? `${(llmStats.stats.hit_rate * 100).toFixed(1)}%` : '-'}
              </div>
              <div className="text-xs text-white/40 mt-1">
                {llmStats?.stats?.hits || 0} hits / {llmStats?.stats?.total_requests || 0} requests
              </div>
            </div>

            {/* Cache Size */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Layers className="w-4 h-4 text-purple-400" />
                <span className="text-xs text-white/50">Cache Size</span>
              </div>
              <div className="text-2xl font-bold text-white">
                {llmStats?.stats?.cache_size || 0}
              </div>
              <div className="flex gap-2 mt-1">
                <span className="text-xs text-orange-400">{llmStats?.stats?.hot_markets_cached || 0} hot</span>
                <span className="text-xs text-cyan-400">{llmStats?.stats?.cold_markets_cached || 0} cold</span>
              </div>
            </div>

            {/* Cost Spent */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className="w-4 h-4 text-red-400" />
                <span className="text-xs text-white/50">Est. Cost Spent</span>
              </div>
              <div className="text-2xl font-bold text-white">
                ${llmStats?.stats?.estimated_cost_spent?.toFixed(4) || '0.00'}
              </div>
              <div className="text-xs text-white/40 mt-1">
                {llmStats?.stats?.api_calls_made || 0} API calls
              </div>
            </div>

            {/* Cost Saved */}
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-4 h-4 text-green-400" />
                <span className="text-xs text-white/50">Est. Cost Saved</span>
              </div>
              <div className="text-2xl font-bold text-green-400">
                ${llmStats?.stats?.estimated_cost_saved?.toFixed(4) || '0.00'}
              </div>
              <div className="text-xs text-white/40 mt-1">
                {llmStats?.stats?.api_calls_saved || 0} calls avoided
              </div>
            </div>
          </div>

          {/* Configuration */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Hot Market Settings */}
            <div className="rounded-xl bg-white/5 border border-orange-500/30 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-lg bg-orange-500/20 flex items-center justify-center">
                  <Flame className="w-5 h-5 text-orange-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Hot Markets</h3>
                  <p className="text-xs text-white/50">High-volume market settings</p>
                </div>
              </div>
              
              {/* Volume Threshold */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-white/60 flex items-center gap-1">
                    Volume Threshold
                    <span className="group relative">
                      <Info className="w-3 h-3 text-white/30 cursor-help" />
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-black/90 text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap transition pointer-events-none">
                        Markets above this 24h volume are "hot"
                      </span>
                    </span>
                  </label>
                  <span className="text-orange-400 font-bold">${(llmConfig.hot_market_volume_threshold || 50000).toLocaleString()}</span>
                </div>
                <input 
                  type="range" 
                  value={llmConfig.hot_market_volume_threshold || 50000} 
                  onChange={(e) => setLlmConfig({...llmConfig, hot_market_volume_threshold: parseInt(e.target.value)})}
                  className="w-full h-2 bg-white/10 rounded-lg accent-orange-500" 
                  min="10000" max="500000" step="10000" 
                />
                <div className="flex justify-between text-xs text-white/30 mt-1">
                  <span>$10k</span>
                  <span>$500k</span>
                </div>
              </div>

              {/* Hot TTL */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-white/60 flex items-center gap-1">
                    Cache TTL
                    <span className="group relative">
                      <Info className="w-3 h-3 text-white/30 cursor-help" />
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-black/90 text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap transition pointer-events-none">
                        How long to cache LLM results for hot markets
                      </span>
                    </span>
                  </label>
                  <span className="text-orange-400 font-bold">{Math.floor((llmConfig.hot_market_ttl_seconds || 600) / 60)} min</span>
                </div>
                <input 
                  type="range" 
                  value={llmConfig.hot_market_ttl_seconds || 600} 
                  onChange={(e) => setLlmConfig({...llmConfig, hot_market_ttl_seconds: parseInt(e.target.value)})}
                  className="w-full h-2 bg-white/10 rounded-lg accent-orange-500" 
                  min="60" max="1800" step="60" 
                />
                <div className="flex justify-between text-xs text-white/30 mt-1">
                  <span>1 min</span>
                  <span>30 min</span>
                </div>
              </div>
            </div>

            {/* Cold Market Settings */}
            <div className="rounded-xl bg-white/5 border border-cyan-500/30 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center">
                  <Snowflake className="w-5 h-5 text-cyan-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Cold Markets</h3>
                  <p className="text-xs text-white/50">Low-volume market settings</p>
                </div>
              </div>

              {/* Cold TTL */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-white/60 flex items-center gap-1">
                    Cache TTL
                    <span className="group relative">
                      <Info className="w-3 h-3 text-white/30 cursor-help" />
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-black/90 text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap transition pointer-events-none">
                        How long to cache LLM results for cold markets
                      </span>
                    </span>
                  </label>
                  <span className="text-cyan-400 font-bold">{Math.floor((llmConfig.cold_market_ttl_seconds || 3600) / 60)} min</span>
                </div>
                <input 
                  type="range" 
                  value={llmConfig.cold_market_ttl_seconds || 3600} 
                  onChange={(e) => setLlmConfig({...llmConfig, cold_market_ttl_seconds: parseInt(e.target.value)})}
                  className="w-full h-2 bg-white/10 rounded-lg accent-cyan-500" 
                  min="300" max="7200" step="300" 
                />
                <div className="flex justify-between text-xs text-white/30 mt-1">
                  <span>5 min</span>
                  <span>2 hours</span>
                </div>
              </div>

              {/* API Timeout */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm text-white/60 flex items-center gap-1">
                    API Timeout
                    <span className="group relative">
                      <Info className="w-3 h-3 text-white/30 cursor-help" />
                      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-black/90 text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap transition pointer-events-none">
                        Max wait time for LLM response
                      </span>
                    </span>
                  </label>
                  <span className="text-cyan-400 font-bold">{llmConfig.llm_timeout_seconds || 10}s</span>
                </div>
                <input 
                  type="range" 
                  value={llmConfig.llm_timeout_seconds || 10} 
                  onChange={(e) => setLlmConfig({...llmConfig, llm_timeout_seconds: parseFloat(e.target.value)})}
                  className="w-full h-2 bg-white/10 rounded-lg accent-cyan-500" 
                  min="5" max="30" step="1" 
                />
                <div className="flex justify-between text-xs text-white/30 mt-1">
                  <span>5s</span>
                  <span>30s</span>
                </div>
              </div>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-end">
            <button 
              onClick={saveLlmConfig} 
              disabled={savingLlmConfig}
              className="flex items-center gap-2 px-6 py-3 rounded-xl bg-purple-500 hover:bg-purple-600 text-white font-semibold transition disabled:opacity-50"
            >
              {savingLlmConfig ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
              Save LLM Config
            </button>
          </div>

          {/* Cache Entries Table */}
          {llmStats?.cache_entries && Object.keys(llmStats.cache_entries).length > 0 && (
            <div className="rounded-xl bg-white/5 border border-white/10 p-6">
              <div className="flex items-center gap-3 mb-4">
                <Database className="w-5 h-5 text-purple-400" />
                <h3 className="text-white font-semibold">Cached Markets</h3>
                <span className="text-xs text-white/50">({Object.keys(llmStats.cache_entries).length} entries)</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-white/50 border-b border-white/10">
                      <th className="text-left py-2 px-2">Market ID</th>
                      <th className="text-center py-2 px-2">Type</th>
                      <th className="text-right py-2 px-2">Sentiment</th>
                      <th className="text-right py-2 px-2">Confidence</th>
                      <th className="text-right py-2 px-2">Age</th>
                      <th className="text-right py-2 px-2">Expires In</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(llmStats.cache_entries).slice(0, 10).map(([id, entry]) => (
                      <tr key={id} className="border-b border-white/5 hover:bg-white/5">
                        <td className="py-2 px-2 text-white/70 font-mono text-xs">{id}...</td>
                        <td className="py-2 px-2 text-center">
                          {entry.is_hot ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-400 text-xs">
                              <Flame className="w-3 h-3" /> Hot
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 text-xs">
                              <Snowflake className="w-3 h-3" /> Cold
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-2 text-right">
                          <span className={entry.sentiment > 0.55 ? 'text-green-400' : entry.sentiment < 0.45 ? 'text-red-400' : 'text-white/60'}>
                            {(entry.sentiment * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-2 px-2 text-right text-white/60">{(entry.confidence * 100).toFixed(0)}%</td>
                        <td className="py-2 px-2 text-right text-white/50">{Math.floor(entry.age_seconds / 60)}m ago</td>
                        <td className="py-2 px-2 text-right">
                          <span className={entry.expires_in < 60 ? 'text-red-400' : 'text-green-400'}>
                            {Math.floor(entry.expires_in / 60)}m
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Market Selection Tab */}
      {activeTab === 'markets' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Liquidity Range - Combined Min and Max */}
          <div className="lg:col-span-2 rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                <DollarSign className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Liquidity Range</h3>
                <p className="text-xs text-white/50">Filter markets by liquidity ($)</p>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Min Liquidity */}
              <div>
                <label className="text-sm text-white/60 mb-2 block">Minimum Liquidity</label>
                <div className="flex items-center gap-4">
                  <input 
                    type="range" 
                    value={config.min_liquidity || 0} 
                    onChange={(e) => setConfig({...config, min_liquidity: parseFloat(e.target.value)})} 
                    className="flex-1 h-2 bg-white/10 rounded-lg accent-emerald-500" 
                    min="0" 
                    max="100000" 
                    step="100" 
                  />
                  <span className="text-white font-bold text-lg w-24 text-right">${(config.min_liquidity || 0).toLocaleString()}</span>
                </div>
                <div className="grid grid-cols-4 gap-2 mt-3">
                  {[0, 100, 1000, 10000].map((val) => (
                    <button 
                      key={val} 
                      onClick={() => setConfig({...config, min_liquidity: val})} 
                      className={`px-2 py-1.5 rounded-lg text-xs font-medium transition ${config.min_liquidity === val ? 'bg-emerald-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}
                    >
                      ${val === 0 ? '0' : val >= 1000 ? `${val/1000}K` : val}
                    </button>
                  ))}
                </div>
              </div>
              {/* Max Liquidity */}
              <div>
                <label className="text-sm text-white/60 mb-2 block">Maximum Liquidity</label>
                <div className="flex items-center gap-4">
                  <input 
                    type="range" 
                    value={config.max_liquidity || 1000000} 
                    onChange={(e) => setConfig({...config, max_liquidity: parseFloat(e.target.value)})} 
                    className="flex-1 h-2 bg-white/10 rounded-lg accent-emerald-500" 
                    min="10000" 
                    max="10000000" 
                    step="10000" 
                  />
                  <span className="text-white font-bold text-lg w-24 text-right">${(config.max_liquidity || 1000000) >= 1000000 ? `${(config.max_liquidity / 1000000).toFixed(1)}M` : `${(config.max_liquidity / 1000).toFixed(0)}K`}</span>
                </div>
                <div className="grid grid-cols-4 gap-2 mt-3">
                  {[100000, 500000, 1000000, 10000000].map((val) => (
                    <button 
                      key={val} 
                      onClick={() => setConfig({...config, max_liquidity: val})} 
                      className={`px-2 py-1.5 rounded-lg text-xs font-medium transition ${config.max_liquidity === val ? 'bg-emerald-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}
                    >
                      ${val >= 1000000 ? `${val/1000000}M` : `${val/1000}K`}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <p className="text-sm text-emerald-400">Trading markets with liquidity between <span className="font-bold">${(config.min_liquidity || 0).toLocaleString()}</span> and <span className="font-bold">${(config.max_liquidity || 1000000).toLocaleString()}</span></p>
            </div>
          </div>
          
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <Activity className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Min Volume 24h</h3>
                <p className="text-xs text-white/50">Minimum 24h trading volume ($)</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <input 
                type="range" 
                value={config.min_volume_24h || 1000} 
                onChange={(e) => setConfig({...config, min_volume_24h: parseFloat(e.target.value)})} 
                className="flex-1 h-2 bg-white/10 rounded-lg" 
                min="0" 
                max="100000" 
                step="1000" 
              />
              <span className="text-white font-bold text-xl w-24 text-right">${(config.min_volume_24h || 1000).toLocaleString()}</span>
            </div>
            <div className="grid grid-cols-4 gap-2 mt-4">
              {[0, 1000, 10000, 100000].map((val) => (
                <button 
                  key={val} 
                  onClick={() => setConfig({...config, min_volume_24h: val})} 
                  className={`px-2 py-2 rounded-lg text-xs font-medium transition ${config.min_volume_24h === val ? 'bg-blue-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}
                >
                  ${val === 0 ? '0' : val >= 1000 ? `${val/1000}K` : val}
                </button>
              ))}
            </div>
            <p className="text-xs text-white/40 mt-3">Higher volume = more active markets</p>
          </div>
          
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
                <Crosshair className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Max Spread</h3>
                <p className="text-xs text-white/50">Maximum bid-ask spread</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <input 
                type="range" 
                value={(config.max_spread || 0.05) * 100} 
                onChange={(e) => setConfig({...config, max_spread: parseFloat(e.target.value) / 100})} 
                className="flex-1 h-2 bg-white/10 rounded-lg" 
                min="1" 
                max="100" 
                step="1" 
              />
              <span className="text-white font-bold text-xl w-20 text-right">{((config.max_spread || 0.05) * 100).toFixed(1)}%</span>
            </div>
            <div className="grid grid-cols-5 gap-2 mt-4">
              {[0.05, 0.10, 0.25, 0.50, 0.99].map((val) => (
                <button 
                  key={val} 
                  onClick={() => setConfig({...config, max_spread: val})} 
                  className={`px-2 py-2 rounded-lg text-xs font-medium transition ${config.max_spread === val ? 'bg-amber-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}
                >
                  {val * 100}%
                </button>
              ))}
            </div>
            <p className="text-xs text-white/40 mt-3">Higher spread tolerance = more trade opportunities but more slippage risk</p>
          </div>

          <div className="lg:col-span-3 rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                <Layers className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Max Open Positions (Global Total)</h3>
                <p className="text-xs text-white/50">Total positions across ALL markets (portfolio-wide limit)</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <input 
                type="range" 
                value={config.max_open_positions || 50} 
                onChange={(e) => setConfig({...config, max_open_positions: parseInt(e.target.value)})} 
                className="flex-1 h-2 bg-white/10 rounded-lg" 
                min="1" 
                max="5000" 
                step="10" 
              />
              <span className="text-white font-bold text-xl w-20 text-right">{config.max_open_positions || 50}</span>
            </div>
            <div className="grid grid-cols-7 gap-2 mt-4">
              {[10, 50, 100, 250, 500, 1000, 5000].map((val) => (
                <button 
                  key={val} 
                  onClick={() => setConfig({...config, max_open_positions: val})} 
                  className={`px-2 py-2 rounded-lg text-xs font-medium transition ${config.max_open_positions === val ? 'bg-purple-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}
                >
                  {val}
                </button>
              ))}
            </div>
            <p className="text-xs text-white/40 mt-3">Higher = more diversification but needs more capital</p>
          </div>

          {/* Stuck Price Multiplier */}
          <div className="lg:col-span-3 rounded-xl bg-gradient-to-br from-rose-500/10 to-orange-500/10 border border-rose-500/20 p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-rose-500/20 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-rose-400" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Stuck Price Filter</h3>
                <p className="text-xs text-white/50">Volume multiplier for markets at default prices (0.0, 0.5, 1.0)</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <input 
                type="range" 
                value={config.stuck_price_multiplier || 2.0} 
                onChange={(e) => setConfig({...config, stuck_price_multiplier: parseFloat(e.target.value)})} 
                className="flex-1 h-2 bg-white/10 rounded-lg accent-rose-500" 
                min="1" 
                max="5" 
                step="0.5" 
              />
              <span className="text-white font-bold text-xl w-16 text-right">{config.stuck_price_multiplier || 2.0}x</span>
            </div>
            <div className="grid grid-cols-5 gap-2 mt-4">
              {[1, 1.5, 2, 3, 5].map((val) => (
                <button 
                  key={val} 
                  onClick={() => setConfig({...config, stuck_price_multiplier: val})} 
                  className={`px-2 py-2 rounded-lg text-xs font-medium transition ${config.stuck_price_multiplier === val ? 'bg-rose-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'}`}
                >
                  {val}x
                </button>
              ))}
            </div>
            <div className="mt-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20">
              <p className="text-sm text-rose-300">
                <strong>Required volume for stuck prices:</strong> {((config.min_volume_24h || 1000) * (config.stuck_price_multiplier || 2.0)).toLocaleString()} 
                <span className="text-white/50 ml-1">({config.stuck_price_multiplier || 2}x × ${(config.min_volume_24h || 1000).toLocaleString()} min volume)</span>
              </p>
              <p className="text-xs text-white/50 mt-2">Markets at exactly $0.00, $0.50, or $1.00 may be stale or newly created. Higher multiplier = stricter filtering.</p>
            </div>
          </div>

          <div className="lg:col-span-3 rounded-xl bg-cyan-500/10 border border-cyan-500/20 p-6">
            <div className="flex items-center gap-3 mb-4">
              <Info className="w-5 h-5 text-cyan-400" />
              <h3 className="text-white font-semibold">Market Selection Guide</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-lg bg-white/5">
                <h4 className="text-white font-medium mb-2">🎯 High Frequency (Aggressive)</h4>
                <p className="text-xs text-white/60">Liquidity: $0, Volume: $0, Spread: 10%</p>
                <p className="text-xs text-white/40 mt-1">Maximum market coverage, higher risk</p>
              </div>
              <div className="p-4 rounded-lg bg-white/5">
                <h4 className="text-white font-medium mb-2">⚖️ Balanced</h4>
                <p className="text-xs text-white/60">Liquidity: $100, Volume: $1K, Spread: 5%</p>
                <p className="text-xs text-white/40 mt-1">Good balance of opportunities and safety</p>
              </div>
              <div className="p-4 rounded-lg bg-white/5">
                <h4 className="text-white font-medium mb-2">🛡️ Conservative</h4>
                <p className="text-xs text-white/60">Liquidity: $10K, Volume: $100K, Spread: 2%</p>
                <p className="text-xs text-white/40 mt-1">Only highest quality markets</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Exit Parameters Tab */}
      {activeTab === 'exits' && (
        <div className="space-y-6">
          {/* Exit Mode Toggle - Dynamic vs Simple */}
          <div className="rounded-xl bg-gradient-to-br from-cyan-500/10 to-blue-500/10 border border-cyan-500/20 p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
                  <Sparkles className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h3 className="text-white font-semibold">Exit Mode</h3>
                  <p className="text-xs text-white/50">Choose between time-aware dynamic exits or simple fixed thresholds</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-sm ${!useDynamicExit ? 'text-white' : 'text-white/40'}`}>Simple</span>
                <button
                  onClick={toggleExitMode}
                  className={`relative w-14 h-7 rounded-full transition-colors ${useDynamicExit ? 'bg-cyan-500' : 'bg-gray-600'}`}
                >
                  <div className={`absolute top-1 w-5 h-5 rounded-full bg-white transition-transform ${useDynamicExit ? 'translate-x-8' : 'translate-x-1'}`} />
                </button>
                <span className={`text-sm ${useDynamicExit ? 'text-cyan-400' : 'text-white/40'}`}>Dynamic</span>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Dynamic Mode Info */}
              <div className={`rounded-lg p-4 border ${useDynamicExit ? 'bg-cyan-500/10 border-cyan-500/30' : 'bg-white/5 border-white/10 opacity-50'}`}>
                <h4 className="text-sm font-medium text-white mb-2 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" /> Dynamic (Time-Aware)
                </h4>
                <ul className="text-xs text-white/60 space-y-1">
                  <li>• TP = 10% of max possible gain (0.5%-50%)</li>
                  <li>• SL scales with price extremeness (-10% to -30%)</li>
                  <li>• ≤3d: Hold to resolution, no TP/SL</li>
                  <li>• 4-7d: Hold with SL protection</li>
                  <li>• 8-30d: Active TP/SL management</li>
                  <li>• &gt;30d: Quick trade, exit in 24h</li>
                </ul>
              </div>
              
              {/* Simple Mode Info */}
              <div className={`rounded-lg p-4 border ${!useDynamicExit ? 'bg-gray-500/10 border-gray-500/30' : 'bg-white/5 border-white/10 opacity-50'}`}>
                <h4 className="text-sm font-medium text-white mb-2 flex items-center gap-2">
                  <Settings className="w-4 h-4 text-gray-400" /> Simple (Configurable)
                </h4>
                <ul className="text-xs text-white/60 space-y-1">
                  <li>• Fixed TP/SL per strategy (configured below)</li>
                  <li>• Same thresholds regardless of price or expiry</li>
                  <li>• Simple to understand and predict</li>
                  <li>• Manual control over exit points</li>
                </ul>
              </div>
            </div>
            
            {useDynamicExit && (
              <div className="mt-4 p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                <p className="text-xs text-cyan-300 text-center">
                  ⚡ Dynamic mode active - Exit parameters below are used as fallback only
                </p>
              </div>
            )}
          </div>
          
          {/* Strategy Exit Parameters (Simple Mode Config) */}
          <div className={`rounded-xl bg-white/5 border border-white/10 p-6 ${useDynamicExit ? 'opacity-60' : ''}`}>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-rose-500 to-orange-600 flex items-center justify-center">
                <Target className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Strategy Exit Parameters {useDynamicExit && <span className="text-xs text-white/40">(Fallback)</span>}</h3>
                <p className="text-xs text-white/50">Configure Take Profit, Stop Loss, and Max Hold Time per strategy</p>
              </div>
            </div>

            <div className="space-y-6">
              {STRATEGIES.map((strategy) => {
                const exitParams = config.exit_params?.[strategy.id] || { take_profit: 0.05, stop_loss: -0.05, max_hours: 6 };
                const Icon = strategy.icon;
                
                const updateExitParam = (param, value) => {
                  setConfig(prev => ({
                    ...prev,
                    exit_params: {
                      ...prev.exit_params,
                      [strategy.id]: {
                        ...prev.exit_params?.[strategy.id],
                        [param]: value
                      }
                    }
                  }));
                };

                return (
                  <div key={strategy.id} className="rounded-xl bg-white/5 border border-white/10 p-5">
                    <div className="flex items-center gap-3 mb-4">
                      <div className={`w-10 h-10 rounded-lg bg-${strategy.color}-500/20 flex items-center justify-center`}>
                        <Icon className={`w-5 h-5 text-${strategy.color}-400`} />
                      </div>
                      <div>
                        <h4 className="text-white font-semibold">{strategy.label}</h4>
                        <p className="text-xs text-white/50">{strategy.description}</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      {/* Take Profit */}
                      <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/20">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm text-white/60 flex items-center gap-2">
                            <TrendingUp className="w-4 h-4 text-green-400" /> Take Profit
                          </span>
                          <span className="text-lg font-bold text-green-400">+{(exitParams.take_profit * 100).toFixed(0)}%</span>
                        </div>
                        <input
                          type="range"
                          value={(exitParams.take_profit || 0.05) * 100}
                          onChange={(e) => updateExitParam('take_profit', parseFloat(e.target.value) / 100)}
                          className="w-full h-2 bg-white/10 rounded-lg accent-green-500"
                          min="1"
                          max="20"
                          step="0.5"
                        />
                        <div className="flex justify-between text-xs text-white/40 mt-1">
                          <span>1%</span>
                          <span>10%</span>
                          <span>20%</span>
                        </div>
                      </div>

                      {/* Stop Loss */}
                      <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm text-white/60 flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-red-400" /> Stop Loss
                          </span>
                          <span className="text-lg font-bold text-red-400">{(exitParams.stop_loss * 100).toFixed(0)}%</span>
                        </div>
                        <input
                          type="range"
                          value={Math.abs(exitParams.stop_loss || 0.05) * 100}
                          onChange={(e) => updateExitParam('stop_loss', -parseFloat(e.target.value) / 100)}
                          className="w-full h-2 bg-white/10 rounded-lg accent-red-500"
                          min="1"
                          max="20"
                          step="0.5"
                        />
                        <div className="flex justify-between text-xs text-white/40 mt-1">
                          <span>-1%</span>
                          <span>-10%</span>
                          <span>-20%</span>
                        </div>
                      </div>

                      {/* Max Hold Time */}
                      <div className="p-4 rounded-lg bg-blue-500/10 border border-blue-500/20">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm text-white/60 flex items-center gap-2">
                            <Clock className="w-4 h-4 text-blue-400" /> Max Hold Time
                          </span>
                          <span className="text-lg font-bold text-blue-400">{exitParams.max_hours}h</span>
                        </div>
                        <input
                          type="range"
                          value={exitParams.max_hours || 6}
                          onChange={(e) => updateExitParam('max_hours', parseFloat(e.target.value))}
                          className="w-full h-2 bg-white/10 rounded-lg accent-blue-500"
                          min="1"
                          max="48"
                          step="1"
                        />
                        <div className="flex justify-between text-xs text-white/40 mt-1">
                          <span>1h</span>
                          <span>24h</span>
                          <span>48h</span>
                        </div>
                      </div>
                    </div>

                    {/* Quick Presets */}
                    <div className="flex items-center gap-2 mt-4">
                      <span className="text-xs text-white/40">Presets:</span>
                      <button
                        onClick={() => {
                          updateExitParam('take_profit', 0.02);
                          updateExitParam('stop_loss', -0.02);
                          updateExitParam('max_hours', 4);
                        }}
                        className="px-2 py-1 text-xs rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition"
                      >
                        Conservative
                      </button>
                      <button
                        onClick={() => {
                          updateExitParam('take_profit', 0.05);
                          updateExitParam('stop_loss', -0.05);
                          updateExitParam('max_hours', 8);
                        }}
                        className="px-2 py-1 text-xs rounded bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 transition"
                      >
                        Moderate
                      </button>
                      <button
                        onClick={() => {
                          updateExitParam('take_profit', 0.10);
                          updateExitParam('stop_loss', -0.08);
                          updateExitParam('max_hours', 24);
                        }}
                        className="px-2 py-1 text-xs rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition"
                      >
                        Aggressive
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Info Box */}
            <div className="mt-6 rounded-xl bg-cyan-500/10 border border-cyan-500/20 p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-cyan-400 mt-0.5" />
                <div>
                  <h4 className="text-white font-medium mb-1">How Exit Parameters Work</h4>
                  <ul className="text-xs text-white/60 space-y-1">
                    <li>• <span className="text-green-400">Take Profit</span>: Close position when unrealized P&L reaches this % gain</li>
                    <li>• <span className="text-red-400">Stop Loss</span>: Close position when unrealized P&L drops to this % loss</li>
                    <li>• <span className="text-blue-400">Max Hold Time</span>: Force close after this many hours regardless of P&L</li>
                    <li>• Asset class adjustments (crypto volatility, sports speed) are applied on top of these base values</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Asset Class Exit Multipliers Tab */}
      {activeTab === 'assetmult' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center">
                <Sliders className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Asset Class Exit Multipliers</h3>
                <p className="text-xs text-white/50">Adjust exit thresholds based on asset class characteristics</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {ASSET_CLASSES.map((asset) => {
                const mult = config.asset_class_exit_multipliers?.[asset.id] || { tp_mult: 1.0, sl_mult: 1.0, time_mult: 1.0 };
                const Icon = asset.icon;
                
                const updateMult = (param, value) => {
                  setConfig(prev => ({
                    ...prev,
                    asset_class_exit_multipliers: {
                      ...prev.asset_class_exit_multipliers,
                      [asset.id]: {
                        ...prev.asset_class_exit_multipliers?.[asset.id],
                        [param]: value
                      }
                    }
                  }));
                };

                return (
                  <div key={asset.id} className="rounded-xl bg-white/5 border border-white/10 p-4">
                    <div className="flex items-center gap-2 mb-4">
                      <Icon className={`w-5 h-5 text-${asset.color}-400`} />
                      <span className="text-white font-medium">{asset.label}</span>
                    </div>
                    
                    <div className="space-y-3">
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-white/50">TP Multiplier</span>
                          <span className="text-green-400">{mult.tp_mult?.toFixed(1)}x</span>
                        </div>
                        <input type="range" value={(mult.tp_mult || 1) * 10} onChange={(e) => updateMult('tp_mult', parseFloat(e.target.value) / 10)} className="w-full h-1.5 bg-white/10 rounded accent-green-500" min="5" max="20" step="1" />
                      </div>
                      
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-white/50">SL Multiplier</span>
                          <span className="text-red-400">{mult.sl_mult?.toFixed(1)}x</span>
                        </div>
                        <input type="range" value={(mult.sl_mult || 1) * 10} onChange={(e) => updateMult('sl_mult', parseFloat(e.target.value) / 10)} className="w-full h-1.5 bg-white/10 rounded accent-red-500" min="5" max="20" step="1" />
                      </div>
                      
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-white/50">Time Multiplier</span>
                          <span className="text-blue-400">{mult.time_mult?.toFixed(2)}x</span>
                        </div>
                        <input type="range" value={(mult.time_mult || 1) * 100} onChange={(e) => updateMult('time_mult', parseFloat(e.target.value) / 100)} className="w-full h-1.5 bg-white/10 rounded accent-blue-500" min="10" max="300" step="5" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 rounded-xl bg-purple-500/10 border border-purple-500/20 p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-purple-400 mt-0.5" />
                <div>
                  <h4 className="text-white font-medium mb-1">How Multipliers Work</h4>
                  <p className="text-xs text-white/60">These multipliers are applied to the base strategy exit parameters. For example, if Crypto has TP=1.5x and your Delta-Neutral strategy has TP=2%, the effective TP for Crypto trades is 3%.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Strategy Thresholds Tab */}
      {activeTab === 'thresholds' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
                <Crosshair className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Strategy Selection Thresholds</h3>
                <p className="text-xs text-white/50">Configure when each strategy is triggered based on market signals</p>
              </div>
            </div>

            <div className="space-y-6">
              {/* Volatility Threshold */}
              <div className="p-4 rounded-lg bg-purple-500/10 border border-purple-500/20">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Zap className="w-4 h-4 text-purple-400" />
                    <span className="text-white font-medium">Volatility Exploitation Threshold</span>
                  </div>
                  <span className="text-purple-400 font-mono text-lg">{((config.volatility_threshold || 0.05) * 100).toFixed(0)}%</span>
                </div>
                <input 
                  type="range" 
                  value={(config.volatility_threshold || 0.05) * 100} 
                  onChange={(e) => setConfig({...config, volatility_threshold: parseFloat(e.target.value) / 100})} 
                  className="w-full h-2 bg-white/10 rounded-lg accent-purple-500" 
                  min="1" max="20" step="1" 
                />
                <p className="text-xs text-white/40 mt-2">Volatility above this triggers the Volatility Exploitation strategy (default: 5%)</p>
              </div>

              {/* Sentiment Strength Threshold */}
              <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/20">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-amber-400" />
                    <span className="text-white font-medium">Sentiment Strength Threshold</span>
                  </div>
                  <span className="text-amber-400 font-mono text-lg">{((config.sentiment_strength_threshold || 0.25) * 100).toFixed(0)}%</span>
                </div>
                <input 
                  type="range" 
                  value={(config.sentiment_strength_threshold || 0.25) * 100} 
                  onChange={(e) => setConfig({...config, sentiment_strength_threshold: parseFloat(e.target.value) / 100})} 
                  className="w-full h-2 bg-white/10 rounded-lg accent-amber-500" 
                  min="5" max="50" step="1" 
                />
                <p className="text-xs text-white/40 mt-2">Sentiment divergence from 50% required for Alpha Directional (default: 25%)</p>
              </div>

              {/* Sharp Alignment Threshold */}
              <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Scale className="w-4 h-4 text-emerald-400" />
                    <span className="text-white font-medium">Sharp Alignment Threshold</span>
                  </div>
                  <span className="text-emerald-400 font-mono text-lg">{((config.sharp_alignment_threshold || 0.8) * 100).toFixed(0)}%</span>
                </div>
                <input 
                  type="range" 
                  value={(config.sharp_alignment_threshold || 0.8) * 100} 
                  onChange={(e) => setConfig({...config, sharp_alignment_threshold: parseFloat(e.target.value) / 100})} 
                  className="w-full h-2 bg-white/10 rounded-lg accent-emerald-500" 
                  min="50" max="95" step="1" 
                />
                <p className="text-xs text-white/40 mt-2">Sharp trader alignment required for Arbitrage strategy (default: 80%)</p>
              </div>

              {/* Delta Neutral Price Range */}
              <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                <div className="flex items-center gap-2 mb-4">
                  <GitBranch className="w-4 h-4 text-cyan-400" />
                  <span className="text-white font-medium">Delta-Neutral Price Range</span>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Min Price</span>
                      <span className="text-cyan-400 font-mono">{((config.delta_neutral_price_min || 0.35) * 100).toFixed(0)}%</span>
                    </div>
                    <input 
                      type="range" 
                      value={(config.delta_neutral_price_min || 0.35) * 100} 
                      onChange={(e) => setConfig({...config, delta_neutral_price_min: parseFloat(e.target.value) / 100})} 
                      className="w-full h-2 bg-white/10 rounded-lg accent-cyan-500" 
                      min="10" max="45" step="1" 
                    />
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Max Price</span>
                      <span className="text-cyan-400 font-mono">{((config.delta_neutral_price_max || 0.65) * 100).toFixed(0)}%</span>
                    </div>
                    <input 
                      type="range" 
                      value={(config.delta_neutral_price_max || 0.65) * 100} 
                      onChange={(e) => setConfig({...config, delta_neutral_price_max: parseFloat(e.target.value) / 100})} 
                      className="w-full h-2 bg-white/10 rounded-lg accent-cyan-500" 
                      min="55" max="90" step="1" 
                    />
                  </div>
                </div>
                <p className="text-xs text-white/40 mt-2">Price range for Delta-Neutral market making (default: 35%-65%)</p>
              </div>

              {/* Sentiment Side Selection Thresholds */}
              <div className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/20">
                <div className="flex items-center gap-2 mb-4">
                  <TrendingUp className="w-4 h-4 text-rose-400" />
                  <span className="text-white font-medium">Sentiment → Side Thresholds</span>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Bullish → YES</span>
                      <span className="text-green-400 font-mono">&gt;{((config.bullish_sentiment_threshold || 0.55) * 100).toFixed(0)}%</span>
                    </div>
                    <input 
                      type="range" 
                      value={(config.bullish_sentiment_threshold || 0.55) * 100} 
                      onChange={(e) => setConfig({...config, bullish_sentiment_threshold: parseFloat(e.target.value) / 100})} 
                      className="w-full h-2 bg-white/10 rounded-lg accent-green-500" 
                      min="51" max="70" step="1" 
                    />
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Bearish → NO</span>
                      <span className="text-red-400 font-mono">&lt;{((config.bearish_sentiment_threshold || 0.45) * 100).toFixed(0)}%</span>
                    </div>
                    <input 
                      type="range" 
                      value={(config.bearish_sentiment_threshold || 0.45) * 100} 
                      onChange={(e) => setConfig({...config, bearish_sentiment_threshold: parseFloat(e.target.value) / 100})} 
                      className="w-full h-2 bg-white/10 rounded-lg accent-red-500" 
                      min="30" max="49" step="1" 
                    />
                  </div>
                </div>
                <p className="text-xs text-white/40 mt-2">Sentiment between thresholds → RL decides direction. Wider gap = more RL influence.</p>
              </div>
            </div>

            {/* Info Box */}
            <div className="mt-6 rounded-xl bg-blue-500/10 border border-blue-500/20 p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-400 mt-0.5" />
                <div>
                  <h4 className="text-white font-medium mb-2">Strategy Selection Order</h4>
                  <ol className="text-xs text-white/60 space-y-1 list-decimal list-inside">
                    <li><span className="text-amber-400">Alpha Directional</span>: Extreme prices (&lt;10% or &gt;90%)</li>
                    <li><span className="text-emerald-400">Arbitrage</span>: Sharp alignment above threshold</li>
                    <li><span className="text-cyan-400">Delta-Neutral</span>: Mid-range price + low volatility</li>
                    <li><span className="text-amber-400">Alpha Directional</span>: Sentiment strength above threshold</li>
                    <li><span className="text-purple-400">Volatility Exploitation</span>: Volatility above threshold</li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Advanced Position Sizing Tab */}
      {activeTab === 'advanced' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-slate-500 to-zinc-600 flex items-center justify-center">
                <Settings className="w-5 h-5 text-white" />
              </div>
              <div>
                <h3 className="text-white font-semibold">Advanced Position Sizing</h3>
                <p className="text-xs text-white/50">Fine-tune position sizing algorithm parameters</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Kelly Bounds */}
              <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                <h4 className="text-white font-medium mb-4 flex items-center gap-2">
                  <Scale className="w-4 h-4 text-cyan-400" /> Kelly Criterion Bounds
                </h4>
                
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Min Kelly Fraction</span>
                      <span className="text-cyan-400">{(config.min_kelly_fraction * 100).toFixed(0)}%</span>
                    </div>
                    <input type="range" value={config.min_kelly_fraction * 100} onChange={(e) => setConfig({...config, min_kelly_fraction: parseFloat(e.target.value) / 100})} className="w-full h-2 bg-white/10 rounded-lg accent-cyan-500" min="1" max="30" step="1" />
                    <p className="text-xs text-white/40 mt-1">Minimum position size as % of Kelly optimal</p>
                  </div>
                  
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Max Kelly Fraction</span>
                      <span className="text-cyan-400">{(config.max_kelly_fraction * 100).toFixed(0)}%</span>
                    </div>
                    <input type="range" value={config.max_kelly_fraction * 100} onChange={(e) => setConfig({...config, max_kelly_fraction: parseFloat(e.target.value) / 100})} className="w-full h-2 bg-white/10 rounded-lg accent-cyan-500" min="10" max="100" step="5" />
                    <p className="text-xs text-white/40 mt-1">Maximum position size cap (safety limit)</p>
                  </div>
                </div>
              </div>

              {/* Position Limits */}
              <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                <h4 className="text-white font-medium mb-4 flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-green-400" /> Position Limits
                </h4>
                
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Minimum Position Size</span>
                      <span className="text-green-400">${config.min_position_size}</span>
                    </div>
                    <input type="range" value={config.min_position_size} onChange={(e) => setConfig({...config, min_position_size: parseFloat(e.target.value)})} className="w-full h-2 bg-white/10 rounded-lg accent-green-500" min="1" max="50" step="1" />
                    <p className="text-xs text-white/40 mt-1">Smallest allowed trade size in USD</p>
                  </div>
                  
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Full Size Liquidity</span>
                      <span className="text-green-400">${config.min_liquidity_for_full_size?.toLocaleString()}</span>
                    </div>
                    <input type="range" value={config.min_liquidity_for_full_size / 1000} onChange={(e) => setConfig({...config, min_liquidity_for_full_size: parseFloat(e.target.value) * 1000})} className="w-full h-2 bg-white/10 rounded-lg accent-green-500" min="1" max="100" step="1" />
                    <p className="text-xs text-white/40 mt-1">24h volume needed for full position sizing</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-4 rounded-xl bg-slate-500/10 border border-slate-500/20 p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-slate-400 mt-0.5" />
                <div>
                  <h4 className="text-white font-medium mb-1">Position Sizing Algorithm</h4>
                  <p className="text-xs text-white/60">Position size = Kelly Fraction × Conviction Signals × Liquidity Factor. The size is bounded by min/max Kelly and scaled down for low-liquidity markets.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="space-y-6">
          <div className="rounded-xl bg-white/5 border border-white/10 p-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${config.alerts_enabled ? 'from-green-500 to-emerald-600' : 'from-slate-500 to-zinc-600'} flex items-center justify-center`}>
                  {config.alerts_enabled ? <Bell className="w-5 h-5 text-white" /> : <BellOff className="w-5 h-5 text-white" />}
                </div>
                <div>
                  <h3 className="text-white font-semibold">Real-Time Market Alerts</h3>
                  <p className="text-xs text-white/50">Get notified of high-volume markets with significant activity</p>
                </div>
              </div>
              
              <button
                onClick={() => setConfig({...config, alerts_enabled: !config.alerts_enabled})}
                className={`px-4 py-2 rounded-lg font-medium transition ${config.alerts_enabled ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-white/5 text-white/60 border border-white/10'}`}
              >
                {config.alerts_enabled ? 'Enabled' : 'Disabled'}
              </button>
            </div>

            {config.alerts_enabled && (
              <div className="space-y-6">
                <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                  <h4 className="text-white font-medium mb-4">Alert Triggers</h4>
                  
                  <div>
                    <div className="flex justify-between text-sm mb-2">
                      <span className="text-white/60">Volume Spike Threshold</span>
                      <span className="text-yellow-400">{config.alert_volume_threshold}x</span>
                    </div>
                    <input type="range" value={config.alert_volume_threshold * 10} onChange={(e) => setConfig({...config, alert_volume_threshold: parseFloat(e.target.value) / 10})} className="w-full h-2 bg-white/10 rounded-lg accent-yellow-500" min="10" max="50" step="1" />
                    <p className="text-xs text-white/40 mt-1">Alert when 24h volume exceeds this multiple of liquidity</p>
                  </div>
                </div>

                <div className="rounded-xl bg-yellow-500/10 border border-yellow-500/20 p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-yellow-400 mt-0.5" />
                    <div>
                      <h4 className="text-white font-medium mb-1">Alert Types</h4>
                      <ul className="text-xs text-white/60 space-y-1">
                        <li>• <span className="text-yellow-400">Volume Spike</span>: Market trading volume increases significantly</li>
                        <li>• <span className="text-cyan-400">Price Movement</span>: Large price swing detected (5%+ change)</li>
                        <li>• Alerts appear in real-time via WebSocket connection</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {!config.alerts_enabled && (
              <div className="text-center py-8 text-white/40">
                <BellOff className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Enable alerts to receive real-time notifications</p>
              </div>
            )}
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
                const exitParams = config.exit_params?.[strategy.id] || {};
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
                        
                        {/* Risk and Return Row */}
                        <div className="flex items-center gap-3 mt-2">
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            strategy.risk === 'Low' ? 'bg-green-500/20 text-green-400' :
                            strategy.risk === 'Medium' ? 'bg-yellow-500/20 text-yellow-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {strategy.risk} Risk
                          </span>
                          <span className="text-xs text-white/40">Return: {strategy.expectedReturn}</span>
                        </div>
                        
                        {/* Strategy Details (shown when enabled) */}
                        {isEnabled && (
                          <div className="mt-3 pt-3 border-t border-white/10 grid grid-cols-3 gap-2 text-xs">
                            <div className="text-center">
                              <div className="text-green-400 font-semibold">+{((exitParams.take_profit || 0.05) * 100).toFixed(0)}%</div>
                              <div className="text-white/40">TP</div>
                            </div>
                            <div className="text-center">
                              <div className="text-red-400 font-semibold">{((exitParams.stop_loss || -0.05) * 100).toFixed(0)}%</div>
                              <div className="text-white/40">SL</div>
                            </div>
                            <div className="text-center">
                              <div className="text-blue-400 font-semibold">{exitParams.max_hours || 6}h</div>
                              <div className="text-white/40">Max</div>
                            </div>
                          </div>
                        )}
                        
                        {/* Best For tooltip */}
                        <div className="mt-2 text-xs text-white/30 italic">
                          Best for: {strategy.bestFor}
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
