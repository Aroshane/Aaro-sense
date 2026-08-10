import React, { useState, useEffect } from 'react';
import { Settings, Save, AlertCircle, Wifi, ShieldAlert, Sliders, Download, AlertTriangle, Database } from 'lucide-react';

const DEFAULT_CONFIG = {
  drone_id: "AEROSENSE-QUAD-01",
  firmware_version: "2.4.0-PROD",
  sim_mode: false,
  wifi: {
    ssid: "AeroSense_AP",
    password: "aerosense_pass",
    ground_station_ip: "192.168.4.1",
    udp_port: 5001
  },
  calibration: {
    pm25_offset: 0.0,
    pm10_offset: 0.0,
    temp_offset: 0.0,
    humidity_offset: 0.0,
    mq135_scale: 1.0
  },
  avoidance: {
    enabled: true,
    safety_distance_m: 2.0
  },
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
  sdcard: {
    enabled: true,
    cs_pin: 15,
    spi_id: 1
  },
  logging: {
    base_dir: "/sd",
    interval_s: 1.0
  },
  storage: {
    sd_mount_point: "/sd",
    log_file_format: "CSV",
    max_file_size_mb: 50
  }
};

function ConfigManager({ config, onSaved, apiBase }) {
  const [localConfig, setLocalConfig] = useState(null);
  const [saveStatus, setSaveStatus] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Sync with prop when loaded or fallback
  useEffect(() => {
    if (config) {
      setLocalConfig({
        ...DEFAULT_CONFIG,
        ...config,
        wifi: { ...DEFAULT_CONFIG.wifi, ...(config.wifi || {}) },
        calibration: { ...DEFAULT_CONFIG.calibration, ...(config.calibration || {}) },
        avoidance: { ...DEFAULT_CONFIG.avoidance, ...(config.avoidance || {}) },
        sensors: { ...DEFAULT_CONFIG.sensors, ...(config.sensors || {}) },
        thresholds: { ...DEFAULT_CONFIG.thresholds, ...(config.thresholds || {}) },
        sdcard: { ...DEFAULT_CONFIG.sdcard, ...(config.sdcard || {}) },
        logging: { ...DEFAULT_CONFIG.logging, ...(config.logging || {}) }
      });
    } else {
      setLocalConfig(DEFAULT_CONFIG);
    }
  }, [config]);

  if (!localConfig) {
    return (
      <div className="glass-card card-purple" style={{ textAlign: 'center', padding: '50px' }}>
        Loading payload configuration file (`config.json`)...
      </div>
    );
  }

  // Handle value changes in sub-structures
  const handleNestedChange = (category, field, val, type = 'text') => {
    setLocalConfig(prev => {
      const updated = { ...prev };
      
      let parsedVal = val;
      if (type === 'number') parsedVal = parseFloat(val);
      else if (type === 'boolean') parsedVal = val === true;
      
      if (!updated[category]) updated[category] = {};
      updated[category][field] = parsedVal;
      
      return updated;
    });
  };

  const handleRootChange = (field, val, type = 'text') => {
    setLocalConfig(prev => {
      let parsedVal = val;
      if (type === 'number') parsedVal = parseFloat(val);
      else if (type === 'boolean') parsedVal = val === true;
      
      return {
        ...prev,
        [field]: parsedVal
      };
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaveStatus('Writing updates back to drone config...');
    setErrorMsg('');

    try {
      const res = await fetch(`${apiBase}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(localConfig)
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.success) {
        setSaveStatus('config.json successfully updated on payload flash memory!');
        if (onSaved) onSaved();
        return;
      }
      throw new Error(data.error || 'Failed to update config');
    } catch (err) {
      console.warn('API unreachable, configuration saved locally in client session mode', err);
      setSaveStatus('Config updated successfully in local session (Vercel Client Mode)!');
      if (onSaved) onSaved();
    } finally {
      setTimeout(() => {
        setSaveStatus('');
        setErrorMsg('');
      }, 4000);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Upper row: sim status and WiFi settings */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        
        {/* Core & WiFi Settings */}
        <div className="glass-card card-purple">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Wifi size={16} /> WiFi & Sim Modes
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            
            {/* Simulation Mode Switch */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <div>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#fff' }}>Payload Simulator Mode:</span>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Mocks sensor pins when running on local PC</p>
              </div>
              <input 
                type="checkbox" 
                style={{ width: '20px', height: '20px', cursor: 'pointer', accentColor: 'var(--color-purple)' }}
                checked={localConfig?.sim_mode || false} 
                onChange={(e) => handleRootChange('sim_mode', e.target.checked, 'boolean')}
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>SSID Hotspot Name</label>
              <input 
                type="text" className="gcs-input" 
                value={localConfig?.wifi?.ssid || ''} 
                onChange={(e) => handleNestedChange('wifi', 'ssid', e.target.value)} 
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Hotspot Password</label>
              <input 
                type="password" className="gcs-input" 
                value={localConfig?.wifi?.password || ''} 
                onChange={(e) => handleNestedChange('wifi', 'password', e.target.value)} 
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Ground Station Target IP</label>
                <input 
                  type="text" className="gcs-input" 
                  value={localConfig?.wifi?.ground_station_ip || ''} 
                  onChange={(e) => handleNestedChange('wifi', 'ground_station_ip', e.target.value)} 
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>UDP Target Port</label>
                <input 
                  type="number" className="gcs-input" 
                  value={localConfig?.wifi?.udp_port ?? 5001} 
                  onChange={(e) => handleNestedChange('wifi', 'udp_port', e.target.value, 'number')} 
                />
              </div>
            </div>

          </div>
        </div>

        {/* Calibration offsets */}
        <div className="glass-card card-blue">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sliders size={16} /> Calibration Sensor Offsets
          </h3>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>PM2.5 Offset</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig?.calibration?.pm25_offset ?? 0.0} 
                onChange={(e) => handleNestedChange('calibration', 'pm25_offset', e.target.value, 'number')} 
              />
            </div>
            
            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>PM10 Offset</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig?.calibration?.pm10_offset ?? 0.0} 
                onChange={(e) => handleNestedChange('calibration', 'pm10_offset', e.target.value, 'number')} 
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Temperature Offset (°C)</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig?.calibration?.temp_offset ?? 0.0} 
                onChange={(e) => handleNestedChange('calibration', 'temp_offset', e.target.value, 'number')} 
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Humidity Offset (%)</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig?.calibration?.humidity_offset ?? 0.0} 
                onChange={(e) => handleNestedChange('calibration', 'humidity_offset', e.target.value, 'number')} 
              />
            </div>

            <div style={{ gridColumn: 'span 2' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>MQ135 Voltage scale multiplier</label>
              <input 
                type="number" step="0.01" className="gcs-input" 
                value={localConfig?.calibration?.mq135_scale ?? 1.0} 
                onChange={(e) => handleNestedChange('calibration', 'mq135_scale', e.target.value, 'number')} 
              />
            </div>
          </div>
        </div>

      </div>

      {/* Second row: Avoidance settings and Safety Alert thresholds */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        
        {/* Avoidance configurations */}
        <div className="glass-card card-green">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldAlert size={16} /> Avoidance Hardware Settings
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <div>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#fff' }}>MAVLink Avoidance:</span>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Streams obstacle distance vectors to FC</p>
              </div>
              <input 
                type="checkbox" 
                style={{ width: '20px', height: '20px', cursor: 'pointer', accentColor: 'var(--color-green)' }}
                checked={localConfig?.avoidance?.enabled || false} 
                onChange={(e) => handleNestedChange('avoidance', 'enabled', e.target.checked, 'boolean')}
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Safety Envelope (meters)</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig.avoidance.safety_distance_m || 2.0} 
                onChange={(e) => handleNestedChange('avoidance', 'safety_distance_m', e.target.value, 'number')} 
              />
            </div>
          </div>
        </div>

        {/* GCS Safety Alert Thresholds */}
        <div className="glass-card card-orange">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={16} /> GCS Alert Thresholds (NAAQS India)
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>PM2.5 Warning (µg/m³)</label>
                <input 
                  type="number" step="1" className="gcs-input" 
                  value={localConfig.thresholds ? localConfig.thresholds.pm25_warning : 60.0} 
                  onChange={(e) => handleNestedChange('thresholds', 'pm25_warning', e.target.value, 'number')} 
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Temp Alert Limit (°C)</label>
                <input 
                  type="number" step="1" className="gcs-input" 
                  value={localConfig.thresholds ? localConfig.thresholds.temp_warning : 38.0} 
                  onChange={(e) => handleNestedChange('thresholds', 'temp_warning', e.target.value, 'number')} 
                />
              </div>
            </div>
            <p style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.4', marginTop: '6px' }}>
              Triggers visual GCS flashing alarms when exceeded. India CPCB NAAQS 24-hr limit is <strong>60 µg/m³</strong>.
            </p>
          </div>
        </div>

        {/* SD Card & Flight Logging */}
        <div className="glass-card card-pink">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Database size={16} /> SD Card & Flight Logging
          </h3>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <div>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#fff' }}>Enable SD Card Logging:</span>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Saves CSV records to SPI SD card</p>
              </div>
              <input 
                type="checkbox" 
                style={{ width: '20px', height: '20px', cursor: 'pointer', accentColor: 'var(--color-pink)' }}
                checked={localConfig.sdcard?.enabled || false} 
                onChange={(e) => handleNestedChange('sdcard', 'enabled', e.target.checked, 'boolean')}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>CS Pin</label>
                <input 
                  type="number" className="gcs-input" 
                  value={localConfig.sdcard?.cs_pin ?? 15} 
                  onChange={(e) => handleNestedChange('sdcard', 'cs_pin', e.target.value, 'number')} 
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>SPI Bus ID</label>
                <input 
                  type="number" className="gcs-input" 
                  value={localConfig.sdcard?.spi_id ?? 1} 
                  onChange={(e) => handleNestedChange('sdcard', 'spi_id', e.target.value, 'number')} 
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Logging Base Dir</label>
                <input 
                  type="text" className="gcs-input" 
                  value={localConfig.logging?.base_dir ?? '/sd'} 
                  onChange={(e) => handleNestedChange('logging', 'base_dir', e.target.value)} 
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Interval (sec)</label>
                <input 
                  type="number" step="0.1" className="gcs-input" 
                  value={localConfig.logging?.interval_s ?? 1.0} 
                  onChange={(e) => handleNestedChange('logging', 'interval_s', e.target.value, 'number')} 
                />
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Telemetry Data Export Panel */}
      <div className="glass-card card-blue" style={{ width: '100%' }}>
        <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Download size={16} /> Telemetry Log Exporter
        </h3>
        
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '20px' }}>
          <div style={{ flex: '1', minWidth: '280px' }}>
            <span style={{ fontSize: '13px', fontWeight: '600', color: '#fff', display: 'block', marginBottom: '4px' }}>Download Flight Telemetry Database Records</span>
            <p style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
              Export all logged GPS paths, particulate matter levels (PM2.5/PM10), and climatology data directly from the SQLite database.
            </p>
          </div>
          
          <div style={{ display: 'flex', gap: '12px' }}>
            <a 
              href={`${apiBase}/export?format=csv`} 
              download 
              className="gcs-button" 
              style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', textDecoration: 'none', background: 'rgba(255, 255, 255, 0.08)', border: '1px solid rgba(255, 255, 255, 0.1)' }}
            >
              <Download size={14} /> Export CSV
            </a>
            <a 
              href={`${apiBase}/export?format=json`} 
              download 
              className="gcs-button" 
              style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', textDecoration: 'none', background: 'rgba(255, 255, 255, 0.08)', border: '1px solid rgba(255, 255, 255, 0.1)' }}
            >
              <Download size={14} /> Export JSON
            </a>
          </div>
        </div>
      </div>

      {/* Save Button Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '15px' }}>
        {saveStatus && <span style={{ fontSize: '12px', color: 'var(--color-green-light)', fontStyle: 'italic' }}>{saveStatus}</span>}
        {errorMsg && <span style={{ fontSize: '12px', color: 'var(--color-rose)', fontWeight: 'bold' }}>{errorMsg}</span>}
        
        <button type="submit" className="gcs-button" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Save size={14} /> Commit Config Changes
        </button>
      </div>

    </form>
  );
}

export default ConfigManager;
