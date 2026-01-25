import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import { Wifi, WifiOff, Activity, Zap, Database, AlertCircle, CheckCircle2, Clock, TrendingUp } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const WebSocketHealthMonitor = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [updateHistory, setUpdateHistory] = useState([]);
  const lastUpdateCount = useRef(0);
  const [updatesPerSecond, setUpdatesPerSecond] = useState(0);

  // Fetch WebSocket status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await axios.get(`${API}/realtime/status`);
        setStatus(res.data);
        setError(null);
        
        // Calculate updates per second
        const currentUpdates = res.data?.market_service?.ws_updates_processed || 0;
        const diff = currentUpdates - lastUpdateCount.current;
        lastUpdateCount.current = currentUpdates;
        
        // Only calculate rate after first fetch
        if (lastUpdateCount.current > 0) {
          setUpdatesPerSecond(diff);
          
          // Add to history for chart (keep last 60 data points)
          setUpdateHistory(prev => {
            const newHistory = [...prev, { time: Date.now(), rate: diff }];
            return newHistory.slice(-60);
          });
        }
        
        setLoading(false);
      } catch (e) {
        console.error('Error fetching WebSocket status:', e);
        setError('Failed to fetch status');
        setLoading(false);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 1000); // Update every second for live feel
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="rounded-xl bg-gradient-to-br from-indigo-900/30 to-purple-900/30 border border-indigo-500/20 p-4">
        <div className="animate-pulse flex items-center gap-2">
          <div className="w-5 h-5 bg-indigo-500/30 rounded" />
          <div className="h-4 bg-indigo-500/30 rounded w-32" />
        </div>
      </div>
    );
  }

  const ws = status?.websocket || {};
  const ms = status?.market_service || {};
  const isConnected = ws.connected || false;
  const isHealthy = status?.health?.is_healthy || false;
  const tokenMappingReady = ms.token_mapping_ready || false;
  const droppedUpdates = ms.dropped_updates || 0;

  // Determine health status color
  const getHealthColor = () => {
    if (!isConnected) return { bg: 'from-red-900/30 to-rose-900/30', border: 'border-red-500/20', text: 'text-red-400' };
    if (droppedUpdates > 0) return { bg: 'from-yellow-900/30 to-amber-900/30', border: 'border-yellow-500/20', text: 'text-yellow-400' };
    if (!tokenMappingReady) return { bg: 'from-yellow-900/30 to-orange-900/30', border: 'border-yellow-500/20', text: 'text-yellow-400' };
    return { bg: 'from-indigo-900/30 to-purple-900/30', border: 'border-indigo-500/20', text: 'text-indigo-400' };
  };

  const colors = getHealthColor();

  return (
    <div 
      className={`rounded-xl bg-gradient-to-br ${colors.bg} ${colors.border} border p-4`}
      data-testid="websocket-health-monitor"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity className={`w-5 h-5 ${colors.text}`} />
          <h3 className="text-sm font-semibold text-white">WebSocket Health</h3>
        </div>
        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${
          isConnected ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
        }`}>
          {isConnected ? (
            <>
              <Wifi className="w-3 h-3" />
              <span>Connected</span>
              {/* Pulse indicator when receiving updates */}
              {updatesPerSecond > 0 && (
                <span className="relative flex h-2 w-2 ml-1">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                </span>
              )}
            </>
          ) : (
            <>
              <WifiOff className="w-3 h-3" />
              <span>Disconnected</span>
            </>
          )}
        </div>
      </div>

      {/* Mini Chart - Update Rate */}
      <div className="mb-3 h-12 bg-white/5 rounded-lg overflow-hidden">
        {updateHistory.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={updateHistory}>
              <YAxis domain={[0, 'auto']} hide />
              <Line 
                type="monotone" 
                dataKey="rate" 
                stroke={isConnected ? '#22c55e' : '#ef4444'} 
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-white/30 text-xs">
            Collecting data...
          </div>
        )}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs mb-3">
        <div className="p-2 rounded-lg bg-white/5">
          <div className="flex items-center gap-1 text-white/50 mb-1">
            <Zap className="w-3 h-3" />
            <span>Updates/sec</span>
          </div>
          <p className="text-lg font-bold text-white">{updatesPerSecond}</p>
        </div>
        <div className="p-2 rounded-lg bg-white/5">
          <div className="flex items-center gap-1 text-white/50 mb-1">
            <TrendingUp className="w-3 h-3" />
            <span>Total Updates</span>
          </div>
          <p className="text-lg font-bold text-white">
            {(ms.ws_updates_processed || 0).toLocaleString()}
          </p>
        </div>
      </div>

      {/* Status Indicators */}
      <div className="space-y-2 text-xs">
        {/* Token Mapping */}
        <div className="flex items-center justify-between p-2 rounded-lg bg-white/5">
          <div className="flex items-center gap-2">
            <Database className="w-3 h-3 text-white/50" />
            <span className="text-white/70">Token Mapping</span>
          </div>
          <div className="flex items-center gap-1">
            {tokenMappingReady ? (
              <>
                <CheckCircle2 className="w-3 h-3 text-green-400" />
                <span className="text-green-400">{ms.tokens_mapped || 0} tokens</span>
              </>
            ) : (
              <>
                <AlertCircle className="w-3 h-3 text-yellow-400" />
                <span className="text-yellow-400">Initializing...</span>
              </>
            )}
          </div>
        </div>

        {/* Markets Subscribed */}
        <div className="flex items-center justify-between p-2 rounded-lg bg-white/5">
          <div className="flex items-center gap-2">
            <Activity className="w-3 h-3 text-white/50" />
            <span className="text-white/70">Subscribed</span>
          </div>
          <span className="text-white font-medium">{ws.subscribed_tokens || 0} markets</span>
        </div>

        {/* Cached Prices */}
        <div className="flex items-center justify-between p-2 rounded-lg bg-white/5">
          <div className="flex items-center gap-2">
            <Database className="w-3 h-3 text-white/50" />
            <span className="text-white/70">Cached Prices</span>
          </div>
          <span className="text-white font-medium">{ms.yes_prices_cached || 0}</span>
        </div>

        {/* Dropped Updates - Only show if > 0 */}
        {droppedUpdates > 0 && (
          <div className="flex items-center justify-between p-2 rounded-lg bg-red-500/10 border border-red-500/20">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-3 h-3 text-red-400" />
              <span className="text-red-400">Dropped Updates</span>
            </div>
            <span className="text-red-400 font-medium">{droppedUpdates}</span>
          </div>
        )}
      </div>

      {/* Last Update */}
      {ws.last_message && (
        <div className="mt-3 pt-2 border-t border-white/10 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1 text-white/40">
            <Clock className="w-3 h-3" />
            <span>Last message</span>
          </div>
          <span className="text-white/60">
            {new Date(ws.last_message).toLocaleTimeString()}
          </span>
        </div>
      )}
    </div>
  );
};

export default WebSocketHealthMonitor;
