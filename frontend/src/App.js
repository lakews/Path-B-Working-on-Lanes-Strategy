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
      toast.success('Trading bot started');
      fetchStatus();
    } catch (e) {
      toast.error('Failed to start bot');
    }
  };

  const stopBot = async () => {
    try {
      await axios.post(`${API}/bot/stop`);
      toast.warning('Trading bot stopped');
      fetchStatus();
    } catch (e) {
      toast.error('Failed to stop bot');
    }
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
                  <Link to="/config" className="text-white/80 hover:text-white transition text-sm font-medium" data-testid="config-nav-link">Config</Link>
                </nav>
              </div>
              
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 px-4 py-2 rounded-lg backdrop-blur-sm bg-white/5 border border-white/10">
                  <div className={`w-2 h-2 rounded-full ${ botRunning ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} data-testid="bot-status-indicator"></div>
                  <span className="text-sm text-white/90">{botRunning ? 'Active' : 'Stopped'}</span>
                </div>
                
                <button
                  onClick={botRunning ? stopBot : startBot}
                  data-testid="bot-toggle-button"
                  className={`px-6 py-2 rounded-lg font-medium transition-all ${
                    botRunning 
                      ? 'bg-red-500 hover:bg-red-600 text-white shadow-lg shadow-red-500/30' 
                      : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white shadow-lg shadow-cyan-500/30'
                  }`}
                >
                  {botRunning ? 'Stop Trading' : 'Start Trading'}
                </button>
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
            <Route path="/config" element={<Configuration />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;