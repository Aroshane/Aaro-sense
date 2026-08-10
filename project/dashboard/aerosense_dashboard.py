"""
AeroSense 3D Pollution Map Dashboard — aerosense_dashboard.py
Plotly Dash web app — reads from SQLite logged by payload firmware.

Install:
  pip3 install dash plotly pandas scipy numpy

Run:
  python3 aerosense_dashboard.py
  Open: http://localhost:8050
"""

import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

import dash
from dash import dcc, html, Input, Output, callback
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.interpolate import griddata

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH      = "/data/aerosense/aerosense.db"
# Fallback for local simulation databases on Windows
if not Path(DB_PATH).exists() and Path("data/aerosense.db").exists():
    DB_PATH = "data/aerosense.db"
REFRESH_MS   = 3000   # live refresh every 3 seconds
MAP_BOX_TOKEN = ""    # optional: set for satellite basemap

AQI_SCALE = [
    [0.00, "#10b981"],      # Good (Emerald Green)
    [0.20, "#fbbf24"],      # Moderate (Amber/Yellow)
    [0.45, "#f97316"],      # Unhealthy (Orange)
    [0.65, "#f43f5e"],      # Very Unhealthy (Rose Red)
    [1.00, "#d946ef"],      # Hazardous (Fuchsia)
]

# ═════════════════════════════════════════════════════════════════════════════
# ML PREDICTION UTILITIES & DATA LAYER
# ═════════════════════════════════════════════════════════════════════════════

import os
import pickle

_cached_model = None
_cached_mtime = None

def get_predictor_model(model_path: str = "data/aerosense_model.pkl"):
    global _cached_model, _cached_mtime
    if not os.path.exists(model_path):
        return None
    try:
        mtime = os.path.getmtime(model_path)
        if _cached_model is None or _cached_mtime != mtime:
            with open(model_path, "rb") as f:
                _cached_model = pickle.load(f)
            _cached_mtime = mtime
    except Exception:
        pass
    return _cached_model

