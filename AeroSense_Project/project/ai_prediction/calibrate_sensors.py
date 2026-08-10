#!/usr/bin/env python3
"""
AeroSense — Sensor Calibration Utility (calibrate_sensors.py)
============================================================
Compares drone payload sensor logs (SQLite database) with reference
Continuous Ambient Air Quality Monitoring (CAAQM) station data
downloaded from the CPCB portal to compute calibration offsets.

Outputs PM2.5, PM10, Temperature, and Humidity calibration values
and writes them directly to project/firmware/config.json.
"""

import os
import sys
import json
import sqlite3
import argparse
import numpy as np
import pandas as pd
from datetime import datetime

# Standard CPCB CSV headers mapping to standard parameter names
CPCB_COL_MAP = {
    'PM2.5 (µg/m³)': 'pm25',
    'PM10 (µg/m³)': 'pm10',
    'AT (°C)': 'temp',
    'RH (%)': 'hum'
}

def load_drone_data(db_path):
    """Load collocated drone telemetry data from SQLite."""
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        sys.exit(1)
        
    print(f"Loading drone telemetry from: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        # Select all valid data points (excluding erroneous status frames)
        query = """
            SELECT timestamp, pm25, pm10, temperature as temp, humidity as hum
            FROM pollution_points
            WHERE gps_quality > 0 
              AND pm25 >= 0 
              AND temp > -50
              AND (quality_flag & 1 = 0)
            ORDER BY timestamp
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            print("Warning: No valid drone telemetry points found in database.")
            return None
            
        # Convert unix epoch to naive local datetime (assuming IST/local)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
        # Convert to local India time and remove timezone awareness for easier pandas matching
        df['datetime_local'] = df['datetime'].dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
        
        print(f"Loaded {len(df)} drone telemetry entries.")
        print(f"Drone Time Range: {df['datetime_local'].min()} to {df['datetime_local'].max()}")
        return df
    except Exception as e:
        print(f"Error reading database: {e}")
        sys.exit(1)

def load_cpcb_data(cpcb_path):
    """Load reference air quality station data from CPCB CSV."""
    if not os.path.exists(cpcb_path):
        print(f"Error: CPCB reference file not found at {cpcb_path}")
        sys.exit(1)
        
    print(f"Loading CPCB reference logs from: {cpcb_path}")
    try:
        # Load CSV, skip metadata headers if any
        # CPCB files sometimes contain metadata headers. Let's find where the table starts.
        with open(cpcb_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [f.readline() for _ in range(20)]
            
        header_idx = 0
        for idx, line in enumerate(lines):
            if "Timestamp" in line or "From Date" in line:
                header_idx = idx
                break
                
        df = pd.read_csv(cpcb_path, skiprows=header_idx)
        
        # Identify Timestamp column
        ts_col = None
        for col in df.columns:
            if "timestamp" in col.lower() or "date" in col.lower():
                ts_col = col
                break
                
        if not ts_col:
            print("Error: Could not identify Date/Timestamp column in CPCB file.")
            sys.exit(1)
            
        # Standardize timestamp naming
        df = df.rename(columns={ts_col: 'Timestamp'})
        df['datetime_local'] = pd.to_datetime(df['Timestamp']).dt.tz_localize(None)
        
        # Clean numeric parameters
        for ext_col, std_name in CPCB_COL_MAP.items():
            if ext_col in df.columns:
                df[std_name] = pd.to_numeric(df[ext_col], errors='coerce')
            else:
                # Try finding without unit
                simple_col = ext_col.split(' ')[0]
                matched = False
                for c in df.columns:
                    if c.startswith(simple_col):
                        df[std_name] = pd.to_numeric(df[c], errors='coerce')
                        matched = True
                        break
                if not matched:
                    df[std_name] = np.nan
                    
        # Keep only required columns
        df = df[['datetime_local', 'pm25', 'pm10', 'temp', 'hum']].dropna(subset=['datetime_local'])
        print(f"Loaded {len(df)} reference entries from CPCB CSV.")
        print(f"CPCB Time Range: {df['datetime_local'].min()} to {df['datetime_local'].max()}")
        return df
    except Exception as e:
        print(f"Error reading CPCB CSV: {e}")
        sys.exit(1)

def align_and_calibrate(drone_df, cpcb_df, shift_years=None):
    """Align drone high-frequency telemetry with CPCB 15-minute average entries."""
    # 1. Resample/group drone data into 15-minute intervals to match CPCB sampling rate
    drone_df['datetime_15m'] = drone_df['datetime_local'].dt.round('15min')
    drone_15m = drone_df.groupby('datetime_15m').agg({
        'pm25': 'mean',
        'pm10': 'mean',
        'temp': 'mean',
        'hum': 'mean'
    }).reset_index()
    
    # 2. Check for direct overlap
    merged = pd.merge(drone_15m, cpcb_df, left_on='datetime_15m', right_on='datetime_local', suffixes=('_drone', '_cpcb'))
    
    # 3. Handle year shift if no direct overlap (e.g. drone is 2026, CPCB is 2025)
    if merged.empty or len(merged) < 2:
        print("\n[!] No overlapping timestamps found. Checking calendar date similarity...")
        drone_min = drone_df['datetime_local'].min()
        cpcb_min = cpcb_df['datetime_local'].min()
        
        if shift_years is None:
            shift_years = drone_min.year - cpcb_min.year
            
        if shift_years != 0:
            print(f"[!] Shifting CPCB timestamps by {shift_years} year(s) to match drone flight timeline.")
            cpcb_df_shifted = cpcb_df.copy()
            cpcb_df_shifted['datetime_local'] = cpcb_df_shifted['datetime_local'] + pd.DateOffset(years=shift_years)
            merged = pd.merge(drone_15m, cpcb_df_shifted, left_on='datetime_15m', right_on='datetime_local', suffixes=('_drone', '_cpcb'))
            
    if merged.empty or len(merged) < 2:
        print("\nError: Unable to align datasets. Please verify that the drone flight days and CPCB logs cover matching calendar dates.")
        print(f"Drone dates: {drone_df['datetime_local'].min().strftime('%Y-%m-%d')} to {drone_df['datetime_local'].max().strftime('%Y-%m-%d')}")
        print(f"CPCB dates: {cpcb_df['datetime_local'].min().strftime('%Y-%m-%d')} to {cpcb_df['datetime_local'].max().strftime('%Y-%m-%d')}")
        sys.exit(1)
        
    print(f"\nSuccessfully aligned {len(merged)} collocated 15-minute data windows.")
    
    # 4. Perform offset calculations
    report = {}
    offsets = {}
    
    parameters = ['pm25', 'pm10', 'temp', 'hum']
    param_labels = {
        'pm25': 'PM2.5 (µg/m³)',
        'pm10': 'PM10 (µg/m³)',
        'temp': 'Temperature (°C)',
        'hum': 'Relative Humidity (%)'
    }
    
    print("\n" + "="*70)
    print(" SENSOR CALIBRATION SUMMARY (COLOCATION VS CPCB REFERENCE)")
    print("="*70)
    
    for param in parameters:
        p_drone = f"{param}_drone"
        p_cpcb = f"{param}_cpcb"
        
        # Filter valid pairs
        clean_df = merged[[p_drone, p_cpcb]].dropna()
        # Filter out negative or extreme placeholder values (e.g. CPCB missing values like 999 or -999)
        clean_df = clean_df[(clean_df[p_drone] >= 0) & (clean_df[p_cpcb] >= 0) & (clean_df[p_cpcb] < 800)]
        
        if len(clean_df) < 2:
            print(f" {param_labels[param]:<22} : Insufficient valid comparison points.")
            continue
            
        drone_vals = clean_df[p_drone].values
        ref_vals = clean_df[p_cpcb].values
        
        # Calculate stats
        mean_drone = np.mean(drone_vals)
        mean_ref = np.mean(ref_vals)
        
        # Additive offset: Offset = Reference - Sensor
        offset = mean_ref - mean_drone
        offsets[param] = round(float(offset), 2)
        
        # Calculate errors
        mae_before = np.mean(np.abs(ref_vals - drone_vals))
        mae_after = np.mean(np.abs(ref_vals - (drone_vals + offset)))
        
        # Correlation
        corr = np.corrcoef(drone_vals, ref_vals)[0, 1]
        r2 = corr ** 2 if not np.isnan(corr) else 0.0
        
        # Linear Fit (Y_ref = m * X_drone + c)
        slope, intercept = np.polyfit(drone_vals, ref_vals, 1)
        
        print(f"\nParameter: {param_labels[param]}")
        print(f"  Collocation Samples : {len(clean_df)}")
        print(f"  Drone Mean          : {mean_drone:.2f}")
        print(f"  CPCB Reference Mean : {mean_ref:.2f}")
        print(f"  Calculated Offset   : {offset:+.2f}")
        print(f"  MAE (Raw Sensor)    : {mae_before:.2f}")
        print(f"  MAE (Calibrated)    : {mae_after:.2f}  (Improvement: {((mae_before - mae_after)/mae_before * 100) if mae_before > 0 else 0:.1f}%)")
        print(f"  Correlation (r)     : {corr:.3f} (R² = {r2:.3f})")
        print(f"  Linear Regression   : Y = {slope:.3f} * X + {intercept:+.3f}")
        
        report[param] = {
            'offset': offset,
            'mae_raw': mae_before,
            'mae_cal': mae_after,
            'r': corr,
            'slope': slope,
            'intercept': intercept
        }
        
    print("="*70)
    return offsets, report

def update_config(config_path, offsets):
    """Write the computed offsets back to config.json."""
    if not os.path.exists(config_path):
        print(f"Error: Config file not found at {config_path}")
        return False
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        if 'calibration' not in config:
            config['calibration'] = {}
            
        # Update offsets inside config
        if 'pm25' in offsets:
            config['calibration']['pm25_offset'] = offsets['pm25']
        if 'pm10' in offsets:
            config['calibration']['pm10_offset'] = offsets['pm10']
        if 'temp' in offsets:
            config['calibration']['temp_offset'] = offsets['temp']
        if 'hum' in offsets:
            config['calibration']['humidity_offset'] = offsets['hum']
            
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
            
        print(f"\n[OK] Calibration offsets successfully written to {config_path}:")
        print(json.dumps(config['calibration'], indent=4))
        return True
    except Exception as e:
        print(f"Error updating config.json: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="AeroSense CPCB sensor calibration utility")
    parser.add_argument("--cpcb", type=str, required=True,
                        help="Path to CPCB reference CSV file")
    parser.add_argument("--db", type=str, default="project/data/aerosense.db",
                        help="Path to drone SQLite database")
    parser.add_argument("--config", type=str, default="project/firmware/config.json",
                        help="Path to config.json file to update")
    parser.add_argument("--shift", type=int, default=None,
                        help="Force timestamp shift by N years")
    parser.add_argument("--write", action="store_true",
                        help="Automatically write calibration offsets to config.json without asking")
    args = parser.parse_args()

    # Load data
    drone_df = load_drone_data(args.db)
    if drone_df is None:
        print("Error: Drone database is empty or does not contain valid telemetry.")
        sys.exit(1)
        
    cpcb_df = load_cpcb_data(args.cpcb)
    
    # Run calibration
    offsets, report = align_and_calibrate(drone_df, cpcb_df, shift_years=args.shift)
    
    # Write calibration to config
    if args.write:
        update_config(args.config, offsets)
    else:
        # Prompt user if running in interactive shell
        try:
            val = input("\nWould you like to write these calculated offsets to config.json? (y/n): ")
            if val.strip().lower() in ['y', 'yes']:
                update_config(args.config, offsets)
            else:
                print("Skipped writing to config.json.")
        except (KeyboardInterrupt, EOFError):
            print("\nSkipped writing to config.json.")

if __name__ == "__main__":
    main()
