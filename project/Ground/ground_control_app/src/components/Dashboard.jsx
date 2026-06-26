import React, { useEffect, useRef } from 'react';
import { 
  Shield, 
  Cpu, 
  Wifi, 
  Database,
  CheckCircle,
  AlertTriangle
} from 'lucide-react';

function Dashboard({ telemetry, stats, apiOnline }) {
  const logContainerRef = useRef(null);

  // Auto-scroll the raw telemetry logs console
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [telemetry]);

  const latest = telemetry[telemetry.length - 1] || {
    timestamp: Date.now() / 1000,
    lat: 8.8932, lon: 76.6141, alt_m: 0.0,
    pm25: 0.0, pm10: 0.0, temperature: 0.0, humidity: 0.0,
    pressure: 0.0, voc: -1.0, mq135_raw: 0.0, quality_flag: 0
  };

  const getPMColor = (val) => {
    if (val <= 12) return 'var(--color-green)';
    if (val <= 35) return 'var(--color-purple-light)';
    if (val <= 55) return 'var(--color-orange)';
    return 'var(--color-rose)';
  };

  const pm25Color = getPMColor(latest.pm25);
  const pm10Color = getPMColor(latest.pm10);

  // Compute status items based on quality_flag
  const fcDisconnected = (latest.quality_flag & 1) > 0;
  const bmeBroken = (latest.quality_flag & 2) > 0;
  const pmsBroken = (latest.quality_flag & 4) > 0;
  const obstacleWarning = (latest.quality_flag & 8) > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <h2 style={{ fontSize: '20px', fontWeight: '600', color: '#fff', borderBottom: '1px solid var(--border-color)', paddingBottom: '10px' }}>
        System Overview & Telemetry Grid
      </h2>

      {/* Overview stats cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
        
        {/* Status Indicators Card */}
        <div className="glass-card card-purple">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Cpu size={16} /> Device Interface Status
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div className="health-indicator">
              <div className={`health-dot ${apiOnline && !fcDisconnected ? 'online' : 'offline'}`}></div>
              <span style={{ fontSize: '12px' }}>Autopilot MAVLink: {fcDisconnected ? 'DISCONNECTED' : 'Pixhawk/SpeedyBee Link'}</span>
            </div>
            
            <div className="health-indicator">
              <div className={`health-dot ${apiOnline && !pmsBroken ? 'online' : 'offline'}`}></div>
              <span style={{ fontSize: '12px' }}>Laser PM Sensor: {pmsBroken ? 'FAULT' : 'PMS5003 Active'}</span>
            </div>

            <div className="health-indicator">
              <div className={`health-dot ${apiOnline && !bmeBroken ? 'online' : 'offline'}`}></div>
              <span style={{ fontSize: '12px' }}>Climate Sensor: {bmeBroken ? 'FAULT' : 'BME280 Active'}</span>
            </div>

            <div className="health-indicator">
              <div className={`health-dot ${apiOnline ? 'online' : 'offline'}`}></div>
              <span style={{ fontSize: '12px' }}>Ground Base: SX1276 LoRa RF Receiver</span>
            </div>
          </div>
        </div>

        {/* PM concentration values card */}
        <div className="glass-card card-blue">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Shield size={16} /> Air Particulates (µg/m³)
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                <span>PM2.5 Fine Particles:</span>
                <span style={{ color: pm25Color, fontWeight: '700' }}>{latest.pm25.toFixed(1)} µg/m³</span>
              </div>
              <div className="bar-track">
                <div 
                  className="bar-fill" 
                  style={{ width: `${Math.min(latest.pm25 * 1.5, 100)}%`, backgroundColor: pm25Color }}
                ></div>
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                <span>PM10 Inhalable Particles:</span>
                <span style={{ color: pm10Color, fontWeight: '700' }}>{latest.pm10.toFixed(1)} µg/m³</span>
              </div>
              <div className="bar-track">
                <div 
                  className="bar-fill" 
                  style={{ width: `${Math.min(latest.pm10 * 1.0, 100)}%`, backgroundColor: pm10Color }}
                ></div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '10px', fontSize: '12px' }}>
            <span>Max PM2.5 Ingested:</span>
            <span style={{ color: '#fff', fontWeight: '600' }}>{stats.pm25_max}</span>
          </div>
        </div>

        {/* Environmental Dials card */}
        <div className="glass-card card-green">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Wifi size={16} /> Atmospheric & Gas readings
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Temperature</span>
              <span style={{ fontSize: '20px', fontWeight: '700', color: 'var(--color-blue-light)', fontFamily: 'Orbitron' }}>
                {latest.temperature.toFixed(1)}°C
              </span>
            </div>
            
            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Humidity</span>
              <span style={{ fontSize: '20px', fontWeight: '700', color: 'var(--color-cyan-light)', fontFamily: 'Orbitron' }}>
                {latest.humidity.toFixed(1)}%
              </span>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Barometer</span>
              <span style={{ fontSize: '14px', fontWeight: '600', color: '#fff', fontFamily: 'monospace', display: 'block', marginTop: '4px' }}>
                {latest.pressure.toFixed(1)} hPa
              </span>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Gas Sensor (MQ135)</span>
              <span style={{ fontSize: '14px', fontWeight: '600', color: 'var(--color-orange-light)', fontFamily: 'monospace', display: 'block', marginTop: '4px' }}>
                {latest.mq135_raw.toFixed(3)} V
              </span>
            </div>
          </div>
        </div>

      </div>

      {/* Raw Payload Log Console */}
      <div className="glass-card card-pink" style={{ marginTop: '10px' }}>
        <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Database size={16} /> Live Drone GCS Data Log (Polling 2s)
        </h3>
        
        <div ref={logContainerRef} className="log-container">
          {telemetry.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '50px 0' }}>
              Waiting for live telemetry stream... Start the payload simulation in `main.py`
            </div>
          ) : (
            telemetry.map((pt, i) => {
              const dt = new Date(pt.timestamp * 1000).toLocaleTimeString();
              const qStr = pt.quality_flag === 0 ? 'OK' : `ERR_0x${pt.quality_flag.toString(16).toUpperCase()}`;
              return (
                <div key={pt.id || i} className="log-item">
                  <span className="log-time">[{dt}]</span>
                  <span style={{ color: '#fff', fontWeight: '600' }}>GPS({pt.gps_quality})</span>{' '}
                  <span style={{ color: 'var(--color-blue-light)' }}>lat={pt.lat.toFixed(5)},lon={pt.lon.toFixed(5)} alt={pt.alt_m.toFixed(1)}m</span>{' | '}
                  <span style={{ color: 'var(--color-purple-light)' }}>PM2.5={pt.pm25.toFixed(1)} PM10={pt.pm10.toFixed(1)}</span>{' | '}
                  <span style={{ color: 'var(--color-green-light)' }}>T={pt.temperature.toFixed(1)}°C RH={pt.humidity.toFixed(1)}%</span>{' | '}
                  <span style={{ color: pt.quality_flag === 0 ? 'var(--color-green-light)' : 'var(--color-rose)' }}>Q={qStr}</span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