def extract_current_profile(db_path: str, max_age_seconds: int = 600) -> dict | None:
    """
    Queries SQLite database for the latest readings and builds a vertical profile 
    (PM2.5, Temperature, Pressure, Humidity) at 15m, 30m, and 50m.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=0.5)
        df = pd.read_sql_query("""
            SELECT timestamp, alt_m, pm25, temperature, humidity, pressure
            FROM pollution_points
            WHERE gps_quality > 0
              AND pm25 >= 0
              AND quality_flag & 1 = 0
            ORDER BY timestamp DESC
            LIMIT 200
        """, conn)
        conn.close()
    except Exception:
        return None

    if df.empty:
        return None

    # Try live data first (within last max_age_seconds)
    latest_ts = df["timestamp"].max()
    live_df = df[df["timestamp"] >= latest_ts - max_age_seconds]
    
    # Fallback to last available records if live window doesn't have all bands
    working_df = live_df if not live_df.empty else df

    bands = [15.0, 30.0, 50.0]
    tolerance = 5.0
    profile = {}

    for b in bands:
        band_df = working_df[np.abs(working_df["alt_m"] - b) <= tolerance]
        if band_df.empty:
            # Try matching against the entire dataframe as a last-resort fallback
            band_df = df[np.abs(df["alt_m"] - b) <= tolerance]
            if band_df.empty:
                return None
        # Use the latest reading in this band
        latest = band_df.iloc[0]
        b_int = int(b)
        profile[f"pm25_{b_int}"] = float(latest["pm25"])
        profile[f"temp_{b_int}"] = float(latest["temperature"])
        profile[f"pressure_{b_int}"] = float(latest["pressure"])
        profile[f"humidity_{b_int}"] = float(latest["humidity"])

    profile["temp_gradient_15_50"] = profile["temp_50"] - profile["temp_15"]
    profile["pressure_gradient_15_50"] = profile["pressure_50"] - profile["pressure_15"]
    profile["hour_of_day"] = datetime.fromtimestamp(latest_ts, tz=timezone.utc).hour

    return profile

def predict_single(model, scaler, profile: dict) -> float:
    """Predict future ground PM2.5 from a single vertical profile dict."""
    FEATURE_COLUMNS = [
        "pm25_15", "pm25_30", "pm25_50",
        "temp_15", "temp_30", "temp_50",
        "pressure_15", "pressure_30", "pressure_50",
        "humidity_15", "humidity_30", "humidity_50",
        "temp_gradient_15_50",
        "pressure_gradient_15_50",
        "hour_of_day",
    ]
    X = pd.DataFrame([profile])[FEATURE_COLUMNS]
    X_s = scaler.transform(X)
    return float(model.predict(X_s)[0])

def calculate_ozone_risk_pandas(temp_series, mq135_series):
    """Vectorized calculation of Heat-Ozone Risk Index (HORI) from 0 to 100."""
    temp_factor = np.clip((temp_series - 25.0) / (38.0 - 25.0), 0.0, 1.0)
    gas_factor = np.clip((mq135_series - 0.15) / (2.5 - 0.15), 0.0, 1.0)
    return temp_factor * gas_factor * 100.0

def get_ozone_risk_category(score):
    """Get the qualitative risk category and associated color."""
    if score <= 25.0:
        return "Low", "#10b981"      # Emerald Green
    elif score <= 50.0:
        return "Moderate", "#fbbf24" # Amber/Yellow
    elif score <= 75.0:
        return "High", "#f97316"     # Orange
    else:
        return "Extreme", "#f43f5e"  # Rose Red

def load_data(db_path: str, limit: int = 5000) -> pd.DataFrame:
    """Load latest N records from SQLite into a DataFrame."""
    try:
        conn = sqlite3.connect(db_path, timeout=0.5)
        df = pd.read_sql_query(f"""
            SELECT timestamp, lat, lon, alt_m,
                   pm25, pm10, temperature, humidity,
                   pressure, voc, mq135_raw, quality_flag
            FROM pollution_points
            WHERE gps_quality > 0
              AND pm25 >= 0
              AND quality_flag & 1 = 0
            ORDER BY timestamp DESC
            LIMIT {limit}
        """, conn)
        conn.close()
        if df.empty:
            return _demo_data()
        df["dt"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df = df.iloc[::-1].reset_index(drop=True)  # chronological
        df["ozone_risk"] = calculate_ozone_risk_pandas(df["temperature"], df["mq135_raw"])
        return df
    except Exception:
        # Return empty demo data if no DB yet
        return _demo_data()


def _demo_data() -> pd.DataFrame:
    """Generate synthetic flight data for UI preview."""
    np.random.seed(42)
    n = 300
    lats = 8.8932 + np.cumsum(np.random.randn(n) * 0.00003)
    lons = 76.6141 + np.cumsum(np.random.randn(n) * 0.00003)
    alts = np.abs(np.sin(np.linspace(0, 4*np.pi, n))) * 50 + 10
    pm25 = 15 + 30 * np.abs(np.sin(np.linspace(0, 8*np.pi, n))) + \
           np.random.randn(n) * 3
    ts   = np.linspace(1700000000, 1700003600, n)
    
    # Simulating a hot summer day with high precursor gases (heatwave + pollution)
    temps = 28.0 + 8.0 * np.sin(np.linspace(-0.5*np.pi, 1.5*np.pi, n)) + np.random.randn(n) * 1.5
    mq_raw = 0.4 + 1.2 * (pm25 / 40.0) + np.random.randn(n) * 0.1
    mq_raw = np.clip(mq_raw, 0.1, 3.0)
    
    df = pd.DataFrame({
        "timestamp": ts, "lat": lats, "lon": lons, "alt_m": alts,
        "pm25": pm25, "pm10": pm25 * 1.4,
        "temperature": temps,
        "humidity":    65 + np.random.randn(n) * 2,
        "pressure":    1010 + np.random.randn(n) * 0.3,
        "voc":         40000 + np.random.randn(n) * 5000,
        "mq135_raw":   mq_raw,
        "quality_flag": np.zeros(n, dtype=int),
        "dt": pd.to_datetime(ts, unit="s", utc=True),
    })
    df["ozone_risk"] = calculate_ozone_risk_pandas(df["temperature"], df["mq135_raw"])
    return df

# ═════════════════════════════════════════════════════════════════════════════
# FIGURE BUILDERS
# ═════════════════════════════════════════════════════════════════════════════

def build_3d_scatter(df: pd.DataFrame, metric: str = "pm25",
                     alt_min: float = 0, alt_max: float = 200) -> go.Figure:
    """3D scatter plot: lon/lat/alt coloured by pollution metric."""
    mask = (df["alt_m"] >= alt_min) & (df["alt_m"] <= alt_max)
    sub  = df[mask]

    if sub.empty:
        sub = df

    values = sub[metric]
    if metric == "ozone_risk":
        vmin, vmax = 0.0, 100.0
    else:
        vmin, vmax = values.quantile(0.02), values.quantile(0.98)

    fig = go.Figure()

    # Flight path line
    fig.add_trace(go.Scatter3d(
        x=sub["lon"], y=sub["lat"], z=sub["alt_m"],
        mode="lines",
        line=dict(color="rgba(150,150,150,0.3)", width=2),
        name="Flight path",
        hoverinfo="skip",
    ))

    # Pollution points
    fig.add_trace(go.Scatter3d(
        x=sub["lon"],
        y=sub["lat"],
        z=sub["alt_m"],
        mode="markers",
        marker=dict(
            size=4,
            color=values,
            colorscale=AQI_SCALE,
            cmin=vmin, cmax=vmax,
            colorbar=dict(
                title=dict(text=metric.upper(), side="right"),
                thickness=14,
                len=0.7,
            ),
            opacity=0.85,
        ),
        text=[
            f"PM2.5: {row.pm25:.1f} µg/m³<br>"
            f"PM10:  {row.pm10:.1f} µg/m³<br>"
            f"Temp:  {row.temperature:.1f}°C<br>"
            f"Ozone Risk: {row.ozone_risk:.1f}/100<br>"
            f"Alt:   {row.alt_m:.1f} m<br>"
            f"Time:  {row.dt.strftime('%H:%M:%S')}"
            for row in sub.itertuples()
        ],
        hoverinfo="text",
        name=metric,
    ))

    fig.update_layout(
        scene=dict(
            xaxis_title="Longitude",
            yaxis_title="Latitude",
            zaxis_title="Altitude (m)",
            bgcolor="rgba(0,0,0,0)",
            xaxis=dict(backgroundcolor="rgba(0,0,0,0)", gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.06)"),
            yaxis=dict(backgroundcolor="rgba(0,0,0,0)", gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.06)"),
            zaxis=dict(backgroundcolor="rgba(0,0,0,0)", gridcolor="rgba(255,255,255,0.06)", zerolinecolor="rgba(255,255,255,0.06)"),
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9ca3af"),
        legend=dict(x=0, y=1),
        title=dict(
            text=f"3D Pollution Map — {metric.upper()} | "
                 f"{len(sub)} points | Alt {alt_min:.0f}–{alt_max:.0f} m",
            font=dict(size=13, color="#e5e7eb"),
        ),
    )
    return fig


def build_timeseries(df: pd.DataFrame) -> go.Figure:
    """Multi-panel time series: PM2.5/PM10, temp/humidity, Ozone Risk, altitude."""
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        subplot_titles=("PM2.5 & PM10 (µg/m³)",
                         "Temperature (°C) & Humidity (%)",
                         "Heat-Ozone Risk Index (HORI)",
                         "Altitude (m)"),
        vertical_spacing=0.06,
    )

    fig.add_trace(go.Scatter(x=df["dt"], y=df["pm25"],
                              name="PM2.5", line=dict(color="#a78bfa", width=2)),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=df["dt"], y=df["pm10"],
                              name="PM10",  line=dict(color="#f43f5e", width=2)),
                  row=1, col=1)

    # WHO PM2.5 threshold line
    fig.add_hline(y=15, line_dash="dash", line_color="#ef4444",
                  annotation_text="WHO limit 15 µg/m³", row=1, col=1)

    fig.add_trace(go.Scatter(x=df["dt"], y=df["temperature"],
                              name="Temp °C", line=dict(color="#3b82f6", width=2)),
                  row=2, col=1)
    fig.add_trace(go.Scatter(x=df["dt"], y=df["humidity"],
                              name="Humidity %",
                              line=dict(color="#06b6d4", width=2, dash="dot")),
                  row=2, col=1)

    fig.add_trace(go.Scatter(x=df["dt"], y=df["ozone_risk"],
                              name="Ozone Risk (HORI)", line=dict(color="#f97316", width=2)),
                  row=3, col=1)

    fig.add_trace(go.Scatter(x=df["dt"], y=df["alt_m"],
                              name="Altitude m",
                              fill="tozeroy",
                              fillcolor="rgba(16, 185, 129, 0.08)",
                              line=dict(color="#10b981", width=2)),
                  row=4, col=1)

    fig.update_layout(
        height=520, margin=dict(l=50, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9ca3af"),
        legend=dict(orientation="h", y=1.02),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def build_altitude_slice(df: pd.DataFrame, alt_target: float,
                          band: float = 5.0) -> go.Figure:
    """2D heatmap of PM2.5 at a specific altitude slice."""
    mask = (df["alt_m"] >= alt_target - band) & \
           (df["alt_m"] <= alt_target + band)
    sub  = df[mask]

    if len(sub) < 4:
        fig = go.Figure()
        fig.add_annotation(
            text=f"🛸 No Flight Data at {alt_target:.0f}m Elevation<br>"
                 f"<span style='color: #6b7280; font-size: 12px;'>"
                 f"Adjust the Altitude Slice slider below to view registered points."
                 f"</span>",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color="#e5e7eb"),
            align="center"
        )
        fig.update_layout(
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, visible=False),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, visible=False),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9ca3af"),
            margin=dict(l=10, r=10, t=50, b=10),
            title=dict(
                text=f"PM2.5 Heatmap at {alt_target:.0f}m ± {band:.0f}m",
                font=dict(size=13, color="#9ca3af")
            )
        )
        return fig

    # Interpolate scattered points onto a grid
    lon_grid = np.linspace(sub["lon"].min(), sub["lon"].max(), 60)
    lat_grid = np.linspace(sub["lat"].min(), sub["lat"].max(), 60)
    lon_mg, lat_mg = np.meshgrid(lon_grid, lat_grid)

    try:
        pm25_grid = griddata(
            (sub["lon"], sub["lat"]), sub["pm25"],
            (lon_mg, lat_mg), method="cubic"
        )
    except Exception:
        pm25_grid = griddata(
            (sub["lon"], sub["lat"]), sub["pm25"],
            (lon_mg, lat_mg), method="nearest"
        )

    fig = go.Figure(go.Heatmap(
        x=lon_grid, y=lat_grid, z=pm25_grid,
        colorscale=AQI_SCALE,
        colorbar=dict(title="PM2.5 µg/m³"),
        zsmooth="best",
    ))

    # Overlay actual sample points
    fig.add_trace(go.Scatter(
        x=sub["lon"], y=sub["lat"],
        mode="markers",
        marker=dict(size=4, color="white", opacity=0.5),
        name="Samples", hoverinfo="skip",
    ))

    fig.update_layout(
        title=dict(
            text=f"PM2.5 Heatmap at {alt_target:.0f} m altitude",
            font=dict(color="#e5e7eb")
        ),
        xaxis_title="Longitude", yaxis_title="Latitude",
        margin=dict(l=50, r=20, t=50, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#9ca3af"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def compute_stats(df: pd.DataFrame) -> dict:
    """Flight summary statistics."""
    if df.empty:
        return {}
    duration = (df["timestamp"].max() - df["timestamp"].min()) / 60
    return {
        "points":    len(df),
        "duration":  f"{duration:.1f} min",
        "alt_range": f"{df['alt_m'].min():.0f}–{df['alt_m'].max():.0f} m",
        "pm25_mean": f"{df['pm25'].mean():.1f} µg/m³",
        "pm25_max":  f"{df['pm25'].max():.1f} µg/m³",
        "temp_mean": f"{df['temperature'].mean():.1f} °C",
        "hum_mean":  f"{df['humidity'].mean():.1f} %",
    }

# ═════════════════════════════════════════════════════════════════════════════
# DATA LOG LOADER FOR CONSOLE
# ═════════════════════════════════════════════════════════════════════════════

def load_latest_logs(db_path: str, limit: int = 10) -> list:
    import time
    try:
        conn = sqlite3.connect(db_path, timeout=0.5)
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT timestamp, lat, lon, alt_m, pm25, pm10, quality_flag
            FROM pollution_points
            ORDER BY timestamp DESC
            LIMIT {limit}
        """)
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            raise Exception("No logs available")
        return rows
    except Exception:
        # Return mock logs if DB fails or does not exist
        t = time.time()
        return [
            (t - i, 8.8932 + i*0.00001, 76.6141 - i*0.00001, 10.0 + i*0.5, 20.0 + i*2.0, 28.0 + i*2.5, 0)
            for i in range(limit)
        ]

