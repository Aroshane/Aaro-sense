import React, { useState, useEffect } from 'react';
import { ShieldAlert, Info, Settings, Radio } from 'lucide-react';

function ObstacleRadar({ apiBase }) {
  const [radarData, setRadarData] = useState({
    sim_mode: true,
    safety_distance_m: 2.0,
    front_laser_m: 4.0,
    right_ultrasonic_m: 4.0,
    warning_active: false
  });
  const [safetyInput, setSafetyInput] = useState(2.0);
  const [saveStatus, setSaveStatus] = useState('');

  // Fetch live obstacle distances from API
  useEffect(() => {
    const fetchRadar = async () => {
      try {
        const res = await fetch(`${apiBase}/obstacle-avoidance`);
        const data = await res.json();
        setRadarData(data);
        
        // Sync local input with backend config on first load
        if (data.safety_distance_m) {
          setSafetyInput(data.safety_distance_m);
        }
      } catch (err) {
        console.error('Failed to poll obstacle avoidance metrics', err);
      }
    };

    fetchRadar();
    const interval = setInterval(fetchRadar, 300); // High frequency polling for obstacle sweeps (300ms)
    return () => clearInterval(interval);
  }, [apiBase]);

  // Save new safety envelope limit
  const handleSaveSafety = async (e) => {
    e.preventDefault();
    setSaveStatus('Saving...');
    try {
      // 1. Fetch current config
      const cfgRes = await fetch(`${apiBase}/config`);
      const cfg = await cfgRes.json();
      
      // 2. Modify safety threshold
      if (!cfg.avoidance) cfg.avoidance = {};
      cfg.avoidance.safety_distance_m = parseFloat(safetyInput);
      cfg.avoidance.enabled = true; // Auto-enable if user updates limit
      
      // 3. Write back to config
      const saveRes = await fetch(`${apiBase}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg)
      });
      const saveData = await saveRes.json();
      if (saveData.success) {
        setSaveStatus('Safety threshold updated successfully!');
      } else {
        setSaveStatus(`Error: ${saveData.error}`);
      }
    } catch (err) {
      setSaveStatus(`Failed: ${err.message}`);
    } finally {
      setTimeout(() => setSaveStatus(''), 4000);
    }
  };

  // Convert distances (0-4m) to SVG circle radii (0-135px)
  const maxRange = 4.0;
  const radarRadius = 135;
  const center = 150;

  // Front blip coordinates (angle = 270 deg / Facing UP)
  const frontRadius = (radarData.front_laser_m / maxRange) * radarRadius;
  const frontX = center;
  const frontY = center - frontRadius;

  // Right blip coordinates (angle = 0 deg / Facing RIGHT)
  const rightRadius = (radarData.right_ultrasonic_m / maxRange) * radarRadius;
  const rightX = center + rightRadius;
  const rightY = center;

  // Safety envelope visual radius
  const safetyVisualRadius = (radarData.safety_distance_m / maxRange) * radarRadius;

  const isFrontDng = radarData.front_laser_m < radarData.safety_distance_m;
  const isRightDng = radarData.right_ultrasonic_m < radarData.safety_distance_m;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
      
      {/* Visual SVG Radar sweep */}
      <div className="glass-card card-purple" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '20px', alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Radio size={16} /> Asynchronous Proximity Sweep
        </h3>

        <div className="radar-scope-wrapper">
          <div className="radar-sweep"></div>
          
          <svg viewBox="0 0 300 300" style={{ width: '100%', height: '100%', position: 'absolute', zIndex: 5 }}>
            {/* Grid Rings */}
            <circle cx="150" cy="150" r="45" fill="none" stroke="rgba(139, 92, 246, 0.1)" strokeDasharray="3, 5" />
            <circle cx="150" cy="150" r="90" fill="none" stroke="rgba(139, 92, 246, 0.1)" strokeDasharray="3, 5" />
            <circle cx="150" cy="150" r="135" fill="none" stroke="rgba(139, 92, 246, 0.3)" />
            
            {/* Axes Lines */}
            <line x1="150" y1="15" x2="150" y2="285" stroke="rgba(139, 92, 246, 0.15)" />
            <line x1="15" y1="150" x2="285" y2="150" stroke="rgba(139, 92, 246, 0.15)" />
            
            {/* Safety distance bubble */}
            <circle 
              cx="150" cy="150" r={safetyVisualRadius} 
              fill="rgba(244, 63, 94, 0.03)" stroke="rgba(244, 63, 94, 0.3)" strokeDasharray="4, 4" 
            />

            {/* Front ToF laser blip */}
            <circle 
              cx={frontX} cy={frontY} r="7" 
              className={`radar-blip ${isFrontDng ? 'radar-blip-alert' : 'radar-blip-front'}`} 
            />
            
            {/* Right Sonic blip */}
            <circle 
              cx={rightX} cy={rightY} r="7" 
              className={`radar-blip ${isRightDng ? 'radar-blip-alert' : 'radar-blip-right'}`} 
            />

            {/* Drone center indicator */}
            <polygon points="150,142 145,153 150,150 155,153" fill="#fff" stroke="#8b5cf6" strokeWidth="1" />
          </svg>

          {/* Compass labels */}
          <div style={{ position: 'absolute', top: '8px', fontSize: '10px', fontWeight: 'bold', color: 'var(--color-cyan-light)', zIndex: 6 }}>FRONT (ToF)</div>
          <div style={{ position: 'absolute', right: '8px', fontSize: '10px', fontWeight: 'bold', color: 'var(--color-orange-light)', zIndex: 6 }}>RIGHT (Sonic)</div>
        </div>

        <div style={{ marginTop: '20px', textAlign: 'center' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Radar Max range: 4.0 meters</span>
        </div>
      </div>

      {/* Avoidance metrics console */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        
        {/* Avoidance system diagnostics */}
        <div className="glass-card card-blue">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldAlert size={16} /> Avoidance Diagnostics Console
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px', borderRadius: '10px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.04)' }}>
              <div>
                <span style={{ fontSize: '13px', fontWeight: '600', color: '#fff' }}>Collision Warning status:</span>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Triggered when obstacles cross safety limit</p>
              </div>
              <span style={{ 
                padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700',
                background: radarData.warning_active ? 'rgba(244, 63, 94, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                color: radarData.warning_active ? 'var(--color-rose-light)' : 'var(--color-green-light)',
                border: radarData.warning_active ? '1px solid rgba(244,63,94,0.4)' : '1px solid rgba(16,185,129,0.4)',
                animation: radarData.warning_active ? 'pulse-blip 0.6s infinite alternate ease-in-out' : 'none'
              }}>
                {radarData.warning_active ? '⚠️ COLLISION WARNING' : '🛡️ ENVELOPE CLEAR'}
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
              <div style={{ background: 'rgba(255, 255, 255, 0.01)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.03)' }}>
                <span style={{ color: 'var(--color-cyan-light)', fontWeight: '600', display: 'block', marginBottom: '6px' }}>Front Obstacle (VL53L1X)</span>
                <span style={{ fontSize: '24px', fontWeight: '700', color: '#fff', fontFamily: 'monospace' }}>
                  {radarData.front_laser_m.toFixed(2)} m
                </span>
                <div style={{ color: isFrontDng ? 'var(--color-rose)' : 'var(--color-green-light)', fontSize: '10px', marginTop: '6px', fontWeight: '500' }}>
                  {isFrontDng ? '⚠️ Too Close!' : '✓ Safe Distance'}
                </div>
              </div>

              <div style={{ background: 'rgba(255, 255, 255, 0.01)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.03)' }}>
                <span style={{ color: 'var(--color-orange-light)', fontWeight: '600', display: 'block', marginBottom: '6px' }}>Right Obstacle (HC-SR04)</span>
                <span style={{ fontSize: '24px', fontWeight: '700', color: '#fff', fontFamily: 'monospace' }}>
                  {radarData.right_ultrasonic_m.toFixed(2)} m
                </span>
                <div style={{ color: isRightDng ? 'var(--color-rose)' : 'var(--color-green-light)', fontSize: '10px', marginTop: '6px', fontWeight: '500' }}>
                  {isRightDng ? '⚠️ Too Close!' : '✓ Safe Distance'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Safety distance configuration card */}
        <div className="glass-card card-green">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Settings size={16} /> Safety Envelope Settings
          </h3>

          <form onSubmit={handleSaveSafety} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                <span>Safety Threshold Distance:</span>
                <span style={{ color: '#fff', fontWeight: '600' }}>{safetyInput} meters</span>
              </div>
              <input 
                type="range" min="0.5" max="3.5" step="0.1" 
                style={{ width: '100%', cursor: 'pointer', accentColor: 'var(--color-green)' }}
                value={safetyInput} onChange={(e) => setSafetyInput(e.target.value)} 
              />
            </div>

            <button type="submit" className="gcs-button" style={{ marginTop: '4px' }}>
              Update Safety Threshold
            </button>

            {saveStatus && (
              <div style={{ fontSize: '11px', color: 'var(--color-green-light)', textAlign: 'center', fontStyle: 'italic' }}>
                {saveStatus}
              </div>
            )}
          </form>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px', background: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.15)', borderRadius: '10px' }}>
          <Info size={16} style={{ color: 'var(--color-blue-light)', flexShrink: 0, marginTop: '2px' }} />
          <p style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.4' }}>
            When obstacle avoidance is enabled, warnings are sent directly via MAVLink (`OBSTACLE_DISTANCE` message #330) to the Pixhawk flight controller at 10 Hz to coordinate path deviations.
          </p>
        </div>
      </div>

    </div>
  );
}

export default ObstacleRadar;
