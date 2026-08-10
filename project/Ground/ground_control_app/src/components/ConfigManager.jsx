import React, { useState, useEffect } from 'react';
import { Settings, Save, AlertCircle, Wifi, ShieldAlert, Sliders } from 'lucide-react';

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

      {/* Avoidance configurations */}
      <div className="glass-card card-green">
        <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldAlert size={16} /> Avoidance Hardware Settings
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <div>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#fff' }}>MAVLink Avoidance Loop:</span>
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

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '14px', background: 'rgba(16, 185, 129, 0.03)', border: '1px solid rgba(16, 185, 129, 0.15)', borderRadius: '10px' }}>
            <AlertCircle size={18} style={{ color: 'var(--color-green-light)', flexShrink: 0, marginTop: '2px' }} />
            <div>
              <span style={{ fontSize: '12px', fontWeight: '700', color: '#fff', display: 'block', marginBottom: '4px' }}>Firmware Pinout Maps</span>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                UART and I2C channel pin mapping registers are configured via source header settings. To change physical payload wiring profiles, modify properties in [WIRING_ESP32.md](file:///c:/Users/aroma/Desktop/drone/AeroSense_Project/project/docs/WIRING_ESP32.md).
              </p>
            </div>
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
