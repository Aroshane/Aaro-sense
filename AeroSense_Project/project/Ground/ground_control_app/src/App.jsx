import React, { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import MissionPlanner from './components/MissionPlanner';
import ObstacleRadar from './components/ObstacleRadar';
import AIPredictor from './components/AIPredictor';
import ConfigManager from './components/ConfigManager';
import RainAnimation from './components/RainAnimation';
import CloudBackground from './components/CloudBackground';
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

const MOCK_TELEMETRY = Array.from({ length: 35 }, (_, i) => {
  const t = Date.now() / 1000 - (35 - i) * 2;
  const alt = Math.min(50, 15 + Math.sin(i / 3) * 15 + i * 0.8);
  return {
    timestamp: t,
    lat: 8.8932 + Math.sin(i / 5) * 0.0004,
    lon: 76.6141 + Math.cos(i / 5) * 0.0004,
    alt_m: parseFloat(alt.toFixed(1)),
    pm25: parseFloat((25 + Math.sin(i / 2) * 12 + (alt > 30 ? 25 : 5)).toFixed(1)),
    pm10: parseFloat((45 + Math.sin(i / 2) * 20 + (alt > 30 ? 40 : 10)).toFixed(1)),
    temperature: parseFloat((28.5 + alt * 0.05 + (i % 3) * 0.2).toFixed(1)),
    humidity: parseFloat((65.0 - alt * 0.1).toFixed(1)),
    pressure: parseFloat((1012.0 - alt * 0.12).toFixed(1)),
    voc: parseFloat((1.2 + (i % 5) * 0.1).toFixed(2)),
    mq135_raw: 195 + (i % 10) * 2,
    quality_flag: 0,
    gps_quality: 3
  };
});

const MOCK_STATS = {
  points: 154,
  duration: '12.5 min',
  alt_range: '15.0 - 50.0 m',
  pm25_mean: '34.2 µg/m³',
  pm25_max: '68.5 µg/m³',
  temp_mean: '29.1 °C',
  hum_mean: '63.4 %'
};

const DEFAULT_CONFIG = {
  drone_id: "AEROSENSE-QUAD-01",
  firmware_version: "2.4.0-PROD",
  baud_rate: 115200,
  telemetry_interval_ms: 1000,
  sensors: {
    bme280: { enabled: true, address: "0x76", i2c_bus: 1 },
    sds011: { enabled: true, uart_port: "/dev/ttyS0", sample_sec: 1 },
    vl53l1x: { enabled: true, address: "0x29", timing_budget_ms: 50 },
    mq135: { enabled: true, adc_pin: 34, R0_kOhm: 76.8 }
  },
  lora: {
    frequency_mhz: 868.0,
    tx_power_dbm: 14,
    bandwidth_khz: 125.0,
    spreading_factor: 7,
    coding_rate: 5
  },
  thresholds: {
    pm25_warning: 60.0,
    pm25_critical: 120.0,
    temp_warning: 38.0,
    battery_min_volts: 14.2
  },
  storage: {
    sd_mount_point: "/sd",
    log_file_format: "CSV",
    max_file_size_mb: 50
  }
};

function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [telemetry, setTelemetry] = useState(MOCK_TELEMETRY);
  const [stats, setStats] = useState(MOCK_STATS);
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [apiOnline, setApiOnline] = useState(false);
  const [refreshCount, setRefreshCount] = useState(0);

  // Poll telemetry and status
  useEffect(() => {
    const fetchData = async () => {
      try {
        const statusRes = await fetch(`${API_BASE}/status`);
        if (!statusRes.ok) throw new Error(`HTTP ${statusRes.status}`);
        const statusData = await statusRes.json();
        const isOnline = statusData.status === 'online';
        setApiOnline(isOnline);

        if (isOnline) {
          const telRes = await fetch(`${API_BASE}/telemetry?limit=150`);
          const telData = await telRes.json();
          if (Array.isArray(telData) && telData.length > 0) {
            setTelemetry(telData);
          }

          const statsRes = await fetch(`${API_BASE}/stats`);
          const statsData = await statsRes.json();
          if (statsData.points) {
            setStats(statsData);
          }
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
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.drone_id) setConfig(data);
      } catch (err) {
        console.warn('Backend API unreachable, using default payload config', err);
        setConfig(prev => prev || DEFAULT_CONFIG);
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

  // Compare telemetry with user threshold limits
  const pm25Limit = config && config.thresholds ? config.thresholds.pm25_warning : 60.0;
  const tempLimit = config && config.thresholds ? config.thresholds.temp_warning : 38.0;
  const pm25Alert = apiOnline && latestData.pm25 > pm25Limit;
  const tempAlert = apiOnline && latestData.temperature > tempLimit;
  const isAnyAlert = pm25Alert || tempAlert;

  // Compute status metrics
  const isHealthy = latestData.quality_flag === 0;
  // Indian National AQI PM2.5 categories (µg/m³):
  // 0-30: Good, 31-60: Satisfactory, 61-90: Moderate, 91-120: Poor, 121-250: Very Poor, >250: Severe
  const pVal = latestData.pm25 || 0;
  const aqiLabel = pVal <= 30 ? 'Good' : pVal <= 60 ? 'Satisfactory' : pVal <= 90 ? 'Moderate' : pVal <= 120 ? 'Poor' : pVal <= 250 ? 'Very Poor' : 'Severe';
  const aqiClass = pVal <= 30 ? 'marquee-success' : pVal <= 60 ? 'marquee-success' : pVal <= 90 ? 'marquee-info' : pVal <= 120 ? 'marquee-warning' : 'marquee-danger';
  const aqiDot = pVal <= 30 ? 'marquee-success-dot' : pVal <= 60 ? 'marquee-success-dot' : pVal <= 90 ? 'marquee-info-dot' : pVal <= 120 ? 'marquee-warning-dot' : 'marquee-danger-dot';

  return (
    <>
      <div className="bg-grid"></div>
      <div className="bg-spotlight"></div>
      <RainAnimation humidity={latestData.humidity || 80} />
      <CloudBackground />
      
      <div className="gcs-container">
        {isAnyAlert && (
          <div className="blink-alert-banner" style={{ background: 'rgba(244, 63, 94, 0.15)', border: '1.5px solid var(--color-rose)', borderRadius: '12px', padding: '12px 20px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '12px', boxShadow: '0 0 15px rgba(244, 63, 94, 0.25)', animation: 'alert-blink 1s infinite alternate' }}>
            <span style={{ fontSize: '20px' }}>⚠️</span>
            <div style={{ flex: '1' }}>
              <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#fff', display: 'block' }}>GCS CRITICAL PARAMETER ALERT</span>
              <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.7)', margin: 0 }}>
                {pm25Alert && `PM2.5 Index is high: ${latestData.pm25.toFixed(1)} µg/m³ (Limit: ${pm25Limit} µg/m³). `}
                {tempAlert && `Atmospheric Temperature is high: ${latestData.temperature.toFixed(1)}°C (Limit: ${tempLimit}°C).`}
              </p>
            </div>
          </div>
        )}

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
            <Dashboard 
              telemetry={telemetry} 
              stats={stats} 
              apiOnline={apiOnline} 
              thresholds={config && config.thresholds} 
              pm25Alert={pm25Alert} 
              tempAlert={tempAlert} 
            />
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
