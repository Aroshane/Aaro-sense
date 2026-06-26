import React, { useState, useEffect } from 'react';
import { TrendingUp, Cpu, Info, BarChart2, Plus } from 'lucide-react';

function AIPredictor({ apiBase }) {
  const [predictionData, setPredictionData] = useState(null);
  const [customProfile, setCustomProfile] = useState({
    pm25_15: 22.0, pm25_30: 45.0, pm25_50: 70.0,
    temp_15: 27.5, temp_30: 29.0, temp_50: 30.5,
    pressure_15: 1011.0, pressure_30: 1010.2, pressure_50: 1009.5,
    humidity_15: 70, humidity_30: 67, humidity_50: 64,
    temp_gradient_15_50: 3.0,
    pressure_gradient_15_50: -1.5,
    hour_of_day: 7
  });
  const [isPredicting, setIsPredicting] = useState(false);
  const [useLive, setUseLive] = useState(true);

  const fetchPrediction = async (profileObj = null) => {
    setIsPredicting(true);
    try {
      const url = `${apiBase}/prediction/predict`;
      const config = {
        method: profileObj ? 'POST' : 'GET',
        headers: { 'Content-Type': 'application/json' }
      };
      if (profileObj) {
        config.body = JSON.stringify(profileObj);
      }

      const res = await fetch(url, config);
      const data = await res.json();
      if (data.success) {
        setPredictionData(data);
        if (!profileObj) {
          // Sync custom form values to latest live values
          setCustomProfile(data.profile);
        }
      }
    } catch (err) {
      console.error('Failed to load predictions', err);
    } finally {
      setIsPredicting(false);
    }
  };

  useEffect(() => {
    fetchPrediction();
  }, [useLive]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    const val = parseFloat(value);
    setCustomProfile(prev => {
      const updated = { ...prev, [name]: isNaN(val) ? value : val };
      
      // Update gradients dynamically
      if (name.includes('temp_')) {
        updated.temp_gradient_15_50 = updated.temp_50 - updated.temp_15;
      }
      if (name.includes('pressure_')) {
        updated.pressure_gradient_15_50 = updated.pressure_50 - updated.pressure_15;
      }
      return updated;
    });
  };

  const handleFormPredict = (e) => {
    e.preventDefault();
    setUseLive(false);
    fetchPrediction(customProfile);
  };

  if (!predictionData) {
    return (
      <div className="glass-card card-purple" style={{ textAlign: 'center', padding: '50px' }}>
        Loading vertical prediction profile models...
      </div>
    );
  }

  // Feature Importance sort
  const importances = predictionData.model_metadata.importances || {};
  const sortedImportances = Object.entries(importances)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const profile = predictionData.profile;
  const isMorning = profile.hour_of_day >= 5 && profile.hour_of_day < 9;
  const isMidday = profile.hour_of_day >= 11 && profile.hour_of_day < 16;
  const tempGrad = profile.temp_gradient_15_50;
  
  let stabilityLabel = 'Atmospheric Stability: Neutral';
  let stabilityColor = 'var(--color-blue-light)';
  let stabilityDesc = 'Normal lapse rate. Convective mixing is active, keeping pollutants distributed.';
  
  if (tempGrad > 1.0) {
    stabilityLabel = '⚠️ Strong Temperature Inversion (Stable)';
    stabilityColor = 'var(--color-orange)';
    stabilityDesc = 'Warm air aloft traps cooler, polluted air near the surface. PM2.5 levels are highly likely to mix down as the surface warms.';
  } else if (tempGrad < -0.5) {
    stabilityLabel = '✓ Unstable Atmospheric Boundary (Mixed)';
    stabilityColor = 'var(--color-green-light)';
    stabilityDesc = 'Active thermal currents are scattering particulates aloft. Lower risk of high ground concentrations.';
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '20px' }}>
      
      {/* Forecasting panels */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        
        {/* Main prediction result card */}
        <div className="glass-card card-purple">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TrendingUp size={16} /> Hyperlocal PM2.5 forecast (Horizon: +15 minutes)
          </h3>

          <div style={{ display: 'flex', gap: '24px', alignItems: 'center', marginBottom: '18px' }}>
            <div style={{ flex: '1', background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.04)', textAlign: 'center' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>
                CURRENT GROUND PM2.5
              </span>
              <span style={{ fontSize: '32px', fontWeight: '800', fontFamily: 'Orbitron', color: '#fff' }}>
                {profile.pm25_15.toFixed(1)} <span style={{ fontSize: '14px', fontWeight: '400', fontFamily: 'sans-serif' }}>µg/m³</span>
              </span>
            </div>

            <div style={{ flex: '1.2', background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.12) 0%, rgba(12, 14, 30, 0.8) 100%)', padding: '20px', borderRadius: '12px', border: '1.5px solid var(--border-color-glow)', textAlign: 'center', boxShadow: '0 0 15px rgba(139, 92, 246, 0.15)' }}>
              <span style={{ fontSize: '11px', color: 'var(--color-purple-light)', textTransform: 'uppercase', display: 'block', marginBottom: '6px', fontWeight: '600' }}>
                PREDICTED GROUND PM2.5 (+15 MIN)
              </span>
              <span style={{ fontSize: '36px', fontWeight: '800', fontFamily: 'Orbitron', color: 'var(--color-purple-light)' }}>
                {predictionData.prediction.toFixed(1)} <span style={{ fontSize: '14px', fontWeight: '400', fontFamily: 'sans-serif', color: '#fff' }}>µg/m³</span>
              </span>
            </div>
          </div>

          <div style={{ borderLeft: `3px solid ${stabilityColor}`, paddingLeft: '12px', marginBottom: '10px' }}>
            <div style={{ fontSize: '13px', fontWeight: '700', color: stabilityColor }}>{stabilityLabel}</div>
            <p style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '4px', lineHeight: '1.4' }}>{stabilityDesc}</p>
          </div>
        </div>

        {/* Profile Vertical comparison Grid */}
        <div className="glass-card card-blue">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '14px' }}>
            Vertical Atmospheric Profile Sensor Columns
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', fontSize: '12px', textAlign: 'center' }}>
            
            {/* 15m Band */}
            <div style={{ background: 'rgba(255,255,255,0.01)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.03)' }}>
              <span style={{ color: 'var(--color-green-light)', fontWeight: '700', display: 'block', marginBottom: '8px' }}>15m Band AGL</span>
              <div style={{ marginBottom: '6px' }}><span style={{ color: 'var(--text-muted)' }}>PM2.5:</span> <strong style={{ color: '#fff' }}>{profile.pm25_15.toFixed(1)}</strong></div>
              <div style={{ marginBottom: '6px' }}><span style={{ color: 'var(--text-muted)' }}>Temp:</span> <strong style={{ color: '#fff' }}>{profile.temp_15.toFixed(1)}°C</strong></div>
              <div><span style={{ color: 'var(--text-muted)' }}>Press:</span> <strong style={{ color: '#fff' }}>{profile.pressure_15.toFixed(1)}</strong></div>
            </div>

            {/* 30m Band */}
            <div style={{ background: 'rgba(255,255,255,0.01)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.03)' }}>
              <span style={{ color: 'var(--color-blue-light)', fontWeight: '700', display: 'block', marginBottom: '8px' }}>30m Band AGL</span>
              <div style={{ marginBottom: '6px' }}><span style={{ color: 'var(--text-muted)' }}>PM2.5:</span> <strong style={{ color: '#fff' }}>{profile.pm25_30.toFixed(1)}</strong></div>
              <div style={{ marginBottom: '6px' }}><span style={{ color: 'var(--text-muted)' }}>Temp:</span> <strong style={{ color: '#fff' }}>{profile.temp_30.toFixed(1)}°C</strong></div>
              <div><span style={{ color: 'var(--text-muted)' }}>Press:</span> <strong style={{ color: '#fff' }}>{profile.pressure_30.toFixed(1)}</strong></div>
            </div>

            {/* 50m Band */}
            <div style={{ background: 'rgba(255,255,255,0.01)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.03)' }}>
              <span style={{ color: 'var(--color-purple-light)', fontWeight: '700', display: 'block', marginBottom: '8px' }}>50m Band AGL</span>
              <div style={{ marginBottom: '6px' }}><span style={{ color: 'var(--text-muted)' }}>PM2.5:</span> <strong style={{ color: '#fff' }}>{profile.pm25_50.toFixed(1)}</strong></div>
              <div style={{ marginBottom: '6px' }}><span style={{ color: 'var(--text-muted)' }}>Temp:</span> <strong style={{ color: '#fff' }}>{profile.temp_50.toFixed(1)}°C</strong></div>
              <div><span style={{ color: 'var(--text-muted)' }}>Press:</span> <strong style={{ color: '#fff' }}>{profile.pressure_50.toFixed(1)}</strong></div>
            </div>

          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '12px', fontSize: '11.5px', color: 'var(--text-muted)' }}>
            <div>
              <span>Temperature Inversion Gradient (50m - 15m):</span>
              <strong style={{ color: tempGrad > 0 ? 'var(--color-orange-light)' : 'var(--color-green-light)', marginLeft: '6px' }}>
                {tempGrad > 0 ? `+${tempGrad.toFixed(2)}` : tempGrad.toFixed(2)}°C
              </strong>
            </div>
            <div>
              <span>Barometer Drop Gradient (50m - 15m):</span>
              <strong style={{ color: '#fff', marginLeft: '6px' }}>{profile.pressure_gradient_15_50.toFixed(2)} hPa</strong>
            </div>
          </div>
        </div>

      </div>

      {/* Model details and Custom what-if testing */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        
        {/* ML Model diagnostics */}
        <div className="glass-card card-green">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart2 size={16} /> Random Forest Importances
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {sortedImportances.map(([feat, imp]) => (
              <div key={feat}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '3px' }}>
                  <span>{feat}</span>
                  <span>{(imp * 100).toFixed(1)}%</span>
                </div>
                <div className="bar-track">
                  <div 
                    className="bar-fill" 
                    style={{ width: `${imp * 100}%`, backgroundColor: 'var(--color-green)' }}
                  ></div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '16px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '10px', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center' }}>
            <div>
              <span>Test split MAE:</span>
              <p style={{ color: '#fff', fontSize: '13px', fontWeight: '700', marginTop: '2px' }}>{predictionData.model_metadata.mae.toFixed(2)} µg/m³</p>
            </div>
            
            <div>
              <span>Cross-val MAE:</span>
              <p style={{ color: '#fff', fontSize: '13px', fontWeight: '700', marginTop: '2px' }}>{predictionData.model_metadata.cv_mae.toFixed(2)} µg/m³</p>
            </div>
          </div>
        </div>

        {/* Custom What-If Simulator Form */}
        <div className="glass-card card-orange">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 style={{ fontSize: '15px', color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Cpu size={16} /> what-if profile testing
            </h3>
            
            <button 
              type="button" 
              className="gcs-button-secondary" 
              style={{ fontSize: '10px', padding: '4px 8px' }}
              onClick={() => {
                setUseLive(true);
                fetchPrediction();
              }}
            >
              Sync Live
            </button>
          </div>

          <form onSubmit={handleFormPredict} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
              <div></div>
              <div style={{ textAlign: 'center' }}>PM2.5</div>
              <div style={{ textAlign: 'center' }}>Temp (°C)</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>15m Band:</span>
              <input type="number" step="0.1" name="pm25_15" value={customProfile.pm25_15} onChange={handleInputChange} className="gcs-input" style={{ padding: '4px 6px', textAlign: 'center' }} />
              <input type="number" step="0.1" name="temp_15" value={customProfile.temp_15} onChange={handleInputChange} className="gcs-input" style={{ padding: '4px 6px', textAlign: 'center' }} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>30m Band:</span>
              <input type="number" step="0.1" name="pm25_30" value={customProfile.pm25_30} onChange={handleInputChange} className="gcs-input" style={{ padding: '4px 6px', textAlign: 'center' }} />
              <input type="number" step="0.1" name="temp_30" value={customProfile.temp_30} onChange={handleInputChange} className="gcs-input" style={{ padding: '4px 6px', textAlign: 'center' }} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>50m Band:</span>
              <input type="number" step="0.1" name="pm25_50" value={customProfile.pm25_50} onChange={handleInputChange} className="gcs-input" style={{ padding: '4px 6px', textAlign: 'center' }} />
              <input type="number" step="0.1" name="temp_50" value={customProfile.temp_50} onChange={handleInputChange} className="gcs-input" style={{ padding: '4px 6px', textAlign: 'center' }} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '10px', alignItems: 'center', marginTop: '6px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '2px' }}>Hour of Day</label>
                <input type="number" min="0" max="23" name="hour_of_day" value={customProfile.hour_of_day} onChange={handleInputChange} className="gcs-input" style={{ padding: '4px 6px', textAlign: 'center' }} />
              </div>
              
              <button type="submit" disabled={isPredicting} className="gcs-button" style={{ height: '36px', marginTop: '14px' }}>
                {isPredicting ? 'Forecasting...' : 'Evaluate Forecast'}
              </button>
            </div>
          </form>
        </div>

      </div>

    </div>
  );
}

export default AIPredictor;