# ═════════════════════════════════════════════════════════════════════════════
# MULTI-PAGE LAYOUTS
# ═════════════════════════════════════════════════════════════════════════════

def get_overview_layout():
    return html.Div(children=[
        # Title
        html.H2("System Overview & Live Telemetry", style={"margin": "0 0 20px 0", "fontSize": "20px", "fontWeight": "600"}),
        
        # Grid layout for Diagnostics + Survey Profile + ML Predictor + Ozone Risk (4 columns)
        html.Div(style={"display": "grid", "gridTemplateColumns": "1.1fr 0.9fr 1.0fr 1.0fr", "gap": "20px", "marginBottom": "24px"}, children=[
            # Diagnostics Card
            html.Div(className="glass-card card-purple", children=[
                html.H3("System Diagnostics & Status", style={"margin": "0 0 16px 0", "fontSize": "15px", "color": "#e5e7eb"}),
                html.Div(style={"display": "flex", "flexDirection": "column", "gap": "14px"}, children=[
                    html.Div(className="health-indicator", children=[
                        html.Div(className="health-dot online"),
                        html.Span("Autopilot Connection: Pixhawk (UART-Sim)")
                    ]),
                    html.Div(className="health-indicator", children=[
                        html.Div(className="health-dot online"),
                        html.Span("RF Telemetry Link: SX1276 LoRa (433MHz-Sim)")
                    ]),
                    html.Div(className="health-indicator", children=[
                        html.Div(className="health-dot online"),
                        html.Span("Air Quality Sensors: PMS5003 PM2.5/PM10 (Simulated)")
                    ]),
                    html.Div(className="health-indicator", children=[
                        html.Div(className="health-dot online"),
                        html.Span("Meteorological Sensor: BME280 Temperature/RH (Simulated)")
                    ]),
                ]),
            ]),

            # Survey Card
            html.Div(className="glass-card card-blue", children=[
                html.H3("Active Survey Mission", style={"margin": "0 0 16px 0", "fontSize": "15px", "color": "#e5e7eb"}),
                html.Div(style={"display": "flex", "flexDirection": "column", "gap": "10px", "fontSize": "13px", "color": "#9ca3af"}, children=[
                    html.Div(style={"display": "flex", "justifyContent": "space-between", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
                        html.Span("Survey Area:"), html.Span("200m x 200m Grid Survey", style={"color": "#fff", "fontWeight": "500"}),
                    ]),
                    html.Div(style={"display": "flex", "justifyContent": "space-between", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
                        html.Span("Flight Speeds:"), html.Span("2.0 m/s Cruise speed", style={"color": "#fff", "fontWeight": "500"}),
                    ]),
                    html.Div(style={"display": "flex", "justifyContent": "space-between", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
                        html.Span("Altitudes AGL:"), html.Span("15m, 30m, 50m Layers", style={"color": "#fff", "fontWeight": "500"}),
                    ]),
                    html.Div(style={"display": "flex", "justifyContent": "space-between", "paddingBottom": "4px"}, children=[
                        html.Span("Waypoint File:"), html.Span("aerosense_mission.waypoints", style={"color": "#fff", "fontWeight": "500"}),
                    ]),
                ]),
            ]),

            # Live PM2.5 Forecast Card
            html.Div(className="glass-card card-green", children=[
                html.H3("Live Ground PM2.5 Forecast (+15m)", style={"margin": "0 0 16px 0", "fontSize": "15px", "color": "#e5e7eb"}),
                html.Div(id="prediction-display", style={"display": "flex", "flexDirection": "column", "gap": "10px", "fontSize": "13px", "color": "#9ca3af"})
            ]),

            # Heat-Ozone Cardiac Risk Card
            html.Div(className="glass-card card-orange", children=[
                html.H3("Heat-Ozone Cardiac Risk (HORI)", style={"margin": "0 0 16px 0", "fontSize": "15px", "color": "#e5e7eb"}),
                html.Div(id="ozone-risk-display", style={"display": "flex", "flexDirection": "column", "gap": "10px", "fontSize": "13px", "color": "#9ca3af"})
            ]),
        ]),

        # Logger Terminal Output
        html.Div(className="glass-card card-pink", children=[
            html.H3("Live Drone Payload Console Output", style={"margin": "0 0 16px 0", "fontSize": "15px", "color": "#e5e7eb"}),
            html.Div(id="live-log-console", className="log-container"),
        ]),
    ])

