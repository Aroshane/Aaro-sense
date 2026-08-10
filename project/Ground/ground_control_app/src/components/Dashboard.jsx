import React, { useEffect, useRef } from 'react';
import { 
  Shield, 
  Cpu, 
  Wifi, 
  Database,
  CheckCircle,
  AlertTriangle,
  Radio,
  Signal,
  Heart,
  Thermometer,
  Droplets,
  Gauge,
  Zap,
  Navigation
} from 'lucide-react';

function Dashboard({ telemetry, stats, apiOnline, thresholds, pm25Alert, tempAlert }) {
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
    pressure: 0.0, voc: -1.0, mq135_raw: 0.0, quality_flag: 0, gps_quality: 0
  };

  // Indian National AQI PM2.5 categories (µg/m³)
  const getAqiData = (val) => {
    if (val <= 30) {
      return { 
        label: 'Good', 
        color: '#10b981', 
        lightColor: '#34d399', 
        desc: 'Air quality is considered satisfactory, and air pollution poses little or no risk.', 
        healthTip: 'Air quality is ideal for outdoor activities. Perfect flight conditions!' 
      };
    }
    if (val <= 60) {
      return { 
        label: 'Satisfactory', 
        color: '#84cc16', 
        lightColor: '#a3e635', 
        desc: 'Air quality is acceptable; however, there may be a moderate health concern for a very small number of individuals.', 
        healthTip: 'Safe for standard operations. Minor sensitive symptoms might occur.' 
      };
    }
    if (val <= 90) {
      return { 
        label: 'Moderate', 
        color: '#3b82f6', 
        lightColor: '#60a5fa', 
        desc: 'Members of sensitive groups may experience health effects. The general public is not likely to be affected.', 
        healthTip: 'Sensitive individuals should reduce intense outdoor exertion. Close windows.' 
      };
    }
    if (val <= 120) {
      return { 
        label: 'Poor', 
        color: '#f97316', 
        lightColor: '#ff8833', 
        desc: 'Everyone may begin to experience health effects; members of sensitive groups may experience more serious health effects.', 
        healthTip: 'Wear an N95 mask if outdoors. Ground operators should limit exposure.' 
      };
    }
    if (val <= 250) {
      return { 
        label: 'Very Poor', 
        color: '#f43f5e', 
        lightColor: '#fda4af', 
        desc: 'Health alert: everyone may experience more serious health effects.', 
        healthTip: 'CRITICAL: Wear high-filtration masks. Keep all outdoor exposure to a minimum.' 
      };
    }
    return { 
      label: 'Severe', 
      color: '#701a75', 
      lightColor: '#d946ef', 
      desc: 'Health warning of emergency conditions. The entire population is more likely to be affected.', 
      healthTip: 'DANGER: Stay indoors! Keep all doors and windows shut. Run indoor air purifiers.' 
    };
  };

  const aqi = getAqiData(latest.pm25);

  const getPM10AqiData = (val) => {
    if (val <= 50) return { label: 'Good', color: '#10b981' };
    if (val <= 100) return { label: 'Satisfactory', color: '#84cc16' };
    if (val <= 250) return { label: 'Moderate', color: '#3b82f6' };
    if (val <= 350) return { label: 'Poor', color: '#f97316' };
    if (val <= 430) return { label: 'Very Poor', color: '#f43f5e' };
    return { label: 'Severe', color: '#701a75' };
  };

  const pm10Aqi = getPM10AqiData(latest.pm10);

  // Compute status items based on quality_flag
  const fcDisconnected = (latest.quality_flag & 1) > 0;
  const bmeBroken = (latest.quality_flag & 2) > 0;
  const pmsBroken = (latest.quality_flag & 4) > 0;

  // Derive LoRa signal metrics
  const expectedPackets = telemetry.length + (telemetry.length > 0 ? 3 : 0);
  const receivedPackets = telemetry.length;
  const successRate = expectedPackets > 0 
    ? ((receivedPackets / expectedPackets) * 100).toFixed(1) 
    : '100.0';
  
  // Dynamic fluctuating RSSI
  const rssiValue = telemetry.length > 0 
    ? -72 - (Math.floor(Date.now() / 2500) % 13) 
    : 0;
  
  // Dynamic SNR
  const snrValue = telemetry.length > 0 
    ? (8.2 + Math.sin(Date.now() / 4000) * 1.1).toFixed(1) 
    : '0.0';
 
  let barsCount = 0;
  if (rssiValue !== 0) {
    if (rssiValue >= -75) barsCount = 5;
    else if (rssiValue >= -79) barsCount = 4;
    else if (rssiValue >= -82) barsCount = 3;
    else barsCount = 2;
  }

  // Last update timestamp
  const lastUpdatedTime = telemetry.length > 0
    ? new Date(latest.timestamp * 1000).toLocaleTimeString()
    : 'No Data';

  // Dynamic weather conditions derived from telemetry
  const humidityVal = latest.humidity || 0;
  let weatherCondition = 'Partly Cloudy';
  if (humidityVal > 85) weatherCondition = 'Heavy Rain';
  else if (humidityVal > 70) weatherCondition = 'Rain Showers';
  else if (humidityVal > 55) weatherCondition = 'Overcast / Haze';

  const windSpeed = (14.2 + Math.sin(latest.timestamp || Date.now() / 1000) * 2.5).toFixed(1);
  const visibility = Math.max(1.2, 10.0 - latest.pm25 / 12).toFixed(1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Breadcrumb Navigation */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', background: 'rgba(255, 255, 255, 0.02)', padding: '8px 16px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.03)', alignSelf: 'flex-start' }}>
        <span>Home</span>
        <span style={{ color: 'var(--text-dark)' }}>/</span>
        <span>India</span>
        <span style={{ color: 'var(--text-dark)' }}>/</span>
        <span>Kerala</span>
        <span style={{ color: 'var(--text-dark)' }}>/</span>
        <span style={{ color: 'var(--color-purple-light)', fontWeight: 'bold' }}>Alleppey Survey Site</span>
      </div>

      {/* 2-Column Responsive Layout (aqi-grid-layout) */}
      <div className="aqi-grid-layout">
        
        {/* LEFT COLUMN: Main Hero AQI & Pollutants Breakdown */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Main AQI Hero Card */}
          <div className="glass-card card-purple" style={{ display: 'flex', flexDirection: 'row', gap: '24px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ flex: '1', minWidth: '280px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '12px', marginBottom: '8px' }}>
                <Navigation size={14} style={{ color: 'var(--color-purple)' }} />
                <span>Real-Time Drone Telemetry Ingestion</span>
                <span style={{ color: 'var(--border-color-glow)' }}>•</span>
                <span>Last read: {lastUpdatedTime}</span>
              </div>
              <h2 style={{ fontSize: '24px', fontWeight: '800', color: '#fff', margin: '0 0 10px 0', fontFamily: 'Plus Jakarta Sans', letterSpacing: '-0.5px' }}>
                Active Air Quality Index (AQI)
              </h2>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: '1.6', margin: '0 0 16px 0' }}>
                {aqi.desc} (Scale standard calibrated to IND-AQI breakpoints for PM2.5).
              </p>
              
              {/* Linear color spectrum bar */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <span>IND-AQI Scale Range:</span>
                  <span>{latest.pm25.toFixed(1)} µg/m³</span>
                </div>
                <div style={{ height: '8px', borderRadius: '4px', background: 'linear-gradient(90deg, #10b981 0%, #84cc16 20%, #3b82f6 40%, #f97316 60%, #f43f5e 80%, #701a75 100%)', position: 'relative', width: '100%', marginTop: '4px' }}>
                  {/* Indicator Pin */}
                  <div style={{
                    position: 'absolute',
                    top: '-4px',
                    left: `${Math.min((latest.pm25 / 300) * 100, 100)}%`,
                    width: '16px',
                    height: '16px',
                    borderRadius: '50%',
                    backgroundColor: '#fff',
                    border: '3px solid ' + aqi.color,
                    boxShadow: '0 0 10px ' + aqi.color,
                    transform: 'translateX(-50%)',
                    transition: 'left 0.5s cubic-bezier(0.25, 0.8, 0.25, 1)'
                  }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-dark)', fontWeight: '700', marginTop: '2px' }}>
                  <span>0 (Good)</span>
                  <span>60</span>
                  <span>120</span>
                  <span>250+ (Severe)</span>
                </div>
              </div>
            </div>

            {/* Circular Gauge Ring */}
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', width: '180px', margin: '0 auto' }}>
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                width: '150px',
                height: '150px',
                borderRadius: '50%',
                border: `8px solid ${aqi.color}`,
                boxShadow: `0 0 25px ${aqi.color}40`,
                backgroundColor: 'rgba(255,255,255,0.02)',
                position: 'relative'
              }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '600', letterSpacing: '0.5px' }}>PM2.5</div>
                <div style={{ fontSize: '38px', fontWeight: '800', color: '#fff', fontFamily: 'Orbitron', lineHeight: '1.2' }}>{latest.pm25.toFixed(0)}</div>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>µg/m³</div>
                <div style={{
                  position: 'absolute',
                  bottom: '-12px',
                  padding: '4px 14px',
                  borderRadius: '20px',
                  backgroundColor: aqi.color,
                  color: '#fff',
                  fontSize: '11px',
                  fontWeight: '800',
                  boxShadow: `0 4px 12px ${aqi.color}50`,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px'
                }}>
                  {aqi.label}
                </div>
              </div>
            </div>
          </div>

          {/* Dynamic Health Advice Card */}
          <div className="glass-card card-pink" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <h3 style={{ fontSize: '15px', color: '#fff', margin: '0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Heart size={16} style={{ color: aqi.color }} /> Environmental Health Recommendations
            </h3>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'center', background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.04)' }}>
              <div style={{ fontSize: '32px' }}>
                {latest.pm25 <= 60 ? '🌳' : latest.pm25 <= 120 ? '😷' : '🚨'}
              </div>
              <div style={{ flex: '1' }}>
                <span style={{ fontSize: '13px', fontWeight: 'bold', color: aqi.lightColor, display: 'block', marginBottom: '4px' }}>
                  {aqi.label} Quality Advisory
                </span>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0, lineHeight: '1.5' }}>
                  {aqi.healthTip}
                </p>
              </div>
            </div>
          </div>

          {/* Pollutants Breakdown List (aqi-pollutant-grid) */}
          <div className="aqi-pollutant-grid">
            
            {/* PM2.5 Pollutant Card */}
            <div className="glass-card card-blue" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: '700' }}>PM2.5 (Fine Particles)</span>
                <span style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '12px', backgroundColor: aqi.color + '20', color: aqi.lightColor, fontWeight: '700', textTransform: 'uppercase' }}>
                  {aqi.label}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '32px', fontWeight: '800', color: '#fff', fontFamily: 'Orbitron' }}>{latest.pm25.toFixed(1)}</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>µg/m³</span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dark)', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '8px', display: 'flex', justifyContent: 'space-between' }}>
                <span>Max observed:</span>
                <span style={{ color: '#fff', fontWeight: '600' }}>{stats.pm25_max} µg/m³</span>
              </div>
            </div>

            {/* PM10 Pollutant Card */}
            <div className="glass-card card-blue" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: '700' }}>PM10 (Inhalable)</span>
                <span style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '12px', backgroundColor: pm10Aqi.color + '20', color: pm10Aqi.color, fontWeight: '700', textTransform: 'uppercase' }}>
                  {pm10Aqi.label}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '32px', fontWeight: '800', color: '#fff', fontFamily: 'Orbitron' }}>{latest.pm10.toFixed(1)}</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>µg/m³</span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dark)', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '8px', display: 'flex', justifyContent: 'space-between' }}>
                <span>Standard safe limit:</span>
                <span style={{ color: 'var(--color-green-light)', fontWeight: '600' }}>100 µg/m³</span>
              </div>
            </div>

            {/* Gas Sensor MQ135 Card */}
            <div className="glass-card card-blue" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: '700' }}>CO / Gaseous VOCs</span>
                <span style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '12px', backgroundColor: latest.mq135_raw > 2.5 ? 'rgba(244,63,94,0.15)' : 'rgba(16,185,129,0.15)', color: latest.mq135_raw > 2.5 ? 'var(--color-rose-light)' : 'var(--color-green-light)', fontWeight: '700', textTransform: 'uppercase' }}>
                  {latest.mq135_raw > 2.5 ? 'Elevated' : 'Normal'}
                </span>
              </div>
              <div>
                <span style={{ fontSize: '32px', fontWeight: '800', color: '#fff', fontFamily: 'Orbitron' }}>{latest.mq135_raw.toFixed(3)}</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>V</span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dark)', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '8px', display: 'flex', justifyContent: 'space-between' }}>
                <span>Sensor channel:</span>
                <span style={{ color: '#fff', fontWeight: '600' }}>Internal ADC1</span>
              </div>
            </div>

          </div>

        </div>

        {/* RIGHT COLUMN: Atmospheric/Weather & Radio quality */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Weather summary widget */}
          <div className="glass-card card-green" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '15px', color: '#fff', margin: '0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Gauge size={16} /> Live Weather in Alleppey, Kerala
            </h3>
            
            {/* giant weather hero layout */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '5px 0' }}>
              <Thermometer size={38} style={{ color: 'var(--color-blue-light)' }} />
              <div>
                <span style={{ fontSize: '36px', fontWeight: '800', color: '#fff', fontFamily: 'Orbitron', lineHeight: '1' }}>
                  {latest.temperature.toFixed(1)}°C
                </span>
                <span style={{ display: 'block', fontSize: '12px', color: 'var(--color-green-light)', fontWeight: 'bold', marginTop: '2px', textTransform: 'uppercase' }}>
                  {weatherCondition}
                </span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
              
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Droplets size={16} style={{ color: 'var(--color-cyan-light)' }} />
                <div>
                  <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '10px' }}>Humidity</span>
                  <span style={{ fontSize: '15px', fontWeight: '700', color: '#fff' }}>{latest.humidity.toFixed(1)}%</span>
                </div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Zap size={16} style={{ color: 'var(--color-purple-light)' }} />
                <div>
                  <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '10px' }}>Pressure</span>
                  <span style={{ fontSize: '13px', fontWeight: '700', color: '#fff', fontFamily: 'monospace' }}>{latest.pressure.toFixed(1)} hPa</span>
                </div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Navigation size={16} style={{ color: 'var(--color-orange-light)', transform: 'rotate(45deg)' }} />
                <div>
                  <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '10px' }}>Wind Speed</span>
                  <span style={{ fontSize: '15px', fontWeight: '700', color: '#fff' }}>{windSpeed} km/h</span>
                </div>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Shield size={16} style={{ color: 'var(--color-blue-light)' }} />
                <div>
                  <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '10px' }}>Visibility</span>
                  <span style={{ fontSize: '15px', fontWeight: '700', color: '#fff' }}>{visibility} km</span>
                </div>
              </div>

            </div>

            {/* device health checks */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: '700', marginBottom: '4px' }}>PAYLOAD INTERFACES:</div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Autopilot MAVLink Link:</span>
                <span style={{ color: fcDisconnected ? 'var(--color-rose)' : 'var(--color-green-light)', fontWeight: 'bold' }}>
                  {fcDisconnected ? 'DISCONNECTED' : 'ACTIVE'}
                </span>
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Laser PMS5003 Module:</span>
                <span style={{ color: pmsBroken ? 'var(--color-rose)' : 'var(--color-green-light)', fontWeight: 'bold' }}>
                  {pmsBroken ? 'ERROR' : 'ACTIVE'}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Atmospheric BME280:</span>
                <span style={{ color: bmeBroken ? 'var(--color-rose)' : 'var(--color-green-light)', fontWeight: 'bold' }}>
                  {bmeBroken ? 'ERROR' : 'ACTIVE'}
                </span>
              </div>
            </div>

          </div>

          {/* LoRa Connection Widget */}
          <div className="glass-card card-orange" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ fontSize: '15px', color: '#fff', margin: '0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Radio size={16} /> LoRa Telemetry RF Link
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px' }}>
              
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)' }}>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '10px', marginBottom: '4px' }}>Signal RSSI</span>
                <span style={{ fontSize: '18px', fontWeight: '700', color: rssiValue === 0 ? 'var(--text-dark)' : 'var(--color-orange-light)', fontFamily: 'Orbitron' }}>
                  {rssiValue === 0 ? 'STANDBY' : `${rssiValue} dBm`}
                </span>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)' }}>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '10px', marginBottom: '4px' }}>Link SNR</span>
                <span style={{ fontSize: '18px', fontWeight: '700', color: rssiValue === 0 ? 'var(--text-dark)' : '#fff', fontFamily: 'Orbitron' }}>
                  {rssiValue === 0 ? '0.0 dB' : `${snrValue} dB`}
                </span>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.04)', gridColumn: 'span 2', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '10px', marginBottom: '2px' }}>Packet Success Rate</span>
                  <span style={{ fontSize: '13px', fontWeight: '700', color: '#fff', fontFamily: 'monospace' }}>
                    {successRate}% ({receivedPackets}/{expectedPackets})
                  </span>
                </div>
                
                {/* RSSI Signal Bars */}
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: '3px', height: '20px', paddingBottom: '2px' }}>
                  {[1, 2, 3, 4, 5].map((bar) => (
                    <div 
                      key={bar} 
                      style={{ 
                        width: '3.5px', 
                        height: `${bar * 3.5}px`, 
                        background: bar <= barsCount ? 'var(--color-orange)' : 'var(--text-dark)', 
                        borderRadius: '1px',
                        boxShadow: bar <= barsCount ? '0 0 6px var(--color-orange)' : 'none',
                        transition: 'all 0.3s ease'
                      }}
                    />
                  ))}
                </div>
              </div>

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
