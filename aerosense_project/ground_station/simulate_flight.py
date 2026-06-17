"""
AeroSense Flight Simulator — simulate_flight.py
Simulates a quadcopter flying the pre-generated waypoint mission.
Generates realistic temperature, pressure, humidity, and PM2.5/PM10 readings
along the path and broadcasts them via UDP MessagePack to port 5005.
"""

import time
import socket
import math
import random
import msgpack
import os

# UDP Telemetry settings
UDP_IP = "127.0.0.1"
UDP_PORT = 5005

# Flight settings
SPEED_MPS = 5.0 # Flight speed in m/s
TICK_RATE_HZ = 2.0 # Broadcast telemetry 2 times a second
STEP_TIME = 1.0 / TICK_RATE_HZ

print("==========================================================")
print("  AeroSense Live Flight Simulator")
print("==========================================================")

# ── Load Waypoints ────────────────────────────────────────────────────────────
waypoints = []
waypoints_file = "aerosense_mission.waypoints"

if os.path.exists(waypoints_file):
    print(f"Loading waypoints from: {waypoints_file}")
    with open(waypoints_file) as f:
        lines = f.readlines()
    for line in lines[1:]: # Skip headers
        parts = line.strip().split("\t")
        if len(parts) >= 11:
            cmd = int(parts[3])
            lat = float(parts[8])
            lon = float(parts[9])
            alt = float(parts[10])
            # Only use standard navigation waypoints (command 16) and takeoff (22)
            if cmd in [16, 22]:
                waypoints.append((lat, lon, alt))
    print(f"Loaded {len(waypoints)} waypoints.")
else:
    print(f"Waypoints file {waypoints_file} not found. Generating default grid...")
    # Default fallback: 8.8932, 76.6141 origin
    lat_start, lon_start = 8.8932, 76.6141
    # Generate simple coordinates for a vertical flight grid
    for alt in [15.0, 30.0, 50.0]:
        for i in range(5):
            for j in range(5):
                lat = lat_start + (i * 0.0001)
                lon = lon_start + (j * 0.0001)
                waypoints.append((lat, lon, alt))
    print(f"Generated {len(waypoints)} default grid points.")

# ── Sensor Simulation Math ────────────────────────────────────────────────────
# Simulate an atmospheric inversion layer:
# PM2.5 is high aloft (at 50m) but lower at the ground (15m), and T is higher aloft.
# Morning inversion pattern.
def get_sensor_readings(lat, lon, alt, t_sec):
    # Base temperature drops with altitude normally, but inversion flips it!
    # Let's simulate a strong temperature inversion: T(50m) = T(15m) + 3.0C
    # Base temp at ground (15m) = 27C. Base temp at 50m = 30C.
    height_ratio = (alt - 15.0) / 35.0 if alt > 15.0 else 0.0
    temp = 27.5 + (height_ratio * 3.0) + (random.random() - 0.5) * 0.3
    
    # Humidity drops as temperature/altitude increases
    humidity = 72.0 - (height_ratio * 8.0) + (random.random() - 0.5) * 1.0
    
    # Barometric pressure drops with altitude
    pressure = 1011.0 - (alt * 0.12) + (random.random() - 0.5) * 0.1
    
    # Inversion layer traps PM2.5 aloft (higher PM2.5 at 50m, lower at 15m)
    pm25_base = 22.0 + (height_ratio * 45.0)
    # Add some spatial pollution pockets (e.g. localized hotspot near coordinates)
    dist_from_hotspot = math.sqrt((lat - 8.8935)**2 + (lon - 76.6145)**2)
    hotspot_influence = max(0.0, 30.0 * (1.0 - (dist_from_hotspot / 0.0005)))
    
    pm25 = max(0.0, pm25_base + hotspot_influence + (random.random() - 0.5) * 2.0)
    pm10 = pm25 * 1.35
    
    # MQ-135 voltage decreases with higher air quality, simulate basic voltage
    mq135_raw = 1.25 - (pm25 * 0.003) + (random.random() - 0.5) * 0.02
    
    return pm25, pm10, temp, humidity, pressure, mq135_raw

# ── Main Simulation Loop ──────────────────────────────────────────────────────
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
current_index = 0
curr_lat, curr_lon, curr_alt = waypoints[0]

# Speed calculation
# 1 deg lat = 111,000m. 1 deg lon = 111,000 * cos(lat)
lat_m_per_deg = 111000.0
lon_m_per_deg = 111000.0 * math.cos(math.radians(curr_lat))

print(f"Connecting to telemetry receiver at {UDP_IP}:{UDP_PORT}...")
print("Press Ctrl+C to terminate simulation.")

start_time = time.time()

try:
    while current_index < len(waypoints):
        target_lat, target_lon, target_alt = waypoints[current_index]
        
        # Calculate distances to target
        d_lat = (target_lat - curr_lat) * lat_m_per_deg
        d_lon = (target_lon - curr_lon) * lon_m_per_deg
        d_alt = target_alt - curr_alt
        
        distance = math.sqrt(d_lat**2 + d_lon**2 + d_alt**2)
        
        # Check if waypoint reached
        if distance < 1.5:
            print(f"\n[Simulator] Reached Waypoint #{current_index} of {len(waypoints) - 1}: Lat={target_lat:.5f}, Lon={target_lon:.5f}, Alt={target_alt:.1f}m")
            current_index += 1
            if current_index >= len(waypoints):
                print("[Simulator] Mission completed! Restarting from takeoff point...")
                current_index = 0
            continue
            
        # Move step towards target
        step_dist = SPEED_MPS * STEP_TIME
        if step_dist >= distance:
            curr_lat, curr_lon, curr_alt = target_lat, target_lon, target_alt
        else:
            curr_lat += (d_lat / distance) * step_dist / lat_m_per_deg
            curr_lon += (d_lon / distance) * step_dist / lon_m_per_deg
            curr_alt += (d_alt / distance) * step_dist
            
        # Simulate sensor inputs
        t_sec = time.time()
        pm25, pm10, temp, humidity, pressure, mq135_raw = get_sensor_readings(curr_lat, curr_lon, curr_alt, t_sec)
        
        # Format payload list (exactly matches firmware/main.py order)
        lst = [
            round(t_sec, 1),
            round(curr_lat, 6),
            round(curr_lon, 6),
            round(curr_alt, 1),
            3, # gps_quality (3 = 3D Fix)
            round(pm25, 2),
            round(pm10, 2),
            round(temp, 2),
            round(humidity, 2),
            round(pressure, 2),
            -1.0, # voc
            round(mq135_raw, 4),
            0  # quality_flag
        ]
        
        # Encode with message pack
        payload_bin = msgpack.packb(lst)
        
        # Send via UDP
        sock.sendto(payload_bin, (UDP_IP, UDP_PORT))
        
        # Print status updates on a single line
        print(f"\rFlight: Alt={curr_alt:4.1f}m | Lat={curr_lat:.5f} Lon={curr_lon:.5f} | PM2.5={pm25:4.1f} ug/m3 | Temp={temp:4.1f}C", end="", flush=True)
        
        time.sleep(STEP_TIME)

except KeyboardInterrupt:
    print("\n[Simulator] Flight simulation terminated by user.")
finally:
    sock.close()