def get_3d_mapping_layout():
    return html.Div(children=[
        html.H2("3D Volumetric Mapping Control Room", style={"margin": "0 0 20px 0", "fontSize": "20px", "fontWeight": "600"}),
        
        # Controls Row
        html.Div(className="glass-card card-purple", style={"marginBottom": "16px"}, children=[
            html.Div(style={"display": "flex", "gap": "24px", "flexWrap": "wrap", "alignItems": "center"}, children=[
                html.Div(children=[
                    html.Label("Target Pollution Metric", style={"fontSize": "11px", "color": "#9ca3af", "display": "block", "marginBottom": "6px", "fontWeight": "500"}),
                    dcc.Dropdown(
                        id="metric-select",
                        options=[
                            {"label": "PM2.5 (µg/m³)", "value": "pm25"},
                            {"label": "PM10 (µg/m³)", "value": "pm10"},
                            {"label": "Temperature (°C)", "value": "temperature"},
                            {"label": "Humidity (%)", "value": "humidity"},
                            {"label": "VOC (N/A — not available with BME280)", "value": "voc", "disabled": True},
                            {"label": "MQ-135 Voltage", "value": "mq135_raw"},
                            {"label": "Heat-Ozone Risk Index", "value": "ozone_risk"},
                        ],
                        value="pm25", clearable=False,
                        className="dash-dropdown",
                        style={"width": "200px"},
                    ),
                ]),

                html.Div(children=[
                    html.Label("Altitude Bounds Filter (m)", style={"fontSize": "11px", "color": "#9ca3af", "display": "block", "marginBottom": "6px", "fontWeight": "500"}),
                    dcc.RangeSlider(
                        id="alt-slider", min=0, max=150, step=5,
                        value=[0, 150], marks={0: "0", 50: "50", 100: "100", 150: "150"},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ),
                ], style={"flex": "1", "minWidth": "220px"}),
            ]),
        ]),

        # 3D Graph
        html.Div(className="glass-card card-blue", children=[
            dcc.Graph(id="scatter3d", style={"height": "500px"}, config={"displayModeBar": False}),
        ]),
    ])

