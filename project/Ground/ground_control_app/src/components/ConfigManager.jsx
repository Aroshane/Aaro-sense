import React, { useState, useEffect } from 'react';
import { Settings, Save, AlertCircle, Wifi, ShieldAlert, Sliders, Download, AlertTriangle, Database } from 'lucide-react';

function ConfigManager({ config, onSaved, apiBase }) {
  const [localConfig, setLocalConfig] = useState(null);
  const [saveStatus, setSaveStatus] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Sync with prop when loaded
  useEffect(() => {
    if (config) {
      setLocalConfig(JSON.parse(JSON.stringify(config))); // Deep clone
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
      const data = await res.json();
      if (data.success) {
        setSaveStatus('config.json successfully updated on payload flash memory!');
        if (onSaved) onSaved();
      } else {
        setErrorMsg(`Failed: ${data.error}`);
      }
    } catch (err) {
      setErrorMsg(`Network Error: ${err.message}`);
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
                checked={localConfig.sim_mode} 
                onChange={(e) => handleRootChange('sim_mode', e.target.checked, 'boolean')}
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>SSID Hotspot Name</label>
              <input 
                type="text" className="gcs-input" 
                value={localConfig.wifi.ssid} 
                onChange={(e) => handleNestedChange('wifi', 'ssid', e.target.value)} 
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Hotspot Password</label>
              <input 
                type="password" className="gcs-input" 
                value={localConfig.wifi.password} 
                onChange={(e) => handleNestedChange('wifi', 'password', e.target.value)} 
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Ground Station Target IP</label>
                <input 
                  type="text" className="gcs-input" 
                  value={localConfig.wifi.ground_station_ip} 
                  onChange={(e) => handleNestedChange('wifi', 'ground_station_ip', e.target.value)} 
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>UDP Target Port</label>
                <input 
                  type="number" className="gcs-input" 
                  value={localConfig.wifi.udp_port} 
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
                value={localConfig.calibration.pm25_offset} 
                onChange={(e) => handleNestedChange('calibration', 'pm25_offset', e.target.value, 'number')} 
              />
            </div>
            
            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>PM10 Offset</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig.calibration.pm10_offset} 
                onChange={(e) => handleNestedChange('calibration', 'pm10_offset', e.target.value, 'number')} 
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Temperature Offset (°C)</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig.calibration.temp_offset} 
                onChange={(e) => handleNestedChange('calibration', 'temp_offset', e.target.value, 'number')} 
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Humidity Offset (%)</label>
              <input 
                type="number" step="0.1" className="gcs-input" 
                value={localConfig.calibration.humidity_offset} 
                onChange={(e) => handleNestedChange('calibration', 'humidity_offset', e.target.value, 'number')} 
              />
            </div>

            <div style={{ gridColumn: 'span 2' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>MQ135 Voltage scale multiplier</label>
              <input 
                type="number" step="0.01" className="gcs-input" 
                value={localConfig.calibration.mq135_scale} 
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
                checked={localConfig.avoidance.enabled} 
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
