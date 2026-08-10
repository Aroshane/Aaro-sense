"""
AeroSense Ground Control Station API Server — aerosense_api.py
Exposes database telemetry, configuration controls, waypoint mission planning,
and vertical profile forecasting models over a REST API.

Run:
  python3 ground_station/aerosense_api.py
  Open: http://localhost:5001/api/status
"""

import os
import sys
import sqlite3
import json
import pickle
import math
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Add parent path or sibling path for imports if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

app = Flask(__name__, static_folder='../ground_control_app/dist', static_url_path='/')
CORS(app)  # Enable Cross-Origin Resource Sharing for React GCS App on Port 5173

# Configuration Paths
DB_PATH = "data/aerosense.db"
CONFIG_PATH = "firmware/config.json"
MODEL_PATH = "data/aerosense_model.pkl"
WAYPOINTS_PATH = "aerosense_mission.waypoints"

# Feature List for AI Forecast
FEATURE_COLUMNS = [
    "pm25_15", "pm25_30", "pm25_50",
    "temp_15", "temp_30", "temp_50",
    "pressure_15", "pressure_30", "pressure_50",
    "humidity_15", "humidity_30", "humidity_50",
    "temp_gradient_15_50",
    "pressure_gradient_15_50",
    "hour_of_day",
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── API ENDPOINTS ─────────────────────────────────────────────────────────────

@app.route("/api/status", methods=["GET"])
def get_status():
    """Verify that the API server and database are reachable."""
    db_ok = os.path.exists(DB_PATH)
    record_count = 0
    if db_ok:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pollution_points")
            record_count = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            db_ok = False
            
    return jsonify({
        "status": "online",
        "database_connected": db_ok,
        "total_records": record_count,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/api/telemetry", methods=["GET"])
def get_telemetry():
    """Return latest N records of flight telemetry for mapping and graphics."""
    limit = request.args.get("limit", default=200, type=int)
    if not os.path.exists(DB_PATH):
        return jsonify([])

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Query latest records
        cursor.execute(f"""
            SELECT * FROM pollution_points
            ORDER BY timestamp DESC
            LIMIT {limit}
        """)
        rows = cursor.fetchall()
        conn.close()

        # Parse into JSON array
        data = []
        for r in rows:
            data.append(dict(r))
        
        # Sort chronologically for charts
        data.reverse()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Compile summary metrics for current flight logging."""
    if not os.path.exists(DB_PATH):
        return jsonify({
            "points": 0, "duration": "0.0 min", "alt_range": "0-0 m",
            "pm25_mean": "0.0 µg/m³", "pm25_max": "0.0 µg/m³",
            "temp_mean": "0.0 °C", "hum_mean": "0.0 %"
        })

    try:
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM pollution_points WHERE gps_quality > 0", conn)
        conn.close()

        if df.empty:
            return jsonify({
                "points": 0, "duration": "0.0 min", "alt_range": "0-0 m",
                "pm25_mean": "0.0 µg/m³", "pm25_max": "0.0 µg/m³",
                "temp_mean": "0.0 °C", "hum_mean": "0.0 %"
            })

        duration_m = (df["timestamp"].max() - df["timestamp"].min()) / 60.0
        
        # Filter valid measurements
        valid_pm = df[df["pm25"] >= 0]
        valid_temp = df[df["temperature"] > -99.0]
        valid_hum = df[df["humidity"] >= 0]

        stats = {
            "points": len(df),
            "duration": f"{duration_m:.1f} min",
            "alt_range": f"{df['alt_m'].min():.0f}–{df['alt_m'].max():.0f} m",
            "pm25_mean": f"{valid_pm['pm25'].mean():.1f} µg/m³" if not valid_pm.empty else "0.0 µg/m³",
            "pm25_max": f"{valid_pm['pm25'].max():.1f} µg/m³" if not valid_pm.empty else "0.0 µg/m³",
            "temp_mean": f"{valid_temp['temperature'].mean():.1f} °C" if not valid_temp.empty else "0.0 °C",
            "hum_mean": f"{valid_hum['humidity'].mean():.1f} %" if not valid_hum.empty else "0.0 %"
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["GET", "POST"])
def manage_config():
    """Read or update config.json payload configurations."""
    if request.method == "GET":
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"error": "config.json not found"}), 404
        try:
            with open(CONFIG_PATH, "r") as f:
                config_data = json.load(f)
            return jsonify(config_data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    elif request.method == "POST":
        try:
            new_config = request.json
            if not new_config:
                return jsonify({"error": "No config data provided"}), 400
            
            # Format and save config.json
            with open(CONFIG_PATH, "w") as f:
                json.dump(new_config, f, indent=2)
            
            return jsonify({"success": True, "message": "Configuration saved successfully."})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/mission/waypoints", methods=["GET"])
def get_waypoints():
    """Parse and return current waypoints file entries for Leaflet map render."""
    if not os.path.exists(WAYPOINTS_PATH):
        # Fallback search in parent directory or mission folder
        alt_path = os.path.join("mission", WAYPOINTS_PATH)
        if os.path.exists(alt_path):
            WAYPOINTS_PATH_RESOLVED = alt_path
        else:
            return jsonify({"waypoints": [], "origin": [8.8932, 76.6141]})
    else:
        WAYPOINTS_PATH_RESOLVED = WAYPOINTS_PATH

    waypoints = []
    origin = [8.8932, 76.6141]

    try:
        with open(WAYPOINTS_PATH_RESOLVED, "r") as f:
            lines = f.readlines()
        
        # Check header
        if not lines or "QGC WPL" not in lines[0]:
            return jsonify({"error": "Invalid waypoints format"}), 400

        for line in lines[1:]:
            parts = line.strip().split("\t")
            if len(parts) < 11:
                continue
            
            seq = int(parts[0])
            frame = int(parts[2])
            cmd = int(parts[3])
            lat = float(parts[8])
            lon = float(parts[9])
            alt = float(parts[10])

            # Get origin from home waypoint (seq 0)
            if seq == 0:
                origin = [lat, lon]

            waypoints.append({
                "seq": seq,
                "frame": frame,
                "command": cmd,
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "param1": float(parts[4]),
                "param2": float(parts[5]),
                "param3": float(parts[6]),
                "param4": float(parts[7])
            })
        
        return jsonify({
            "waypoints": waypoints,
            "origin": origin
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mission/generate", methods=["POST"])
def generate_mission():
    """Trigger the mission planner script to generate a new waypoint grid."""
    try:
        params = request.json or {}
        
        # Pull parameters, fallback to defaults
        origin_lat = float(params.get("origin_lat", 8.8932))
        origin_lon = float(params.get("origin_lon", 76.6141))
        grid_width = float(params.get("grid_width", 200.0))
        grid_height = float(params.get("grid_height", 200.0))
        lane_spacing = float(params.get("lane_spacing", 15.0))
        altitudes = params.get("altitudes", [15.0, 30.0, 50.0])
        speed_ms = float(params.get("speed_ms", 2.0))

        # Import and trigger generator from mission module
        import mission.aerosense_mission as gcs_mission
        
        # Override configuration variables dynamically
        gcs_mission.ORIGIN_LAT = origin_lat
        gcs_mission.ORIGIN_LON = origin_lon
        gcs_mission.GRID_WIDTH = grid_width
        gcs_mission.GRID_HEIGHT = grid_height
        gcs_mission.LANE_SPACING = lane_spacing
        gcs_mission.ALTITUDES = altitudes
        gcs_mission.SPEED_MS = speed_ms
        
        # Generate to local workspace file
        output_file = "aerosense_mission.waypoints"
        gcs_mission.generate_mission(output_file)

        # Copy to mission folder for redundancy
        try:
            os.makedirs("mission", exist_ok=True)
            with open(output_file, "r") as src, open(os.path.join("mission", output_file), "w") as dst:
                dst.write(src.read())
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"Successfully generated mission waypoints for a {grid_width}x{grid_height}m grid."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prediction/predict", methods=["POST", "GET"])
def predict_pollution():
    """Run pollution forecasting from current atmospheric profiles or custom inputs."""
    # 1. Load model pickle
    if not os.path.exists(MODEL_PATH):
        return jsonify({"error": "Predictor model file (aerosense_model.pkl) not found. Run training script first."}), 404
    
    try:
        with open(MODEL_PATH, "rb") as f:
            model_data = pickle.load(f)
        
        model = model_data["model"]
        scaler = model_data["scaler"]
        mae = model_data.get("mae", 0.0)
        cv_mae = model_data.get("cv_mae", 0.0)
        
        # Get importances if available
        importances = {}
        if "importances" in model_data:
            # Series to dict
            importances = model_data["importances"].to_dict()
    except Exception as e:
        return jsonify({"error": f"Failed to load model: {str(e)}"}), 500

    # 2. Extract profile (from request or fallback to database)
    profile = None
    source = "custom"
    
    if request.method == "POST":
        profile = request.json
        
    if not profile:
        # Fallback to query database for latest profile
        source = "live_database"
        profile = extract_profile_from_db()

    if not profile:
        # Fallback: mock standard early morning inversion profile
        source = "mock_inversion"
        profile = {
            "pm25_15": 22.0, "pm25_30": 45.0, "pm25_50": 70.0,
            "temp_15": 27.5, "temp_30": 29.0, "temp_50": 30.5,
            "pressure_15": 1011.0, "pressure_30": 1010.2, "pressure_50": 1009.5,
            "humidity_15": 70, "humidity_30": 67, "humidity_50": 64,
            "temp_gradient_15_50": 3.0,
            "pressure_gradient_15_50": -1.5,
            "hour_of_day": 7,
        }

    try:
        # Predict ground future PM2.5
        X = pd.DataFrame([profile])[FEATURE_COLUMNS]
        X_s = scaler.transform(X)
        prediction = float(model.predict(X_s)[0])
        
        return jsonify({
            "success": True,
            "source": source,
            "profile": profile,
            "prediction": prediction,
            "model_metadata": {
                "mae": mae,
                "cv_mae": cv_mae,
                "importances": importances
            }
        })
    except Exception as e:
        return jsonify({"error": f"Prediction evaluation failed: {str(e)}"}), 500


@app.route("/api/obstacle-avoidance", methods=["GET"])
def get_obstacle_avoidance():
    """Retrieve current obstacle distances and warnings."""
    # Since direct hardware reads are handled by main.py, we extract configuration
    # parameters and return mock telemetry signals if running in sim mode
    sim_mode = True
    safety_distance = 2.0

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            sim_mode = cfg.get("sim_mode", False)
            safety_distance = cfg.get("avoidance", {}).get("safety_distance_m", 2.0)
        except Exception:
            pass

    # Read latest database logs for flags
    warning_active = False
    front_distance = 4.0
    right_distance = 4.0
    
    if os.path.exists(DB_PATH):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT alt_m, quality_flag FROM pollution_points ORDER BY timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            # If avoiding, warning indicators might trigger
            if row and (row["quality_flag"] & 8):
                warning_active = True
        except Exception:
            pass

    # Synthesize live radar readings for visual feedback based on time
    import time
    t = time.time()
    
    # Simulates periodic obstacles moving closer
    if sim_mode:
        # Periodic oscillation between 0.8m and 4.0m
        front_distance = 2.4 + 1.6 * math.sin(t * 0.2)
        right_distance = 2.6 + 1.4 * math.cos(t * 0.3)
        # Random drop occasionally to simulate proximity danger
        if int(t) % 35 < 5:
            front_distance = 0.9 + 0.3 * math.sin(t * 2.0)
            
        warning_active = (front_distance < safety_distance) or (right_distance < safety_distance)

    return jsonify({
        "sim_mode": sim_mode,
        "safety_distance_m": safety_distance,
        "front_laser_m": front_distance,
        "right_ultrasonic_m": right_distance,
        "warning_active": warning_active,
        "timestamp": t
    })


def extract_profile_from_db():
    """Collect latest flight points and assign to 15m, 30m, and 50m vertical profile bands."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("""
            SELECT timestamp, alt_m, pm25, temperature, humidity, pressure
            FROM pollution_points
            WHERE gps_quality > 0 AND pm25 >= 0 AND quality_flag & 1 = 0
            ORDER BY timestamp DESC
            LIMIT 200
        """, conn)
        conn.close()
    except Exception:
        return None

    if df.empty:
        return None

    # Get latest timestamp
    latest_ts = df["timestamp"].max()
    bands = [15.0, 30.0, 50.0]
    tolerance = 5.0
    profile = {}

    for b in bands:
        band_df = df[np.abs(df["alt_m"] - b) <= tolerance]
        if band_df.empty:
            return None # Incomplete profile
        
        # Take latest reading in this altitude band
        latest_pt = band_df.iloc[0]
        b_int = int(b)
        profile[f"pm25_{b_int}"] = float(latest_pt["pm25"])
        profile[f"temp_{b_int}"] = float(latest_pt["temperature"])
        profile[f"pressure_{b_int}"] = float(latest_pt["pressure"])
        profile[f"humidity_{b_int}"] = float(latest_pt["humidity"])

    profile["temp_gradient_15_50"] = profile["temp_50"] - profile["temp_15"]
    profile["pressure_gradient_15_50"] = profile["pressure_50"] - profile["pressure_15"]
    profile["hour_of_day"] = datetime.fromtimestamp(latest_ts, tz=timezone.utc).hour

    return profile


# Serve React static assets in production build
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


if __name__ == "__main__":
    port = 5001
    print(f"Starting AeroSense GCS API Server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