def get_2d_slice_layout():
    return html.Div(children=[
        html.H2("Interpolated 2D Spatial Heatmaps", style={"margin": "0 0 20px 0", "fontSize": "20px", "fontWeight": "600"}),
        
        # Controls Row
        html.Div(className="glass-card card-purple", style={"marginBottom": "16px"}, children=[
            html.Div(style={"display": "flex", "gap": "24px", "flexWrap": "wrap", "alignItems": "center"}, children=[
                html.Div(children=[
                    html.Label("Target Elevation Slice Layer (m)", style={"fontSize": "11px", "color": "#9ca3af", "display": "block", "marginBottom": "6px", "fontWeight": "500"}),
                    dcc.Slider(
                        id="slice-alt", min=0, max=150, step=5, value=10,
                        marks={0: "0m", 50: "50m", 100: "100m", 150: "150m"},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ),
                ], style={"flex": "1"}),
            ]),
        ]),

        # Heatmap Graph
        html.Div(className="glass-card card-green", children=[
            dcc.Graph(id="heatmap2d", style={"height": "500px"}, config={"displayModeBar": False}),
        ]),
    ])

def get_analytics_layout():
    return html.Div(children=[
        html.H2("Multi-Parameter Trend Analytics", style={"margin": "0 0 20px 0", "fontSize": "20px", "fontWeight": "600"}),
        
        # Timeseries Graph
        html.Div(className="glass-card card-pink", children=[
            dcc.Graph(id="timeseries", style={"height": "500px"}, config={"displayModeBar": False}),
        ]),
    ])

# ═════════════════════════════════════════════════════════════════════════════
# DASH APP INSTANCE & ROOT LAYOUT
# ═════════════════════════════════════════════════════════════════════════════

app = dash.Dash(__name__, title="AeroSense — Pollution Mapper", suppress_callback_exceptions=True)

