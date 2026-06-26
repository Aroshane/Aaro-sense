"""
AeroSense — ArduPilot Mission Generator
Generates a multi-altitude lawnmower grid survey .waypoints file
for Mission Planner / QGroundControl.

Usage:
  python3 aerosense_mission.py

Output:
  aerosense_mission.waypoints  ← load into Mission Planner
"""

import math
from dataclasses import dataclass
from typing import List

# ═════════════════════════════════════════════════════════════════════════════
# MISSION PARAMETERS — edit these for your site
# ═════════════════════════════════════════════════════════════════════════════

# Survey area centre (Kollam, Kerala — example)
ORIGIN_LAT  =  8.8932
ORIGIN_LON  = 76.6141

# Survey grid size (metres)
GRID_WIDTH  = 200.0   # East-West extent
GRID_HEIGHT = 200.0   # North-South extent

# Lane spacing (metres) — affects sample density
LANE_SPACING = 15.0

# Altitudes to survey (one complete grid per altitude)
ALTITUDES   = [15.0, 30.0, 50.0]   # metres AGL

# Flight speed (m/s) — slower = more samples per metre
SPEED_MS    = 2.0

# Loiter time at each waypoint (seconds) — 0 for continuous flight
LOITER_S    = 0

# Takeoff and RTL altitudes
TAKEOFF_ALT = 10.0
RTL_ALT     = 20.0

# ═════════════════════════════════════════════════════════════════════════════
# COORDINATE MATH
# ═════════════════════════════════════════════════════════════════════════════

EARTH_R = 6_371_000.0  # metres

def offset_latlon(lat: float, lon: float,
                  north_m: float, east_m: float):
    """Offset a lat/lon by north_m and east_m metres."""
    d_lat = north_m / EARTH_R
    d_lon = east_m  / (EARTH_R * math.cos(math.radians(lat)))
    return lat + math.degrees(d_lat), lon + math.degrees(d_lon)


@dataclass
class Waypoint:
    seq:   int
    lat:   float
    lon:   float
    alt:   float
    cmd:   int   = 16    # MAV_CMD_NAV_WAYPOINT
    param1: float = 0.0  # loiter time
    param2: float = 2.0  # acceptance radius (m)
    param3: float = 0.0  # pass-through radius
    param4: float = 0.0  # yaw (0=auto)
    frame: int   = 3     # MAV_FRAME_GLOBAL_RELATIVE_ALT

    def to_line(self) -> str:
        # QGC WPL 110 format:
        # index current coordframe command param1 param2 param3 param4 lat lon alt autocontinue
        return (f"{self.seq}\t0\t{self.frame}\t{self.cmd}\t"
                f"{self.param1:.2f}\t{self.param2:.2f}\t"
                f"{self.param3:.2f}\t{self.param4:.2f}\t"
                f"{self.lat:.7f}\t{self.lon:.7f}\t{self.alt:.2f}\t1")


def generate_grid(origin_lat: float, origin_lon: float,
                  width: float, height: float,
                  lane_spacing: float, altitude: float,
                  start_seq: int,
                  direction: str = "EW") -> List[Waypoint]:
    """
    Generate a lawnmower (boustrophedon) grid of waypoints.
    direction: "EW" (east-west lanes) or "NS" (north-south lanes)
    """
    wps = []
    seq = start_seq

    # Start from bottom-left corner
    corner_lat, corner_lon = offset_latlon(
        origin_lat, origin_lon, -height/2, -width/2)

    if direction == "EW":
        n_lanes = int(height / lane_spacing) + 1
        for i in range(n_lanes):
            north = i * lane_spacing
            row_lat, row_lon = offset_latlon(corner_lat, corner_lon, north, 0)

            if i % 2 == 0:
                # West to East
                start_lon = row_lon
                end_lat, end_lon = offset_latlon(row_lat, row_lon, 0, width)
            else:
                # East to West
                start_lat, start_lon = offset_latlon(row_lat, row_lon, 0, width)
                end_lat, end_lon = row_lat, row_lon
                row_lat, row_lon = start_lat, start_lon

            wps.append(Waypoint(
                seq=seq, lat=row_lat, lon=row_lon, alt=altitude,
                param1=LOITER_S,
            ))
            seq += 1
            wps.append(Waypoint(
                seq=seq, lat=end_lat, lon=end_lon, alt=altitude,
                param1=LOITER_S,
            ))
            seq += 1

    else:  # NS
        n_lanes = int(width / lane_spacing) + 1
        for i in range(n_lanes):
            east = i * lane_spacing
            col_lat, col_lon = offset_latlon(corner_lat, corner_lon, 0, east)

            if i % 2 == 0:
                start = (col_lat, col_lon)
                end   = offset_latlon(col_lat, col_lon, height, 0)
            else:
                start = offset_latlon(col_lat, col_lon, height, 0)
                end   = (col_lat, col_lon)

            wps.append(Waypoint(seq=seq, lat=start[0], lon=start[1],
                                 alt=altitude, param1=LOITER_S))
            seq += 1
            wps.append(Waypoint(seq=seq, lat=end[0],   lon=end[1],
                                 alt=altitude, param1=LOITER_S))
            seq += 1

    return wps


