import React, { useState, useEffect, useRef } from 'react';
import { Play, Download, Map, Send, Layers } from 'lucide-react';

function MissionPlanner({ apiBase }) {
  const [waypoints, setWaypoints] = useState([]);
  const [origin, setOrigin] = useState([8.8932, 76.6141]);
  const [params, setParams] = useState({
    origin_lat: 8.8932,
    origin_lon: 76.6141,
    grid_width: 200.0,
    grid_height: 200.0,
    lane_spacing: 15.0,
    altitudes: '15,30,50',
    speed_ms: 2.0
  });
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);

  // Load waypoints from API
  const fetchWaypoints = async () => {
    try {
      const res = await fetch(`${apiBase}/mission/waypoints`);
      const data = await res.json();
      if (data.waypoints) {
        setWaypoints(data.waypoints);
        setOrigin(data.origin || [8.8932, 76.6141]);
        
        // Sync parameters with loaded origin if not manually edited
        setParams(prev => ({
          ...prev,
          origin_lat: data.origin ? data.origin[0] : prev.origin_lat,
          origin_lon: data.origin ? data.origin[1] : prev.origin_lon
        }));
      }
    } catch (err) {
      console.error('Failed to load waypoints', err);
    }
  };

  useEffect(() => {
    fetchWaypoints();
  }, []);

  // Handle Leaflet Map rendering in React
  useEffect(() => {
    // Wait until window.L (Leaflet) is loaded from CDN
    if (!window.L || !waypoints.length) return;

    // Remove old map instance if it exists
    if (mapInstanceRef.current) {
      mapInstanceRef.current.remove();
      mapInstanceRef.current = null;
    }

    const L = window.L;
    
    // Create new map instance
    const map = L.map(mapRef.current).setView([origin[0], origin[1]], 16);
    mapInstanceRef.current = map;

    // Dark styled map tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: 'OpenStreetMap contributors'
    }).addTo(map);

    // Group waypoints by altitude to display multiple paths with different colors
    const pathsByAlt = {};
    const colors = ['#8b5cf6', '#3b82f6', '#10b981', '#ea580c'];
    
    // Filter actual nav points
    const navWps = waypoints.filter(wp => wp.command === 16 || wp.command === 22 || wp.command === 20);

    // Draw waypoints and markers
    navWps.forEach((wp, idx) => {
      // Seq 0 is home, cmd 22 is takeoff, cmd 20 is land
      let iconColor = 'violet';
      let popupText = `Waypoint #${wp.seq}<br>Altitude: ${wp.alt}m`;

      if (wp.seq === 0) {
        iconColor = 'red';
        popupText = 'Home Position (Launch/RTL)';
      } else if (wp.command === 22) {
        iconColor = 'green';
        popupText = `Takeoff to ${wp.alt}m`;
      } else if (wp.command === 20) {
        iconColor = 'orange';
        popupText = `RTL (Return To Launch) at ${wp.alt}m`;
      }

      // Add circles for waypoints
      const circle = L.circle([wp.lat, wp.lon], {
        color: wp.seq === 0 ? '#ef4444' : colors[Math.floor(wp.alt / 20) % colors.length],
        fillColor: wp.seq === 0 ? '#ef4444' : colors[Math.floor(wp.alt / 20) % colors.length],
        fillOpacity: 0.4,
        radius: wp.seq === 0 ? 12 : 5
      }).addTo(map);
      circle.bindPopup(popupText);

      // Group for connecting line
      if (wp.seq > 0 && wp.command === 16) {
        if (!pathsByAlt[wp.alt]) pathsByAlt[wp.alt] = [];
        pathsByAlt[wp.alt].push([wp.lat, wp.lon]);
      }
    });

    // Draw polyline paths
    Object.keys(pathsByAlt).forEach((alt, i) => {
      const coords = pathsByAlt[alt];
      if (coords.length > 1) {
        L.polyline(coords, {
          color: colors[i % colors.length],
          weight: 3.5,
          opacity: 0.85,
          dashArray: '5, 8'
        }).addTo(map).bindPopup(`Survey Track at ${alt}m altitude`);
      }
    });

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [waypoints, origin]);

  // Form input changes
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setParams(prev => ({
      ...prev,
      [name]: value
    }));
  };

  // Generate new mission
  const handleGenerate = async (e) => {
    e.preventDefault();
    setIsGenerating(true);
    setStatusMsg('Running mission grid generator...');
    
    // Parse altitudes string "15,30,50" -> [15.0, 30.0, 50.0]
    const parsedAlts = params.altitudes
      .split(',')
      .map(s => parseFloat(s.trim()))
      .filter(n => !isNaN(n));

    try {
      const res = await fetch(`${apiBase}/mission/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          origin_lat: parseFloat(params.origin_lat),
          origin_lon: parseFloat(params.origin_lon),
          grid_width: parseFloat(params.grid_width),
          grid_height: parseFloat(params.grid_height),
          lane_spacing: parseFloat(params.lane_spacing),
          altitudes: parsedAlts,
          speed_ms: parseFloat(params.speed_ms)
        })
      });
      const data = await res.json();
      if (data.success) {
        setStatusMsg('Grid mission created successfully! Reloading...');
        await fetchWaypoints();
      } else {
        setStatusMsg(`Failed: ${data.error}`);
      }
    } catch (err) {
      setStatusMsg(`Connection Error: ${err.message}`);
    } finally {
      setIsGenerating(false);
      setTimeout(() => setStatusMsg(''), 4000);
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '20px' }}>
      
      {/* Waypoints Map Viewer */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div className="glass-card card-purple" style={{ flex: '1', display: 'flex', flexDirection: 'column' }}>
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Map size={16} /> Volumetric Waypoints Map Viewer
          </h3>
          
          <div 
            ref={mapRef} 
            style={{ width: '100%', height: '480px', borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            {waypoints.length === 0 && (
              <div style={{ display: 'flex', alignItems: 'center', justify: 'center', height: '100%', color: 'var(--text-muted)' }}>
                No Waypoint mission loaded. Submit parameters to generate a mission.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Grid Parameters Form */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div className="glass-card card-blue">
          <h3 style={{ fontSize: '15px', color: '#fff', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Send size={16} /> Mission Grid Parameters
          </h3>
          
          <form onSubmit={handleGenerate} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Origin Latitude</label>
              <input 
                type="number" step="0.0000001" className="gcs-input" 
                name="origin_lat" value={params.origin_lat} onChange={handleInputChange} 
              />
            </div>
            
            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Origin Longitude</label>
              <input 
                type="number" step="0.0000001" className="gcs-input" 
                name="origin_lon" value={params.origin_lon} onChange={handleInputChange} 
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Width (m)</label>
                <input 
                  type="number" step="1" className="gcs-input" 
                  name="grid_width" value={params.grid_width} onChange={handleInputChange} 
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Height (m)</label>
                <input 
                  type="number" step="1" className="gcs-input" 
                  name="grid_height" value={params.grid_height} onChange={handleInputChange} 
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Lane Spacing (m)</label>
                <input 
                  type="number" step="0.5" className="gcs-input" 
                  name="lane_spacing" value={params.lane_spacing} onChange={handleInputChange} 
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Flight Speed (m/s)</label>
                <input 
                  type="number" step="0.1" className="gcs-input" 
                  name="speed_ms" value={params.speed_ms} onChange={handleInputChange} 
                />
              </div>
            </div>

            <div>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Survey Altitudes AGL (m, comma-split)</label>
              <input 
                type="text" className="gcs-input" 
                name="altitudes" value={params.altitudes} onChange={handleInputChange} 
                placeholder="e.g. 15,30,50"
              />
            </div>

            <button type="submit" disabled={isGenerating} className="gcs-button" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginTop: '10px' }}>
              <Play size={14} /> {isGenerating ? 'Generating...' : 'Generate Waypoint Grid'}
            </button>

            {statusMsg && (
              <div style={{ fontSize: '12px', color: 'var(--color-cyan-light)', textAlign: 'center', marginTop: '4px', fontStyle: 'italic' }}>
                {statusMsg}
              </div>
            )}
          </form>
        </div>

        {/* Waypoints Sequence List */}
        <div className="glass-card card-green" style={{ maxHeight: '200px', overflowY: 'auto' }}>
          <h3 style={{ fontSize: '13px', color: '#fff', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={14} /> Waypoints Sequence ({waypoints.length} nodes)
          </h3>
          <div style={{ fontSize: '11px', fontFamily: 'monospace' }}>
            {waypoints.map((wp) => {
              let label = `WP #${wp.seq}`;
              if (wp.seq === 0) label = 'Home (Base)';
              else if (wp.command === 22) label = 'Takeoff';
              else if (wp.command === 20) label = 'RTL (Land)';
              
              return (
                <div key={wp.seq} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                  <span style={{ color: 'var(--color-purple-light)', fontWeight: '600' }}>{label}</span>
                  <span style={{ color: 'var(--text-muted)' }}>Alt: {wp.alt.toFixed(0)}m</span>
                  <span style={{ color: '#fff' }}>[{wp.lat.toFixed(5)}, {wp.lon.toFixed(5)}]</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

    </div>
  );
}

export default MissionPlanner;