app.layout = html.Div(style={
    "position": "relative",
    "minHeight": "100vh",
    "fontFamily": "system-ui, -apple-system, sans-serif",
    "color": "#f3f4f6",
    "padding": "24px",
    "backgroundColor": "#080a16",
    "overflowX": "hidden",
}, children=[
    # Curtain loader overlay (curtain raising splash screen on first boot)
    html.Div(className="curtain-loader", children=[
        html.Div(className="curtain-panel"),
        html.Div(className="curtain-content", children=[
            html.Div("🛸", className="curtain-logo"),
            html.H1("AeroSense", className="curtain-title"),
            html.P("Quadcopter 3D Spatial Pollution Mapping System", className="curtain-subtitle"),
            html.Div(className="preloader-counter"),
            html.Div(className="preloader-progress-track", children=[
                html.Div(className="preloader-progress-bar")
            ])
        ])
    ]),


    # Custom CSS styles are loaded automatically by Dash from the assets/styles.css file
    dcc.Location(id="url", refresh=False),

    # Background elements
    html.Div(className="bg-grid"),
    html.Div(className="bg-spotlight"),
    html.Div(className="glow-orb-1"),
    html.Div(className="glow-orb-2"),

    # Content wrapper to sit above background z-index
    html.Div(style={"position": "relative", "zIndex": 10}, children=[
        # ── Header Navbar ────────────────────────────────────────────────────────
        html.Div(style={"display":"flex","alignItems":"center","gap":"20px",
                        "marginBottom":"24px"}, children=[
            html.Div("🛸", style={"fontSize":"36px"}),
            html.Div(children=[
                html.H1("AeroSense",
                        style={"margin":0,"fontSize":"26px","fontWeight":"700","letterSpacing":"-0.5px"}),
                html.P("Quadcopter 3D Pollution Mapper — Live Dashboard",
                       style={"margin":0,"fontSize":"13px","color":"#9ca3af"}),
            ]),
            html.Div(style={"marginLeft":"auto","display":"flex","gap":"12px"}, children=[
                html.Div(id="stat-points", className="stat-badge stat-purple"),
                html.Div(id="stat-duration", className="stat-badge stat-blue"),
                html.Div(id="stat-pm25", className="stat-badge stat-green"),
            ]),
        ]),

        dcc.Interval(id="refresh", interval=REFRESH_MS, n_intervals=0),

        # ── Router Navigation Tabs ────────────────────────────────────────────────
        html.Div(className="navbar-container", children=[
            dcc.Link("Overview", href="/", id="link-overview", className="nav-link"),
            dcc.Link("3D Volumetric Mapping", href="/3d-mapping", id="link-3d", className="nav-link"),
            dcc.Link("2D Spatial Slices", href="/2d-slice", id="link-slice", className="nav-link"),
            dcc.Link("Analytics & Trends", href="/analytics", id="link-analytics", className="nav-link"),
        ]),

        # ── Live Telemetry Ticker Marquee ─────────────────────────────────────────
        html.Div(id="live-telemetry-marquee", className="marquee-container"),

        # ── Page Content Container ────────────────────────────────────────────────
        html.Div(id="page-content"),

        # ── Footer ────────────────────────────────────────────────────────────────
        html.Div(id="last-update",
                 style={"textAlign":"right","fontSize":"11px",
                        "color":"#4b5563","marginTop":"20px"}),
    ])
])

# ═════════════════════════════════════════════════════════════════════════════
# ROUTING & TELEMETRY CALLBACKS
# ═════════════════════════════════════════════════════════════════════════════

@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def render_page(pathname):
    if pathname == "/3d-mapping":
        return get_3d_mapping_layout()
    elif pathname == "/2d-slice":
        return get_2d_slice_layout()
    elif pathname == "/analytics":
        return get_analytics_layout()
    else:
        return get_overview_layout()

@app.callback(
    Output("link-overview", "className"),
    Output("link-3d", "className"),
    Output("link-slice", "className"),
    Output("link-analytics", "className"),
    Input("url", "pathname")
)
def toggle_active_links(pathname):
    if pathname == "/3d-mapping":
        return "nav-link", "nav-link nav-link-active", "nav-link", "nav-link"
    elif pathname == "/2d-slice":
        return "nav-link", "nav-link", "nav-link nav-link-active", "nav-link"
    elif pathname == "/analytics":
        return "nav-link", "nav-link", "nav-link", "nav-link nav-link-active"
    else:
        return "nav-link nav-link-active", "nav-link", "nav-link", "nav-link"