def generate_mission(output_path: str = "aerosense_mission.waypoints"):
    all_wps: List[Waypoint] = []

    # ── 0: Home (auto-set by GCS, seq 0 is always home) ─────────────────────
    home = Waypoint(seq=0, lat=ORIGIN_LAT, lon=ORIGIN_LON,
                    alt=0, cmd=16, frame=0)
    all_wps.append(home)

    seq = 1

    # ── 1: Takeoff ────────────────────────────────────────────────────────────
    takeoff = Waypoint(seq=seq, lat=ORIGIN_LAT, lon=ORIGIN_LON,
                        alt=TAKEOFF_ALT, cmd=22, frame=3)  # MAV_CMD_NAV_TAKEOFF
    all_wps.append(takeoff)
    seq += 1

    # ── 2: Set airspeed for all legs ──────────────────────────────────────────
    spd_wp = Waypoint(seq=seq, lat=0, lon=0, alt=0,
                       cmd=178, frame=0,   # MAV_CMD_DO_CHANGE_SPEED
                       param1=0, param2=SPEED_MS, param3=-1, param4=0)
    all_wps.append(spd_wp)
    seq += 1

    # ── 3: Grid survey at each altitude ───────────────────────────────────────
    for i, alt in enumerate(ALTITUDES):
        # Transit to grid start at this altitude
        # Alternate EW/NS direction each altitude for better 3D coverage
        direction = "EW" if i % 2 == 0 else "NS"

        grid_wps = generate_grid(
            ORIGIN_LAT, ORIGIN_LON,
            GRID_WIDTH, GRID_HEIGHT,
            LANE_SPACING, alt, seq, direction
        )
        all_wps.extend(grid_wps)
        seq += len(grid_wps)

    # ── 4: Return to Launch ───────────────────────────────────────────────────
    rtl = Waypoint(seq=seq, lat=ORIGIN_LAT, lon=ORIGIN_LON,
                    alt=RTL_ALT, cmd=20, frame=3)  # MAV_CMD_NAV_RETURN_TO_LAUNCH
    all_wps.append(rtl)

    # ── Write .waypoints file ─────────────────────────────────────────────────
    with open(output_path, "w") as f:
        f.write("QGC WPL 110\n")
        for wp in all_wps:
            f.write(wp.to_line() + "\n")

    # ── Mission summary ───────────────────────────────────────────────────────
    grid_wps_only = [w for w in all_wps if w.cmd == 16]
    total_pts = len(grid_wps_only)

    # Rough distance estimate
    dist_per_alt = 0
    prev = None
    for wp in grid_wps_only[:len(grid_wps_only)//len(ALTITUDES)]:
        if prev:
            dlat = math.radians(wp.lat - prev.lat)
            dlon = math.radians(wp.lon - prev.lon)
            a = (math.sin(dlat/2)**2 +
                 math.cos(math.radians(prev.lat)) *
                 math.cos(math.radians(wp.lat)) *
                 math.sin(dlon/2)**2)
            dist_per_alt += 2 * EARTH_R * math.asin(math.sqrt(a))
        prev = wp

    total_dist = dist_per_alt * len(ALTITUDES)
    flight_time = total_dist / SPEED_MS / 60

    print(f"\n{'='*52}")
    print(f"  AeroSense Mission Summary")
    print(f"{'='*52}")
    print(f"  Grid         : {GRID_WIDTH:.0f} m x {GRID_HEIGHT:.0f} m")
    print(f"  Lane spacing : {LANE_SPACING:.0f} m")
    print(f"  Altitudes    : {ALTITUDES} m AGL")
    print(f"  Total wpts   : {len(all_wps)} ({total_pts} survey points)")
    print(f"  Est. distance: {total_dist/1000:.2f} km")
    print(f"  Est. flight  : {flight_time:.1f} min @ {SPEED_MS} m/s")
    print(f"  Output file  : {output_path}")
    print(f"{'='*52}\n")
    print("Load into Mission Planner:")
    print("  File -> Load WP File -> select aerosense_mission.waypoints")
    print("  Review in map view, then Upload to drone.\n")


if __name__ == "__main__":
    generate_mission("aerosense_mission.waypoints")
