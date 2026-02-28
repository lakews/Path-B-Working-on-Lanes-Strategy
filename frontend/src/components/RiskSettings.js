import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { 
  Shield, Save, RefreshCw, CheckCircle, XCircle, AlertTriangle, 
  Zap, Target, TrendingUp, Crosshair, Newspaper, Trophy, 
  DollarSign, Percent, Clock, Activity, Settings, Layers,
  ChevronDown, ChevronUp, Info, RotateCcw
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Lane icons and colors
const LANE_META = {
  HFT: { icon: Zap, color: 'yellow', label: 'HFT (Market Maker)' },
  ALPHA: { icon: TrendingUp, color: 'green', label: 'ALPHA (Strategist)' },
  GAMMA: { icon: Crosshair, color: 'purple', label: 'GAMMA (Sniper)' },
  SPORTS: { icon: Trophy, color: 'orange', label: 'SPORTS (Bookie)' },
  NEWS: { icon: Newspaper, color: 'blue', label: 'NEWS (Injector)' },
};

const RiskSettings = () => {
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [synced, setSynced] = useState(true);
  const [hasChanges, setHasChanges] = useState(false);
  const [expandedLanes, setExpandedLanes] = useState({});
  const [expandedSections, setExpandedSections] = useState({
    global: true,
    extreme_price: false,
    lanes: true,
    kelly: false,
    sectors: false
  });

  // Fetch config from backend
  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API}/risk-config`);
      if (response.data.success) {
        setConfig(response.data.config);
        setStatus(response.data.status);
        setSynced(response.data.synced);
        setHasChanges(false);
      }
    } catch (error) {
      console.error('Error fetching risk config:', error);
      toast.error('Failed to load risk configuration');
      setSynced(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  // Save config to backend
  const saveConfig = async () => {
    try {
      setSaving(true);
      const response = await axios.post(`${API}/risk-config`, config);
      if (response.data.success) {
        toast.success('Risk configuration saved');
        setSynced(true);
        setHasChanges(false);
        setConfig(response.data.config);
      } else {
        toast.error(response.data.error || 'Failed to save');
        setSynced(false);
      }
    } catch (error) {
      console.error('Error saving risk config:', error);
      toast.error(error.response?.data?.error || 'Failed to save configuration');
      setSynced(false);
    } finally {
      setSaving(false);
    }
  };

  // Reload config from file
  const reloadConfig = async () => {
    try {
      const response = await axios.post(`${API}/risk-config/reload`);
      if (response.data.success) {
        toast.success('Configuration reloaded from file');
        setConfig(response.data.config);
        setSynced(true);
        setHasChanges(false);
      }
    } catch (error) {
      toast.error('Failed to reload configuration');
    }
  };

  // Update a nested config value
  const updateConfig = (path, value) => {
    setConfig(prev => {
      const newConfig = JSON.parse(JSON.stringify(prev));
      const keys = path.split('.');
      let current = newConfig;
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]];
      }
      current[keys[keys.length - 1]] = value;
      return newConfig;
    });
    setHasChanges(true);
  };

  // Toggle lane expansion
  const toggleLane = (lane) => {
    setExpandedLanes(prev => ({ ...prev, [lane]: !prev[lane] }));
  };

  // Toggle section expansion
  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        <span className="ml-2 text-gray-400">Loading risk configuration...</span>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-6 text-center">
        <XCircle className="w-12 h-12 text-red-400 mx-auto mb-2" />
        <p className="text-red-300">Failed to load risk configuration</p>
        <button 
          onClick={fetchConfig}
          className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="w-8 h-8 text-blue-400" />
          <div>
            <h2 className="text-2xl font-bold text-white">Risk Configuration</h2>
            <p className="text-gray-400 text-sm">5-Lane Architecture SSOT</p>
          </div>
        </div>
        
        {/* Sync Status */}
        <div className="flex items-center gap-4">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full ${
            synced && !hasChanges 
              ? 'bg-green-500/20 text-green-400' 
              : hasChanges 
                ? 'bg-yellow-500/20 text-yellow-400'
                : 'bg-red-500/20 text-red-400'
          }`}>
            {synced && !hasChanges ? (
              <>
                <CheckCircle className="w-4 h-4" />
                <span className="text-sm font-medium">Synced</span>
              </>
            ) : hasChanges ? (
              <>
                <AlertTriangle className="w-4 h-4" />
                <span className="text-sm font-medium">Unsaved Changes</span>
              </>
            ) : (
              <>
                <XCircle className="w-4 h-4" />
                <span className="text-sm font-medium">Out of Sync</span>
              </>
            )}
          </div>
          
          <button
            onClick={reloadConfig}
            className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
            title="Reload from file"
          >
            <RefreshCw className="w-5 h-5 text-gray-400" />
          </button>
          
          <button
            onClick={saveConfig}
            disabled={saving || !hasChanges}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              hasChanges 
                ? 'bg-blue-600 hover:bg-blue-700 text-white' 
                : 'bg-gray-700 text-gray-400 cursor-not-allowed'
            }`}
          >
            {saving ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Save Changes
          </button>
        </div>
      </div>

      {/* Version Info */}
      {status && (
        <div className="bg-gray-800/50 rounded-lg p-3 flex items-center justify-between text-sm">
          <div className="flex items-center gap-4">
            <span className="text-gray-400">Version:</span>
            <span className="text-white font-mono">{status.version}</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-gray-400">Last Loaded:</span>
            <span className="text-white">{status.last_loaded ? new Date(status.last_loaded).toLocaleString() : 'Never'}</span>
          </div>
        </div>
      )}

      {/* Global Safety Rails */}
      <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => toggleSection('global')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Shield className="w-5 h-5 text-red-400" />
            <span className="font-semibold text-white">Global Safety Rails</span>
          </div>
          {expandedSections.global ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>
        
        {expandedSections.global && config.global && (
          <div className="p-4 pt-0 space-y-4">
            {/* NEW: Dual Circuit Breaker with Reset Button */}
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-white/50">Circuit Breaker Limits</span>
              <button
                onClick={() => {
                  updateConfig('global.max_account_drawdown_pct', 0.10);
                  updateConfig('global.max_realized_drawdown_pct', 0.15);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-white/60 hover:text-white transition-colors"
              >
                <RotateCcw className="w-3 h-3" />
                Reset to Defaults (10%/15%)
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Account Drawdown - Primary */}
              <div className="bg-rose-500/10 border border-rose-500/30 rounded-lg p-4">
                <label className="block text-sm text-rose-300 mb-2">Account Drawdown (Primary CB)</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={(config.global.max_account_drawdown_pct ? config.global.max_account_drawdown_pct * 100 : config.global.max_drawdown_pct * 100).toFixed(0)}
                    onChange={(e) => updateConfig('global.max_account_drawdown_pct', parseFloat(e.target.value) / 100)}
                    className="w-20 bg-gray-800 border border-rose-500/50 rounded px-3 py-2 text-white"
                    min="3"
                    max="25"
                    step="1"
                  />
                  <Percent className="w-4 h-4 text-rose-400" />
                </div>
                <p className="text-xs text-rose-400/60 mt-1">Capital protection - vs initial</p>
              </div>
              
              {/* Realized Drawdown - Secondary */}
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
                <label className="block text-sm text-amber-300 mb-2">Realized Drawdown (Secondary CB)</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={(config.global.max_realized_drawdown_pct ? config.global.max_realized_drawdown_pct * 100 : 15).toFixed(0)}
                    onChange={(e) => updateConfig('global.max_realized_drawdown_pct', parseFloat(e.target.value) / 100)}
                    className="w-20 bg-gray-800 border border-amber-500/50 rounded px-3 py-2 text-white"
                    min="5"
                    max="30"
                    step="1"
                  />
                  <Percent className="w-4 h-4 text-amber-400" />
                </div>
                <p className="text-xs text-amber-400/60 mt-1">Profit protection - from peak P&L</p>
              </div>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Max Deployment</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={(config.global.max_deployment_pct * 100).toFixed(0)}
                  onChange={(e) => updateConfig('global.max_deployment_pct', parseFloat(e.target.value) / 100)}
                  className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                  min="50"
                  max="100"
                  step="5"
                />
                <Percent className="w-4 h-4 text-gray-400" />
              </div>
              <p className="text-xs text-gray-500 mt-1">Max capital in play</p>
            </div>

            {/* Kill Switch Low */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Kill Switch Low</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={(config.global.kill_switch_low * 100).toFixed(0)}
                  onChange={(e) => updateConfig('global.kill_switch_low', parseFloat(e.target.value) / 100)}
                  className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                  min="1"
                  max="10"
                  step="1"
                />
                <Percent className="w-4 h-4 text-gray-400" />
              </div>
              <p className="text-xs text-gray-500 mt-1">Skip prices below</p>
            </div>

            {/* Kill Switch High */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Kill Switch High</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={(config.global.kill_switch_high * 100).toFixed(0)}
                  onChange={(e) => updateConfig('global.kill_switch_high', parseFloat(e.target.value) / 100)}
                  className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                  min="90"
                  max="99"
                  step="1"
                />
                <Percent className="w-4 h-4 text-gray-400" />
              </div>
              <p className="text-xs text-gray-500 mt-1">Skip prices above</p>
            </div>

            {/* Max Open Positions */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Max Open Positions</label>
              <input
                type="number"
                value={config.global.max_open_positions}
                onChange={(e) => updateConfig('global.max_open_positions', parseInt(e.target.value))}
                className="w-24 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                min="10"
                max="200"
                step="10"
              />
            </div>

            {/* Min Trade Amount */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Min Trade Amount</label>
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-gray-400" />
                <input
                  type="number"
                  value={config.global.min_trade_amount}
                  onChange={(e) => updateConfig('global.min_trade_amount', parseFloat(e.target.value))}
                  className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                  min="1"
                  max="10"
                  step="0.5"
                />
              </div>
            </div>

            {/* Taker Fee */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Taker Fee</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={(config.global.taker_fee * 100).toFixed(1)}
                  onChange={(e) => updateConfig('global.taker_fee', parseFloat(e.target.value) / 100)}
                  className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                  min="0"
                  max="5"
                  step="0.1"
                />
                <Percent className="w-4 h-4 text-gray-400" />
              </div>
            </div>

            {/* Price Zone Threshold */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Whale Zone Ceiling</label>
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-gray-400" />
                <input
                  type="number"
                  value={config.global.price_zone_threshold}
                  onChange={(e) => updateConfig('global.price_zone_threshold', parseFloat(e.target.value))}
                  className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                  min="0.05"
                  max="0.20"
                  step="0.01"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">Price below = Whale Zone</p>
            </div>
            </div>
          </div>

          {/* Entry Validation Section */}
          <div className="mt-6 pt-6 border-t border-white/10">
            <h4 className="text-md font-semibold text-cyan-400 mb-4 flex items-center gap-2">
              <Shield className="w-4 h-4" />
              Entry Validation (Phantom Order Protection)
            </h4>
            <p className="text-xs text-gray-500 mb-4">
              Prevents recording phantom fills from dust orders that would never execute in reality.
              These settings protect P&L accuracy and ML/RL training data.
            </p>
            
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {/* Entry Price Floor */}
              <div className="bg-gray-900/50 rounded-lg p-4">
                <label className="block text-sm text-gray-400 mb-2">Price Floor</label>
                <div className="flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-red-400" />
                  <input
                    type="number"
                    value={(config.global.entry_price_floor || 0.02)}
                    onChange={(e) => updateConfig('global.entry_price_floor', parseFloat(e.target.value))}
                    className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                    min="0.01"
                    max="0.10"
                    step="0.01"
                  />
                </div>
                <p className="text-xs text-gray-500 mt-1">Reject below</p>
              </div>

              {/* Entry Price Ceiling */}
              <div className="bg-gray-900/50 rounded-lg p-4">
                <label className="block text-sm text-gray-400 mb-2">Price Ceiling</label>
                <div className="flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-red-400" />
                  <input
                    type="number"
                    value={(config.global.entry_price_ceiling || 0.98)}
                    onChange={(e) => updateConfig('global.entry_price_ceiling', parseFloat(e.target.value))}
                    className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                    min="0.90"
                    max="0.99"
                    step="0.01"
                  />
                </div>
                <p className="text-xs text-gray-500 mt-1">Reject above</p>
              </div>

              {/* Max Spread */}
              <div className="bg-gray-900/50 rounded-lg p-4">
                <label className="block text-sm text-gray-400 mb-2">Max Spread</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={((config.global.max_spread_entry_pct || 0.15) * 100).toFixed(0)}
                    onChange={(e) => updateConfig('global.max_spread_entry_pct', parseFloat(e.target.value) / 100)}
                    className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                    min="5"
                    max="25"
                    step="1"
                  />
                  <Percent className="w-4 h-4 text-gray-400" />
                </div>
                <p className="text-xs text-gray-500 mt-1">Skip illiquid</p>
              </div>

              {/* Max Liquidity Consumption */}
              <div className="bg-gray-900/50 rounded-lg p-4">
                <label className="block text-sm text-gray-400 mb-2">Max Consumption</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={((config.global.max_liquidity_consumption_pct || 0.25) * 100).toFixed(0)}
                    onChange={(e) => updateConfig('global.max_liquidity_consumption_pct', parseFloat(e.target.value) / 100)}
                    className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                    min="10"
                    max="50"
                    step="5"
                  />
                  <Percent className="w-4 h-4 text-gray-400" />
                </div>
                <p className="text-xs text-gray-500 mt-1">Of book depth</p>
              </div>

              {/* Min Liquidity Coverage */}
              <div className="bg-gray-900/50 rounded-lg p-4">
                <label className="block text-sm text-gray-400 mb-2">Min Coverage</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={((config.global.min_liquidity_coverage_pct || 1.0) * 100).toFixed(0)}
                    onChange={(e) => updateConfig('global.min_liquidity_coverage_pct', parseFloat(e.target.value) / 100)}
                    className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                    min="50"
                    max="100"
                    step="10"
                  />
                  <Percent className="w-4 h-4 text-gray-400" />
                </div>
                <p className="text-xs text-gray-500 mt-1">Can fill order</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Extreme Price Validation (Tiered Kill Switch) */}
      <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => toggleSection('extreme_price')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Zap className="w-5 h-5 text-yellow-400" />
            <span className="font-semibold text-white">Extreme Price Validation</span>
            <span className="text-sm text-gray-400">(Tiered Kill Switch)</span>
          </div>
          {expandedSections.extreme_price ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>

        {expandedSections.extreme_price && config.extreme_price_validation && (
          <div className="p-4 pt-0 space-y-4">
            {/* Enable/Disable Toggle */}
            <div className="flex items-center justify-between bg-gray-900/50 rounded-lg p-4">
              <div>
                <span className="text-white font-medium">Enable Tiered Validation</span>
                <p className="text-xs text-gray-400">Allow extreme prices with additional checks</p>
              </div>
              <button
                onClick={() => updateConfig('extreme_price_validation.enabled', !config.extreme_price_validation.enabled)}
                className={`relative w-12 h-6 rounded-full transition-colors ${
                  config.extreme_price_validation.enabled ? 'bg-yellow-500' : 'bg-gray-600'
                }`}
              >
                <span className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                  config.extreme_price_validation.enabled ? 'left-7' : 'left-1'
                }`} />
              </button>
            </div>

            {/* Global Thresholds */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-900/50 rounded-lg p-4">
                <label className="block text-sm text-gray-400 mb-2">Extreme Low Threshold</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={(config.extreme_price_validation.extreme_low_threshold * 100).toFixed(1)}
                    onChange={(e) => updateConfig('extreme_price_validation.extreme_low_threshold', parseFloat(e.target.value) / 100)}
                    className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                    min="0.5"
                    max="10"
                    step="0.5"
                  />
                  <Percent className="w-4 h-4 text-gray-400" />
                </div>
                <p className="text-xs text-gray-500 mt-1">Prices below need extra validation</p>
              </div>

              <div className="bg-gray-900/50 rounded-lg p-4">
                <label className="block text-sm text-gray-400 mb-2">Extreme High Threshold</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={(config.extreme_price_validation.extreme_high_threshold * 100).toFixed(1)}
                    onChange={(e) => updateConfig('extreme_price_validation.extreme_high_threshold', parseFloat(e.target.value) / 100)}
                    className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                    min="90"
                    max="99.5"
                    step="0.5"
                  />
                  <Percent className="w-4 h-4 text-gray-400" />
                </div>
                <p className="text-xs text-gray-500 mt-1">Prices above need extra validation</p>
              </div>
            </div>

            {/* Validation Requirements */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <h4 className="text-white font-medium mb-3">Validation Requirements for Extreme Prices</h4>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Min Orderbook Depth ($)</label>
                  <input
                    type="number"
                    value={config.extreme_price_validation.requirements?.min_orderbook_depth_usd || 100}
                    onChange={(e) => updateConfig('extreme_price_validation.requirements.min_orderbook_depth_usd', parseFloat(e.target.value))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                    min="50"
                    max="1000"
                    step="50"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Max Spread (%)</label>
                  <input
                    type="number"
                    value={((config.extreme_price_validation.requirements?.min_spread_quality || 0.05) * 100).toFixed(0)}
                    onChange={(e) => updateConfig('extreme_price_validation.requirements.min_spread_quality', parseFloat(e.target.value) / 100)}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                    min="1"
                    max="10"
                    step="1"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Min Volume/Hour ($)</label>
                  <input
                    type="number"
                    value={config.extreme_price_validation.requirements?.min_recent_volume_1h || 50}
                    onChange={(e) => updateConfig('extreme_price_validation.requirements.min_recent_volume_1h', parseFloat(e.target.value))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                    min="10"
                    max="500"
                    step="10"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Min Hours to Expiry</label>
                  <input
                    type="number"
                    value={config.extreme_price_validation.requirements?.min_time_to_expiry_hours || 24}
                    onChange={(e) => updateConfig('extreme_price_validation.requirements.min_time_to_expiry_hours', parseFloat(e.target.value))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                    min="1"
                    max="168"
                    step="1"
                  />
                </div>
              </div>
            </div>

            {/* Strategy Overrides */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <h4 className="text-white font-medium mb-3">Strategy-Specific Kill Switch Overrides</h4>
              <p className="text-xs text-gray-400 mb-4">Allow specific strategies to trade at more extreme prices (higher convexity)</p>
              
              {/* Volatility Exploit Override */}
              <div className="border border-purple-500/30 rounded-lg p-3 mb-3">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-purple-400" />
                    <span className="text-white font-medium">Volatility Exploit</span>
                  </div>
                  <button
                    onClick={() => updateConfig('extreme_price_validation.strategy_overrides.hft_volatility_exploit.enabled', 
                      !(config.extreme_price_validation.strategy_overrides?.hft_volatility_exploit?.enabled || false))}
                    className={`relative w-10 h-5 rounded-full transition-colors ${
                      config.extreme_price_validation.strategy_overrides?.hft_volatility_exploit?.enabled ? 'bg-purple-500' : 'bg-gray-600'
                    }`}
                  >
                    <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                      config.extreme_price_validation.strategy_overrides?.hft_volatility_exploit?.enabled ? 'left-5' : 'left-0.5'
                    }`} />
                  </button>
                </div>
                {config.extreme_price_validation.strategy_overrides?.hft_volatility_exploit?.enabled && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Min Price (%)</label>
                      <input
                        type="number"
                        value={((config.extreme_price_validation.strategy_overrides?.hft_volatility_exploit?.kill_switch_low || 0.005) * 100).toFixed(1)}
                        onChange={(e) => updateConfig('extreme_price_validation.strategy_overrides.hft_volatility_exploit.kill_switch_low', parseFloat(e.target.value) / 100)}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                        min="0.1"
                        max="5"
                        step="0.1"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Max Price (%)</label>
                      <input
                        type="number"
                        value={((config.extreme_price_validation.strategy_overrides?.hft_volatility_exploit?.kill_switch_high || 0.995) * 100).toFixed(1)}
                        onChange={(e) => updateConfig('extreme_price_validation.strategy_overrides.hft_volatility_exploit.kill_switch_high', parseFloat(e.target.value) / 100)}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                        min="95"
                        max="99.9"
                        step="0.1"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Gamma Scalp Override */}
              <div className="border border-green-500/30 rounded-lg p-3">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-green-400" />
                    <span className="text-white font-medium">Gamma Scalp</span>
                  </div>
                  <button
                    onClick={() => updateConfig('extreme_price_validation.strategy_overrides.gamma_scalp.enabled', 
                      !(config.extreme_price_validation.strategy_overrides?.gamma_scalp?.enabled || false))}
                    className={`relative w-10 h-5 rounded-full transition-colors ${
                      config.extreme_price_validation.strategy_overrides?.gamma_scalp?.enabled ? 'bg-green-500' : 'bg-gray-600'
                    }`}
                  >
                    <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                      config.extreme_price_validation.strategy_overrides?.gamma_scalp?.enabled ? 'left-5' : 'left-0.5'
                    }`} />
                  </button>
                </div>
                {config.extreme_price_validation.strategy_overrides?.gamma_scalp?.enabled && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Min Price (%)</label>
                      <input
                        type="number"
                        value={((config.extreme_price_validation.strategy_overrides?.gamma_scalp?.kill_switch_low || 0.01) * 100).toFixed(1)}
                        onChange={(e) => updateConfig('extreme_price_validation.strategy_overrides.gamma_scalp.kill_switch_low', parseFloat(e.target.value) / 100)}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                        min="0.5"
                        max="5"
                        step="0.1"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Max Price (%)</label>
                      <input
                        type="number"
                        value={((config.extreme_price_validation.strategy_overrides?.gamma_scalp?.kill_switch_high || 0.99) * 100).toFixed(1)}
                        onChange={(e) => updateConfig('extreme_price_validation.strategy_overrides.gamma_scalp.kill_switch_high', parseFloat(e.target.value) / 100)}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                        min="95"
                        max="99.5"
                        step="0.1"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Lane Configuration */}
      <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => toggleSection('lanes')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Layers className="w-5 h-5 text-blue-400" />
            <span className="font-semibold text-white">Lane Configuration</span>
            <span className="text-sm text-gray-400">(5 Lanes)</span>
          </div>
          {expandedSections.lanes ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>

        {expandedSections.lanes && config.lanes && (
          <div className="p-4 pt-0 space-y-3">
            {Object.entries(config.lanes).map(([laneName, laneConfig]) => {
              const meta = LANE_META[laneName] || { icon: Activity, color: 'gray', label: laneName };
              const Icon = meta.icon;
              const isExpanded = expandedLanes[laneName];
              
              return (
                <div key={laneName} className={`bg-gray-900/50 rounded-lg border border-${meta.color}-500/20 overflow-hidden`}>
                  <button
                    onClick={() => toggleLane(laneName)}
                    className="w-full flex items-center justify-between p-3 hover:bg-gray-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-lg bg-${meta.color}-500/20`}>
                        <Icon className={`w-5 h-5 text-${meta.color}-400`} />
                      </div>
                      <div className="text-left">
                        <span className="font-medium text-white">{meta.label}</span>
                        <p className="text-xs text-gray-400">{laneConfig.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <span className={`text-${meta.color}-400 font-bold`}>{(laneConfig.alloc_pct * 100).toFixed(0)}%</span>
                        <p className="text-xs text-gray-500">Allocation</p>
                      </div>
                      {isExpanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                    </div>
                  </button>
                  
                  {isExpanded && (
                    <div className="p-4 pt-0 grid grid-cols-2 md:grid-cols-4 gap-3 border-t border-gray-700/50">
                      {/* Allocation */}
                      <div className="p-3 bg-gray-800/50 rounded-lg">
                        <label className="block text-xs text-gray-400 mb-1">Allocation %</label>
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            value={(laneConfig.alloc_pct * 100).toFixed(0)}
                            onChange={(e) => updateConfig(`lanes.${laneName}.alloc_pct`, parseFloat(e.target.value) / 100)}
                            className="w-16 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                            min="0"
                            max="100"
                            step="5"
                          />
                          <Percent className="w-3 h-3 text-gray-500" />
                        </div>
                      </div>

                      {/* Max Position USD */}
                      <div className="p-3 bg-gray-800/50 rounded-lg">
                        <label className="block text-xs text-gray-400 mb-1">Max Pos USD</label>
                        <div className="flex items-center gap-1">
                          <DollarSign className="w-3 h-3 text-gray-500" />
                          <input
                            type="number"
                            value={laneConfig.max_pos_usd}
                            onChange={(e) => updateConfig(`lanes.${laneName}.max_pos_usd`, parseFloat(e.target.value))}
                            className="w-16 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                            min="5"
                            max="500"
                            step="5"
                          />
                        </div>
                      </div>

                      {/* Max Position % */}
                      <div className="p-3 bg-gray-800/50 rounded-lg">
                        <label className="block text-xs text-gray-400 mb-1">Max Pos %</label>
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            value={(laneConfig.max_pos_pct * 100).toFixed(1)}
                            onChange={(e) => updateConfig(`lanes.${laneName}.max_pos_pct`, parseFloat(e.target.value) / 100)}
                            className="w-16 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                            min="0.5"
                            max="10"
                            step="0.5"
                          />
                          <Percent className="w-3 h-3 text-gray-500" />
                        </div>
                      </div>

                      {/* Min Liquidity */}
                      {laneConfig.min_liquidity !== undefined && (
                        <div className="p-3 bg-gray-800/50 rounded-lg">
                          <label className="block text-xs text-gray-400 mb-1">Min Liquidity</label>
                          <div className="flex items-center gap-1">
                            <DollarSign className="w-3 h-3 text-gray-500" />
                            <input
                              type="number"
                              value={laneConfig.min_liquidity}
                              onChange={(e) => updateConfig(`lanes.${laneName}.min_liquidity`, parseFloat(e.target.value))}
                              className="w-20 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                              min="100"
                              max="50000"
                              step="100"
                            />
                          </div>
                        </div>
                      )}

                      {/* Min Volume */}
                      {laneConfig.min_volume_24h !== undefined && (
                        <div className="p-3 bg-gray-800/50 rounded-lg">
                          <label className="block text-xs text-gray-400 mb-1">Min Volume 24h</label>
                          <div className="flex items-center gap-1">
                            <DollarSign className="w-3 h-3 text-gray-500" />
                            <input
                              type="number"
                              value={laneConfig.min_volume_24h}
                              onChange={(e) => updateConfig(`lanes.${laneName}.min_volume_24h`, parseFloat(e.target.value))}
                              className="w-20 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                              min="100"
                              max="50000"
                              step="100"
                            />
                          </div>
                        </div>
                      )}

                      {/* Max Spread */}
                      {laneConfig.max_spread_pct !== undefined && (
                        <div className="p-3 bg-gray-800/50 rounded-lg">
                          <label className="block text-xs text-gray-400 mb-1">Max Spread</label>
                          <div className="flex items-center gap-1">
                            <input
                              type="number"
                              value={(laneConfig.max_spread_pct * 100).toFixed(0)}
                              onChange={(e) => updateConfig(`lanes.${laneName}.max_spread_pct`, parseFloat(e.target.value) / 100)}
                              className="w-14 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                              min="1"
                              max="30"
                              step="1"
                            />
                            <Percent className="w-3 h-3 text-gray-500" />
                          </div>
                        </div>
                      )}

                      {/* Cycle Time */}
                      {laneConfig.cycle_seconds !== undefined && (
                        <div className="p-3 bg-gray-800/50 rounded-lg">
                          <label className="block text-xs text-gray-400 mb-1">Cycle Time</label>
                          <div className="flex items-center gap-1">
                            <Clock className="w-3 h-3 text-gray-500" />
                            <input
                              type="number"
                              value={laneConfig.cycle_seconds}
                              onChange={(e) => updateConfig(`lanes.${laneName}.cycle_seconds`, parseFloat(e.target.value))}
                              className="w-14 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                              min="0.1"
                              max="60"
                              step="0.5"
                            />
                            <span className="text-xs text-gray-500">s</span>
                          </div>
                        </div>
                      )}

                      {/* Sizing Method (read-only) */}
                      <div className="p-3 bg-gray-800/50 rounded-lg">
                        <label className="block text-xs text-gray-400 mb-1">Sizing Method</label>
                        <span className="text-sm text-white font-mono">{laneConfig.sizing_method}</span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Kelly Configuration */}
      <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => toggleSection('kelly')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Target className="w-5 h-5 text-green-400" />
            <span className="font-semibold text-white">Kelly Criterion Settings</span>
          </div>
          {expandedSections.kelly ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>

        {expandedSections.kelly && config.kelly && (
          <div className="p-4 pt-0 grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Scaling Factor */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Scaling Factor</label>
              <input
                type="number"
                value={config.kelly.scaling_factor}
                onChange={(e) => updateConfig('kelly.scaling_factor', parseFloat(e.target.value))}
                className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                min="0.1"
                max="1.0"
                step="0.05"
              />
              <p className="text-xs text-gray-500 mt-1">Fractional Kelly (25% = 0.25)</p>
            </div>

            {/* Min Fraction */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Min Fraction</label>
              <input
                type="number"
                value={config.kelly.min_fraction}
                onChange={(e) => updateConfig('kelly.min_fraction', parseFloat(e.target.value))}
                className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                min="0.01"
                max="0.25"
                step="0.01"
              />
            </div>

            {/* Max Fraction */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Max Fraction</label>
              <input
                type="number"
                value={config.kelly.max_fraction}
                onChange={(e) => updateConfig('kelly.max_fraction', parseFloat(e.target.value))}
                className="w-20 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                min="0.25"
                max="1.0"
                step="0.05"
              />
            </div>

            {/* Utilization Hard Stop */}
            <div className="bg-gray-900/50 rounded-lg p-4">
              <label className="block text-sm text-gray-400 mb-2">Util Hard Stop</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={(config.kelly.utilization_hard_stop * 100).toFixed(0)}
                  onChange={(e) => updateConfig('kelly.utilization_hard_stop', parseFloat(e.target.value) / 100)}
                  className="w-16 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
                  min="80"
                  max="100"
                  step="5"
                />
                <Percent className="w-4 h-4 text-gray-400" />
              </div>
              <p className="text-xs text-gray-500 mt-1">Stop new trades above</p>
            </div>
          </div>
        )}
      </div>

      {/* Sector Caps */}
      <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
        <button
          onClick={() => toggleSection('sectors')}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-700/30 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Activity className="w-5 h-5 text-purple-400" />
            <span className="font-semibold text-white">Sector Caps</span>
          </div>
          {expandedSections.sectors ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
        </button>

        {expandedSections.sectors && config.sector_caps && (
          <div className="p-4 pt-0 grid grid-cols-3 md:grid-cols-5 gap-3">
            {Object.entries(config.sector_caps).map(([sector, cap]) => (
              <div key={sector} className="bg-gray-900/50 rounded-lg p-3">
                <label className="block text-xs text-gray-400 mb-1 capitalize">{sector}</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={(cap * 100).toFixed(0)}
                    onChange={(e) => updateConfig(`sector_caps.${sector}`, parseFloat(e.target.value) / 100)}
                    className="w-14 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-white text-sm"
                    min="5"
                    max="50"
                    step="5"
                  />
                  <Percent className="w-3 h-3 text-gray-500" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info Box */}
      <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-300">
          <p className="font-medium">Single Source of Truth (SSOT)</p>
          <p className="text-blue-200/70 mt-1">
            This configuration is stored in <code className="bg-blue-900/50 px-1 rounded">backend/config/risk_config.json</code> and 
            drives all 5 trading lanes. Changes here are hot-reloaded without restarting the bot.
          </p>
        </div>
      </div>
    </div>
  );
};

export default RiskSettings;