@app.callback(
    Output("live-telemetry-marquee", "children"),
    Input("refresh", "n_intervals")
)
def update_marquee(n):
    df = load_data(DB_PATH)
    
    # Live summary calculations
    if not df.empty:
        points = len(df)
        pm25_mean = df["pm25"].mean()
        alt_min = df["alt_m"].min()
        alt_max = df["alt_m"].max()
        latest = df.iloc[-1]
        temp = float(latest["temperature"])
        mq135 = float(latest["mq135_raw"])
        score = calculate_ozone_risk_pandas(pd.Series([temp]), pd.Series([mq135])).iloc[0]
        category, _ = get_ozone_risk_category(score)
        flags = int(latest["quality_flag"])
    else:
        points = 0
        pm25_mean = 0.0
        alt_min = 0.0
        alt_max = 0.0
        score = 0.0
        category = "Low"
        flags = 0

    items = []
    
    # System Status
    items.append(html.Div(className="marquee-item", children=[
        html.Div(className="marquee-dot marquee-success-dot"),
        html.Span("AEROSENSE SYSTEM STATUS:", className="marquee-label"),
        html.Span("ONLINE / LIVE LOGGING", className="marquee-value marquee-success")
    ]))
    
    # Air Quality warning
    if pm25_mean > 35.0:
        items.append(html.Div(className="marquee-item", children=[
            html.Div(className="marquee-dot marquee-warning-dot"),
            html.Span("AIR QUALITY ALERT:", className="marquee-label"),
            html.Span(f"ELEVATED PM2.5 ({pm25_mean:.1f} µg/m³)", className="marquee-value marquee-warning")
        ]))
    else:
        items.append(html.Div(className="marquee-item", children=[
            html.Div(className="marquee-dot marquee-success-dot"),
            html.Span("AIR QUALITY:", className="marquee-label"),
            html.Span(f"NORMAL ({pm25_mean:.1f} µg/m³)", className="marquee-value marquee-success")
        ]))
        
    # Ozone / HORI Risk
    if category in ["High", "Extreme"]:
        items.append(html.Div(className="marquee-item", children=[
            html.Div(className="marquee-dot marquee-warning-dot"),
            html.Span("OZONE CARDIAC RISK:", className="marquee-label"),
            html.Span(f"{category.upper()} (HORI: {score:.1f})", className="marquee-value marquee-warning")
        ]))
    else:
        items.append(html.Div(className="marquee-item", children=[
            html.Div(className="marquee-dot marquee-info-dot"),
            html.Span("OZONE CARDIAC RISK:", className="marquee-label"),
            html.Span(f"LOW ({score:.1f})", className="marquee-value marquee-info")
        ]))

    # Survey altitude
    items.append(html.Div(className="marquee-item", children=[
        html.Div(className="marquee-dot marquee-info-dot"),
        html.Span("FLIGHT PROFILE AGL:", className="marquee-label"),
        html.Span(f"BOUNDS {alt_min:.0f}m - {alt_max:.0f}m", className="marquee-value")
    ]))
    
    # Avoidance Module status
    items.append(html.Div(className="marquee-item", children=[
        html.Div(className="marquee-dot marquee-success-dot"),
        html.Span("OBSTACLE AVOIDANCE:", className="marquee-label"),
        html.Span("ACTIVE (VL53L1X + HC-SR04)", className="marquee-value marquee-success")
    ]))

    # Diagnostic quality flags
    if flags > 0:
        items.append(html.Div(className="marquee-item", children=[
            html.Div(className="marquee-dot marquee-warning-dot"),
            html.Span("PAYLOAD TELEMETRY WARNING:", className="marquee-label"),
            html.Span(f"QUALITY CODE 0x{flags:02X}", className="marquee-value marquee-warning")
        ]))
    else:
        items.append(html.Div(className="marquee-item", children=[
            html.Div(className="marquee-dot marquee-success-dot"),
            html.Span("PAYLOAD DIAGNOSTICS:", className="marquee-label"),
            html.Span("ALL SENSORS NORMAL", className="marquee-value marquee-success")
        ]))

    # Duplicate items list for infinite scrolling wrap
    return html.Div(className="marquee-content", children=items + items)

@app.callback(
    Output("stat-points",  "children"),
    Output("stat-duration","children"),
    Output("stat-pm25",    "children"),
    Output("last-update",  "children"),
    Input("refresh",       "n_intervals")
)
def update_navbar_stats(n):
    df = load_data(DB_PATH)
    stats = compute_stats(df)
    stat_points_layout = [
        html.Div("TOTAL SAMPLES", style={"fontSize": "10px", "color": "#9ca3af", "letterSpacing": "0.7px", "fontWeight": "600"}),
        html.Div(f"{stats.get('points','—')}", style={"fontSize": "18px", "fontWeight": "700", "color": "#a78bfa", "marginTop": "4px"}),
    ]
    stat_duration_layout = [
        html.Div("FLIGHT DURATION", style={"fontSize": "10px", "color": "#9ca3af", "letterSpacing": "0.7px", "fontWeight": "600"}),
        html.Div(f"{stats.get('duration','—')}", style={"fontSize": "18px", "fontWeight": "700", "color": "#60a5fa", "marginTop": "4px"}),
    ]
    stat_pm25_layout = [
        html.Div("AVG PM2.5 LEVEL", style={"fontSize": "10px", "color": "#9ca3af", "letterSpacing": "0.7px", "fontWeight": "600"}),
        html.Div(f"{stats.get('pm25_mean','—')}", style={"fontSize": "18px", "fontWeight": "700", "color": "#34d399", "marginTop": "4px"}),
    ]
    now = datetime.now(tz=timezone.utc).strftime("Updated %H:%M:%S UTC")
    return stat_points_layout, stat_duration_layout, stat_pm25_layout, now

@app.callback(
    Output("live-log-console", "children"),
    Input("refresh", "n_intervals")
)
def update_overview_console(n):
    logs = load_latest_logs(DB_PATH, 10)
    log_elements = []
    for row in logs:
        ts, lat, lon, alt, pm25, pm10, flag = row
        time_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")
        log_elements.append(html.Div(className="log-item", children=[
            html.Span(f"[{time_str}]", className="log-time"),
            html.Span("PAYLOAD: ", className="log-level-info"),
            html.Span(f"lat={lat:.5f} lon={lon:.5f} alt={alt:.1f}m | PM2.5={pm25:.1f} PM10={pm10:.1f} ug/m3 | Q_flag=0x{flag:02X}")
        ]))
    return log_elements

