import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import axios from 'axios';
import '@/App.css';
import Dashboard from './pages/Dashboard';
import Markets from './pages/Markets';
import Positions from './pages/Positions';
import Analytics from './pages/Analytics';
import Backtest from './pages/Backtest';
import Configuration from './pages/Configuration';
import StrategyTuning from './pages/StrategyTuning';
import { Toaster } from './components/ui/sonner';
import { toast } from 'sonner';
import { AlertCircle } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [botRunning, setBotRunning] = useState(false);
  const [status, setStatus] = useState(null);
  const [tradingMode, setTradingMode] = useState('stopped');
  const [showModeConfirm, setShowModeConfirm] = useState(false);
  const [pendingMode, setPendingMode] = useState(null);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setStatus(response.data);
      setBotRunning(response.data.bot_running);
      setTradingMode(response.data.trading_mode || 'stopped');
    } catch (e) {
      console.error('Error fetching status:', e);
    }
  };

  const startBot = async () => {
    try {
      await axios.post(`${API}/bot/start`);
      toast.success('Live trading bot started');
      fetchStatus();
    } catch (e) {
      toast.error(e.response?.data?.message || 'Failed to start bot');
    }
  };

  const stopBot = async () => {
    try {
      await axios.post(`${API}/bot/stop`);
      toast.warning('Live trading bot stopped');
      fetchStatus();
    } catch (e) {
      toast.error('Failed to stop bot');
    }
  };

  const handleModeSwitch = (mode) => {
    if (tradingMode !== 'stopped' && mode !== tradingMode) {
      setPendingMode(mode);
      setShowModeConfirm(true);
    }
  };

  const confirmModeSwitch = async () => {
    // Stop current mode
    if (tradingMode === 'live') {
      await stopBot();
    } else if (tradingMode === 'backtest') {
      try {
        await axios.post(`${API}/backtest/stop`);
      } catch (e) {}
    }
    
    setShowModeConfirm(false);
    setPendingMode(null);
    await fetchStatus();
    
    toast.info(`Switched to ${pendingMode} mode`);
  };

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
        <Toaster position="top-right" />
        
        {/* Header */}
        <header className="border-b border-white/10 backdrop-blur-xl bg-black/20">
          <div className="container mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-8">
                <Link to="/" className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-cyan-400 to-blue-600 rounded-lg flex items-center justify-center">
                    <span className="text-xl font-bold text-white">A</span>
                  </div>
                  <div>
                    <h1 className="text-2xl font-bold text-white" style={{fontFamily: 'Exo 2, sans-serif'}}>APEX TRADER</h1>
                    <p className="text-xs text-cyan-400">Advanced Polymarket Execution System</p>
                  </div>
                </Link>
                
                <nav className="flex gap-6">
                  <Link to="/" className="text-white/80 hover:text-white transition text-sm font-medium" data-testid="dashboard-nav-link">Dashboard</Link>
                  <Link to="/markets" className="text-white/80 hover:text-white transition text-sm font-medium" data-testid="markets-nav-link">Markets</Link>
                  <Link to="/positions" className="text-white/80 hover:text-white transition text-sm font-medium" data-testid="positions-nav-link">Positions</Link>
                  <Link to="/analytics" className="text-white/80 hover:text-white transition text-sm font-medium" data-testid="analytics-nav-link">Analytics</Link>
                  <Link to="/backtest" className="text-white/80 hover:text-white transition text-sm font-medium" data-testid="backtest-nav-link">Backtest</Link>
                  <Link to="/config" className="text-white/80 hover:text-white transition text-sm font-medium" data-testid="config-nav-link">Config</Link>
                </nav>
              </div>
              
              <div className="flex items-center gap-4">
                {/* Mode Switcher */}
                <div className="flex items-center gap-2 rounded-lg backdrop-blur-sm bg-white/5 border border-white/10 p-1">
                  <button
                    onClick={() => handleModeSwitch('live')}
                    data-testid="mode-live-button"
                    className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
                      tradingMode === 'live' 
                        ? 'bg-green-500 text-white' 
                        : 'text-white/60 hover:text-white'
                    }`}
                  >
                    Live
                  </button>
                  <button
                    onClick={() => handleModeSwitch('backtest')}
                    data-testid="mode-backtest-button"
                    className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
                      tradingMode === 'backtest' 
                        ? 'bg-orange-500 text-white' 
                        : 'text-white/60 hover:text-white'
                    }`}
                  >
                    Backtest
                  </button>
                </div>
                
                <div className="flex items-center gap-2 px-4 py-2 rounded-lg backdrop-blur-sm bg-white/5 border border-white/10">
                  <div className={`w-2 h-2 rounded-full ${
                    tradingMode === 'live' ? 'bg-green-400 animate-pulse' :
                    tradingMode === 'backtest' ? 'bg-orange-400 animate-pulse' :
                    'bg-gray-400'
                  }`} data-testid="bot-status-indicator"></div>
                  <span className="text-sm text-white/90">
                    {tradingMode === 'live' ? 'Live Trading' : 
                     tradingMode === 'backtest' ? 'Backtesting' : 
                     'Stopped'}
                  </span>
                </div>
                
                {tradingMode === 'live' && (
                  <button
                    onClick={botRunning ? stopBot : startBot}
                    data-testid="bot-toggle-button"
                    className={`px-6 py-2 rounded-lg font-medium transition-all ${
                      botRunning 
                        ? 'bg-red-500 hover:bg-red-600 text-white shadow-lg shadow-red-500/30' 
                        : 'bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white shadow-lg shadow-green-500/30'
                    }`}
                  >
                    {botRunning ? 'Stop Live' : 'Start Live'}
                  </button>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="container mx-auto px-6 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/markets" element={<Markets />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/config" element={<Configuration />} />
          </Routes>
        </main>

        {/* Mode Switch Confirmation Modal */}
        {showModeConfirm && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50" data-testid="mode-confirm-modal">
            <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-white/20 rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
              <div className="flex items-center gap-3 mb-4">
                <AlertCircle className="w-8 h-8 text-orange-400" />
                <h3 className="text-xl font-bold text-white">Confirm Mode Switch</h3>
              </div>
              
              <p className="text-white/80 mb-2">
                You are currently in <span className="font-semibold text-cyan-400">{tradingMode}</span> mode.
              </p>
              <p className="text-white/80 mb-6">
                Switching to <span className="font-semibold text-orange-400">{pendingMode}</span> mode will stop all current operations.
              </p>
              
              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 mb-6">
                <p className="text-yellow-400 text-sm font-medium">
                  ⚠️ Warning: This action will immediately halt all active trading or backtesting.
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setShowModeConfirm(false);
                    setPendingMode(null);
                  }}
                  data-testid="mode-confirm-cancel"
                  className="flex-1 px-6 py-3 rounded-lg bg-white/10 hover:bg-white/20 text-white font-medium transition"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmModeSwitch}
                  data-testid="mode-confirm-accept"
                  className="flex-1 px-6 py-3 rounded-lg bg-gradient-to-r from-orange-500 to-red-600 hover:from-orange-600 hover:to-red-700 text-white font-semibold transition shadow-lg shadow-orange-500/30"
                >
                  Confirm Switch
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </BrowserRouter>
  );
}

export default App;