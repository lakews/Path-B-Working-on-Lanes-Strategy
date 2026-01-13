import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Settings, Save } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Configuration = () => {
  const [config, setConfig] = useState({
    trades_per_10min: 500,
    initial_capital: 100,
    capital_deployment_pct: 80,
    max_position_size_pct: 3
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setConfig(response.data.configuration || config);
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
      toast.success('Configuration updated successfully');
    } catch (e) {
      toast.error('Failed to update configuration');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96" data-testid="config-loading">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6" data-testid="configuration-page">
      <div className="flex items-center gap-3">
        <Settings className="w-8 h-8 text-cyan-400" />
        <div>
          <h2 className="text-2xl font-bold text-white">Trading Configuration</h2>
          <p className="text-white/60 text-sm">Adjust trading parameters (restart bot for changes to take effect)</p>
        </div>
      </div>

      <div className="rounded-xl bg-white/5 backdrop-blur-xl border border-white/10 p-8 space-y-8">
        {/* Trading Frequency */}
        <div>
          <label className="block text-sm font-medium text-white mb-2" data-testid="trades-per-10min-label">
            Trading Frequency
          </label>
          <p className="text-xs text-white/60 mb-3">Target number of trades every 10 minutes</p>
          <input
            type="number"
            data-testid="trades-per-10min-input"
            value={config.trades_per_10min || ''}
            onChange={(e) => setConfig({...config, trades_per_10min: parseInt(e.target.value) || 0})}
            className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:border-cyan-500 transition"
            min="1"
            max="10000"
          />
          <p className="text-xs text-cyan-400 mt-2">Current: {config.trades_per_10min} trades / 10 min</p>
        </div>

        {/* Initial Capital */}
        <div>
          <label className="block text-sm font-medium text-white mb-2" data-testid="initial-capital-label">
            Initial Capital ($)
          </label>
          <p className="text-xs text-white/60 mb-3">Total capital available for trading</p>
          <input
            type="number"
            data-testid="initial-capital-input"
            value={config.initial_capital || ''}
            onChange={(e) => setConfig({...config, initial_capital: parseFloat(e.target.value) || 0})}
            className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:border-cyan-500 transition"
            min="1"
            step="0.01"
          />
        </div>

        {/* Capital Deployment */}
        <div>
          <label className="block text-sm font-medium text-white mb-2" data-testid="capital-deployment-label">
            Capital Deployment (%)
          </label>
          <p className="text-xs text-white/60 mb-3">Percentage of capital to actively deploy</p>
          <div className="flex items-center gap-4">
            <input
              type="range"
              data-testid="capital-deployment-slider"
              value={config.capital_deployment_pct || 0}
              onChange={(e) => setConfig({...config, capital_deployment_pct: parseInt(e.target.value)})}
              className="flex-1"
              min="10"
              max="100"
              step="5"
            />
            <span className="text-white font-semibold w-16 text-right">{config.capital_deployment_pct}%</span>
          </div>
          <p className="text-xs text-cyan-400 mt-2">
            Deployed: ${(config.initial_capital * config.capital_deployment_pct / 100).toFixed(2)}
          </p>
        </div>

        {/* Max Position Size */}
        <div>
          <label className="block text-sm font-medium text-white mb-2" data-testid="max-position-size-label">
            Max Position Size (%)
          </label>
          <p className="text-xs text-white/60 mb-3">Maximum position size as percentage of capital (Kelly cap)</p>
          <div className="flex items-center gap-4">
            <input
              type="range"
              data-testid="max-position-size-slider"
              value={config.max_position_size_pct || 0}
              onChange={(e) => setConfig({...config, max_position_size_pct: parseFloat(e.target.value)})}
              className="flex-1"
              min="0.5"
              max="10"
              step="0.5"
            />
            <span className="text-white font-semibold w-16 text-right">{config.max_position_size_pct}%</span>
          </div>
          <p className="text-xs text-cyan-400 mt-2">
            Max: ${(config.initial_capital * config.max_position_size_pct / 100).toFixed(2)} per position
          </p>
        </div>

        {/* Save Button */}
        <div className="pt-6 border-t border-white/10">
          <button
            onClick={handleSave}
            disabled={saving}
            data-testid="save-config-button"
            className="w-full px-6 py-3 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            <Save className="w-5 h-5" />
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>

      {/* Info Panel */}
      <div className="rounded-xl bg-gradient-to-br from-cyan-500/10 to-blue-500/10 border border-cyan-500/30 p-6">
        <h3 className="text-sm font-semibold text-cyan-400 mb-3">Configuration Notes</h3>
        <ul className="space-y-2 text-sm text-white/70">
          <li>• Higher trading frequency may improve opportunities but increases execution costs</li>
          <li>• Kelly Criterion with 25-50% fractional sizing is applied automatically</li>
          <li>• Position sizing is capped at configured max to manage risk</li>
          <li>• Circuit breakers activate if drawdown exceeds 3%</li>
          <li>• Restart the trading bot after updating configuration</li>
        </ul>
      </div>
    </div>
  );
};

export default Configuration;