@app.callback(
    Output("scatter3d", "figure"),
    Input("refresh", "n_intervals"),
    Input("metric-select", "value"),
    Input("alt-slider", "value")
)
def update_3d_scatter(n, metric, alt_range):
    df = load_data(DB_PATH)
    return build_3d_scatter(df, metric, alt_range[0], alt_range[1])

@app.callback(
    Output("heatmap2d", "figure"),
    Input("refresh", "n_intervals"),
    Input("slice-alt", "value")
)
def update_heatmap2d(n, slice_alt):
    df = load_data(DB_PATH)
    return build_altitude_slice(df, slice_alt)

@app.callback(
    Output("timeseries", "figure"),
    Input("refresh", "n_intervals")
)
def update_timeseries(n):
    df = load_data(DB_PATH)
    return build_timeseries(df)

@app.callback(
    Output("prediction-display", "children"),
    Input("refresh", "n_intervals")
)
def update_live_prediction(n):
    # 1. Load trained model & scaler from pickle
    model_data = get_predictor_model("data/aerosense_model.pkl")
    if not model_data:
        return html.Div("⚠️ Prediction model not trained. Run 'python ai_prediction/aerosense_predict.py --sim' to train.", 
                        style={"color": "#fbbf24", "fontSize": "13px"})

    # 2. Extract profile from SQLite
    profile = extract_current_profile(DB_PATH)
    if not profile:
        return html.Div("⏳ Waiting for complete flight profile (15m, 30m, 50m readings)...", 
                        style={"color": "#9ca3af", "fontSize": "13px"})

    # 3. Perform prediction
    pred_val = predict_single(model_data["model"], model_data["scaler"], profile)
    ground_now = profile["pm25_15"]
    diff = pred_val - ground_now

    # 4. Format trend UI indicators
    if diff > 1.5:
        trend_text = f"Descent: +{diff:.1f} ug/m3"
        trend_color = "#f43f5e" # Rose Red
    elif diff < -1.5:
        trend_text = f"Dispersion: -{abs(diff):.1f} ug/m3"
        trend_color = "#10b981" # Emerald Green
    else:
        trend_text = "Stable Mix"
        trend_color = "#9ca3af"

    return html.Div(children=[
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
            html.Span("Ground PM2.5 NOW (15m):"),
            html.Span(f"{ground_now:.1f} ug/m3", style={"color": "#fff", "fontWeight": "600"}),
        ]),
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
            html.Span("Predicted PM2.5 (+15m):"),
            html.Span(f"{pred_val:.1f} ug/m3", style={"color": "#34d399", "fontWeight": "700"}),
        ]),
        html.Div(style={"display": "flex", "justifyContent": "space-between", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
            html.Span("Trend Indicator:"),
            html.Span(trend_text, style={"color": trend_color, "fontWeight": "600"}),
        ]),
        html.Div(style={"display": "flex", "justifyContent": "space-between", "paddingBottom": "2px"}, children=[
            html.Span("Atmospheric Gradient:"),
            html.Span(f"{profile['temp_gradient_15_50']:+.1f}°C", style={"color": "#fff", "fontWeight": "500"}),
        ]),
    ])

@app.callback(
    Output("ozone-risk-display", "children"),
    Input("refresh", "n_intervals")
)
def update_ozone_risk_display(n):
    df = load_data(DB_PATH)
    if df.empty:
        return html.Div("⏳ Waiting for data...", style={"color": "#9ca3af"})
    
    # Get the latest reading
    latest = df.iloc[-1]
    temp = float(latest["temperature"])
    mq135 = float(latest["mq135_raw"])
    
    # Calculate score
    score = calculate_ozone_risk_pandas(pd.Series([temp]), pd.Series([mq135])).iloc[0]
    category, color = get_ozone_risk_category(score)
    
    # Check alert message
    alert_msg = "Safe outdoor conditions."
    if category == "Moderate":
        alert_msg = "Monitor if you have respiratory issues."
    elif category == "High":
        alert_msg = "Caution: Heat & precursors are elevated."
    elif category == "Extreme":
        alert_msg = "Critical: Extreme cardiac/respiratory threat!"
        
    return html.Div(children=[
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
            html.Span("Latest Temperature:"),
            html.Span(f"{temp:.1f} °C", style={"color": "#fff", "fontWeight": "600"}),
        ]),
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
            html.Span("Precursor Gas (MQ-135):"),
            html.Span(f"{mq135:.2f} V", style={"color": "#fff", "fontWeight": "600"}),
        ]),
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
            html.Span("HORI Score:"),
            html.Span(f"{score:.1f} / 100", style={"color": color, "fontWeight": "700"}),
        ]),
        html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "borderBottom": "1px solid rgba(255,255,255,0.03)", "paddingBottom": "6px"}, children=[
            html.Span("Risk Category:"),
            html.Span(category, style={"color": color, "fontWeight": "700"}),
        ]),
        html.Div(style={"fontSize": "11px", "color": color, "fontWeight": "500", "marginTop": "4px", "lineHeight": "1.3"}, children=[
            alert_msg
        ])
    ])

# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n[INFO] AeroSense Dashboard starting...")
    print("   Open: http://localhost:8050\n")
    app.run(debug=False, host="0.0.0.0", port=8050, threaded=True)
