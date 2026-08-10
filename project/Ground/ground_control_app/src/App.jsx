import React, { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import MissionPlanner from './components/MissionPlanner';
import ObstacleRadar from './components/ObstacleRadar';
import AIPredictor from './components/AIPredictor';
import ConfigManager from './components/ConfigManager';
import { 
  Activity, 
  MapPin, 
  ShieldAlert, 
  TrendingUp, 
  Settings, 
  Plane,
  RefreshCw
} from 'lucide-react';

const API_BASE = window.location.origin === 'http://localhost:5173' ? 'http://localhost:5001/api' : '/api';

function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [telemetry, setTelemetry] = useState([]);
  const [stats, setStats] = useState({
    points: 0, duration: '0.0 min', alt_range: '0-0 m',
    pm25_mean: '0.0 µg/m³', pm25_max: '0.0 µg/m³',
    temp_mean: '0.0 °C', hum_mean: '0.0 %'
  });
  const [config, setConfig] = useState(null);
  const [apiOnline, setApiOnline] = useState(false);
  const [refreshCount, setRefreshCount] = useState(0);

  // Poll telemetry and status
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Status Check
        const statusRes = await fetch(`${API_BASE}/status`);
        const statusData = await statusRes.json();
        setApiOnline(statusData.status === 'online');

        if (statusData.status === 'online') {
          // Telemetry Check
          const telRes = await fetch(`${API_BASE}/telemetry?limit=150`);
          const telData = await telRes.json();
          setTelemetry(telData);

          // Stats Check
          const statsRes = await fetch(`${API_BASE}/stats`);
          const statsData = await statsRes.json();
          setStats(statsData);
        }
      } catch (err) {
        setApiOnline(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [refreshCount]);

  // Load config once on startup
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch(`${API_BASE}/config`);
        const data = await res.json();
        setConfig(data);
      } catch (err) {
        console.error('Failed to load payload config', err);
      }
    };
    fetchConfig();
  }, [refreshCount]);

  const handleConfigSaved = () => {
    setRefreshCount(prev => prev + 1);
  };

  // Get current readings for live display
  const latestData = telemetry[telemetry.length - 1] || {
    pm25: 0, pm10: 0, temperature: 0, humidity: 0, pressure: 0, alt_m: 0, quality_flag: 0, gps_quality: 0
  };

  // Compute status metrics
  const isHealthy = latestData.quality_flag === 0;
  const aqiLabel = latestData.pm25 <= 12 ? 'Good' : latestData.pm25 <= 35 ? 'Moderate' : latestData.pm25 <= 55 ? 'Unhealthy' : 'Hazardous';
  const aqiClass = latestData.pm25 <= 12 ? 'marquee-success' : latestData.pm25 <= 35 ? 'marquee-info' : 'marquee-warning';
  const aqiDot = latestData.pm25 <= 12 ? 'marquee-success-dot' : latestData.pm25 <= 35 ? 'marquee-info-dot' : 'marquee-warning-dot';

  return (
    <>
      <div className="bg-grid"></div>
      <div className="bg-spotlight"></div>
      
      <div className="gcs-container">
        {/* Navbar Title and Stats */}
        <header style={{ display: 'flex', alignItems: 'center', gap: '20px', marginBottom: '24px' }}>
          <div style={{ fontSize: '36px' }}>🛸</div>
          <div>
            <h1 style={{ fontFamily: 'Orbitron', margin: 0, fontSize: '26px', fontWeight: '800', letterSpacing: '-0.5px' }}>
              AeroSense GCS
            </h1>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-muted)' }}>
              Quadcopter 3D Spatial Pollution Mapping — Ground Control Cockpit
            </p>
          </div>
          
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '12px' }}>
            <div className={`stat-badge stat-purple ${activeTab === 'overview' ? 'active-purple' : ''}`}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Fly points</div>
              <div style={{ fontFamily: 'Orbitron', fontSize: '16px', fontWeight: '700', color: '#fff' }}>{stats.points} pts</div>
            </div>
            
            <div className={`stat-badge stat-blue ${activeTab === 'overview' ? 'active-blue' : ''}`}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Time aloft</div>
              <div style={{ fontFamily: 'Orbitron', fontSize: '16px', fontWeight: '700', color: '#fff' }}>{stats.duration}</div>
            </div>

            <div className={`stat-badge stat-green ${activeTab === 'overview' ? 'active-green' : ''}`}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Avg PM2.5</div>
              <div style={{ fontFamily: 'Orbitron', fontSize: '16px', fontWeight: '700', color: '#fff' }}>{stats.pm25_mean}</div>
            </div>
          </div>
        </header>

        {/* Tab Links */}
        <nav className="navbar-container">
          <button 
            className={`nav-link ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <Activity size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-top' }} />
            Overview Telemetry
          </button>
          
          <button 
            className={`nav-link ${activeTab === 'mission' ? 'active' : ''}`}
            onClick={() => setActiveTab('mission')}
          >
            <MapPin size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-top' }} />
            Waypoints & Mission
          </button>

          <button 
            className={`nav-link ${activeTab === 'radar' ? 'active' : ''}`}
            onClick={() => setActiveTab('radar')}
          >
            <ShieldAlert size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-top' }} />
            Obstacle Radar
          </button>

          <button 
            className={`nav-link ${activeTab === 'ai' ? 'active' : ''}`}
            onClick={() => setActiveTab('ai')}
          >
            <TrendingUp size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-top' }} />
            AI Forecasts
          </button>

          <button 
            className={`nav-link ${activeTab === 'config' ? 'active' : ''}`}
            onClick={() => setActiveTab('config')}
          >
            <Settings size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-top' }} />
            Device Config
          </button>
          
          <button 
            onClick={() => setRefreshCount(prev => prev + 1)}
            className="nav-link"
            title="Reload Config & Stats"
            style={{ padding: '8px 12px' }}
          >
            <RefreshCw size={14} />
          </button>
        </nav>

        {/* Ticker Marquee Status bar */}
        <div className="marquee-container">
          <div className="marquee-content">
            <div className="marquee-item">
              <div className={`marquee-dot ${apiOnline ? 'marquee-success-dot' : 'marquee-warning-dot'}`}></div>
              <span className="marquee-label">GCS SERVER STATUS:</span>
              <span className={`marquee-value ${apiOnline ? 'marquee-success' : 'marquee-warning'}`}>
                {apiOnline ? 'ONLINE / REALTIME INGESTION ACTIVE' : 'OFFLINE / STANDBY MODE'}
              </span>
            </div>
            
            <div className="marquee-item">
              <div className="marquee-dot marquee-info-dot"></div>
              <span className="marquee-label">DRONE ALTITUDE:</span>
              <span className="marquee-value marquee-info">{latestData.alt_m.toFixed(1)} m AGL</span>
            </div>

            <div className="marquee-item">
              <div className={`marquee-dot ${aqiDot}`}></div>
              <span className="marquee-label">AIR INDEX (PM2.5):</span>
              <span className={`marquee-value ${aqiClass}`}>{latestData.pm25.toFixed(1)} µg/m³ ({aqiLabel})</span>
            </div>

            <div className="marquee-item">
              <div className="marquee-dot marquee-success-dot"></div>
              <span className="marquee-label">METEOROLOGICAL SENSORS:</span>
              <span className="marquee-value marquee-success">T={latestData.temperature.toFixed(1)}°C | RH={latestData.humidity.toFixed(1)}%</span>
            </div>

            <div className="marquee-item">
              <div className="marquee-dot marquee-info-dot"></div>
              <span className="marquee-label">GPS STATUS:</span>
              <span className="marquee-value marquee-info">3D Fused Fix ({latestData.gps_quality} satellites)</span>
            </div>

            {/* Repeated for scrolling loop */}
            <div className="marquee-item">
              <div className={`marquee-dot ${apiOnline ? 'marquee-success-dot' : 'marquee-warning-dot'}`}></div>
              <span className="marquee-label">GCS SERVER STATUS:</span>
              <span className={`marquee-value ${apiOnline ? 'marquee-success' : 'marquee-warning'}`}>
                {apiOnline ? 'ONLINE / REALTIME INGESTION ACTIVE' : 'OFFLINE / STANDBY MODE'}
              </span>
            </div>
            
            <div className="marquee-item">
              <div className="marquee-dot marquee-info-dot"></div>
              <span className="marquee-label">DRONE ALTITUDE:</span>
              <span className="marquee-value marquee-info">{latestData.alt_m.toFixed(1)} m AGL</span>
            </div>

            <div className="marquee-item">
              <div className={`marquee-dot ${aqiDot}`}></div>
              <span className="marquee-label">AIR INDEX (PM2.5):</span>
              <span className={`marquee-value ${aqiClass}`}>{latestData.pm25.toFixed(1)} µg/m³ ({aqiLabel})</span>
            </div>
          </div>
        </div>

        {/* Tab Routing Renders */}
        <main>
          {activeTab === 'overview' && (
            <Dashboard telemetry={telemetry} stats={stats} apiOnline={apiOnline} />
          )}
          {activeTab === 'mission' && (
            <MissionPlanner apiBase={API_BASE} />
          )}
          {activeTab === 'radar' && (
            <ObstacleRadar apiBase={API_BASE} />
          )}
          {activeTab === 'ai' && (
            <AIPredictor apiBase={API_BASE} />
          )}
          {activeTab === 'config' && (
            <ConfigManager 
              config={config} 
              onSaved={handleConfigSaved} 
              apiBase={API_BASE}
            />
          )}
        </main>

        <footer style={{ textAlign: 'right', fontSize: '11px', color: 'var(--text-dark)', marginTop: '30px', fontFamily: 'monospace' }}>
          AeroSense GCS Cockpit v1.2.0 | Flight DB: data/aerosense.db
        </footer>
      </div>
    </>
  );
}

export default App;
