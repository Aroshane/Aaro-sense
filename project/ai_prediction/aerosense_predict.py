"""
AeroSense — Vertical Profile Predictor (aerosense_predict.py
)
=================================================================
Predicts future ground-level PM2.5 from a drone's vertical
atmospheric profile (PM2.5, temperature, pressure, humidity at
multiple altitude bands).

Concept:
  Temperature/pressure gradients between altitude bands act as a
  proxy for atmospheric stability (inversion vs. mixing). This
  pipeline learns the empirical relationship between "what the
  vertical profile looks like NOW" and "what ground PM2.5 will be
  LATER" — the same principle used in inversion forecasting,
  applied at hyperlocal scale via drone survey data.

Honest scope:
  - This is a PROOF-OF-CONCEPT pipeline, not a validated forecaster.
  - With few flights, results are directional, not predictive-grade.
  - Designed to run on real OR simulated flight logs (--sim mode
    generates synthetic multi-flight data with realistic inversion
    patterns so the pipeline can be demoed end-to-end today).

Usage:
  python3 aerosense_predict.py --sim          # generate synthetic data + train
  python3 aerosense_predict.py --db path.db   # train on real flight DB(s)

Install:
  pip3 install pandas numpy scikit-learn xgboost matplotlib
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import argparse
import sqlite3
import os
import glob
import math
import random
import warnings
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, KFold, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

warnings.filterwarnings("ignore")

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════

ALTITUDE_BANDS = [15.0, 30.0, 50.0]  # metres AGL — matches mission survey altitudes
BAND_TOLERANCE = 5.0                 # ± metres for assigning a sample to a band
GROUND_BAND    = 15.0                # "ground-level" proxy = lowest survey altitude
HORIZON_MIN    = 15                  # prediction horizon in minutes

FEATURE_COLUMNS = [
    "pm25_15", "pm25_30", "pm25_50",
    "temp_15", "temp_30", "temp_50",
    "pressure_15", "pressure_30", "pressure_50",
    "humidity_15", "humidity_30", "humidity_50",
    "temp_gradient_15_50",      # stability proxy: T(50m) - T(15m)
    "pressure_gradient_15_50",  # stability proxy
    "hour_of_day",
]
TARGET_COLUMN = "pm25_ground_future"

# ═════════════════════════════════════════════════════════════════════════════
# SYNTHETIC DATA GENERATOR (--sim mode)
# ═════════════════════════════════════════════════════════════════════════════

def generate_synthetic_flights(n_flights: int = 24, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic multi-flight vertical profile data with a
    realistic diurnal inversion cycle:

      - Early morning (5-8am): strong inversion -> pollution trapped
        aloft, ground PM2.5 LOW now but RISES as inversion breaks
        and trapped pollution mixes down.
      - Midday (11am-3pm): well-mixed atmosphere -> uniform PM2.5
        across altitudes, ground PM2.5 STABLE.
      - Evening (6-9pm): inversion re-forming -> ground PM2.5 RISES
        as traffic emissions get trapped near surface.

    Each "flight" = one vertical profile snapshot + the ground PM2.5
    value HORIZON_MIN later (the prediction target).
    """
    rng = np.random.default_rng(seed)
    rows = []

    base_date = datetime(2026, 1, 15, tzinfo=timezone.utc)

    for i in range(n_flights):
        # Spread flights across a realistic diurnal cycle over several days
        day_offset = i // 4
        hour = [6, 9, 13, 19][i % 4] + rng.normal(0, 0.5)
        hour = np.clip(hour, 5, 22)
        ts = base_date + timedelta(days=day_offset, hours=hour)

        # ── Atmospheric stability regime ──────────────────────────────────
        if 5 <= hour < 9:
            regime = "inversion_morning"
            temp_gradient = rng.uniform(1.5, 4.0)   # T(50m) > T(15m) -> stable
            trapped_pm    = rng.uniform(40, 90)     # high pollution trapped aloft
            ground_now    = rng.uniform(15, 30)     # currently low at ground
            mixing_factor = rng.uniform(0.3, 0.6)   # fraction of trapped PM that mixes down
        elif 11 <= hour < 16:
            regime = "well_mixed_midday"
            temp_gradient = rng.uniform(-2.0, 0.5)  # T(50m) < T(15m) -> unstable/mixed
            trapped_pm    = rng.uniform(15, 35)
            ground_now    = trapped_pm + rng.normal(0, 3)
            mixing_factor = rng.uniform(0.85, 1.0)  # nearly uniform already
        else:
            regime = "inversion_evening"
            temp_gradient = rng.uniform(1.0, 3.0)
            trapped_pm    = rng.uniform(20, 50)
            ground_now    = rng.uniform(25, 45)
            mixing_factor = rng.uniform(0.4, 0.7)

        pressure_gradient = -temp_gradient * rng.uniform(0.8, 1.2)  # correlated proxy

        # ── Build vertical profile ────────────────────────────────────────
        pm25_15 = ground_now + rng.normal(0, 2)
        pm25_30 = pm25_15 + (trapped_pm - pm25_15) * 0.5 + rng.normal(0, 2)
        pm25_50 = trapped_pm + rng.normal(0, 2)

        temp_15 = 28.0 + rng.normal(0, 1.0)
        temp_30 = temp_15 + temp_gradient * 0.5 + rng.normal(0, 0.3)
        temp_50 = temp_15 + temp_gradient + rng.normal(0, 0.3)

        pressure_15 = 1011.0 + rng.normal(0, 0.5)
        pressure_30 = pressure_15 + pressure_gradient * 0.5
        pressure_50 = pressure_15 + pressure_gradient

        humidity_15 = 68 + rng.normal(0, 3)
        humidity_30 = humidity_15 - 2 + rng.normal(0, 2)
        humidity_50 = humidity_15 - 4 + rng.normal(0, 2)

        # ── Target: ground PM2.5 HORIZON_MIN later ────────────────────────
        # Pollution aloft mixes toward ground proportional to mixing_factor
        pm25_ground_future = (
            ground_now * (1 - mixing_factor) +
            trapped_pm * mixing_factor +
            rng.normal(0, 3)
        )
        pm25_ground_future = max(0, pm25_ground_future)

        rows.append({
            "flight_id": i,
            "timestamp": ts.isoformat(),
            "regime": regime,
            "hour_of_day": hour,
            "pm25_15": max(0, pm25_15), "pm25_30": max(0, pm25_30), "pm25_50": max(0, pm25_50),
            "temp_15": temp_15, "temp_30": temp_30, "temp_50": temp_50,
            "pressure_15": pressure_15, "pressure_30": pressure_30, "pressure_50": pressure_50,
            "humidity_15": humidity_15, "humidity_30": humidity_30, "humidity_50": humidity_50,
            "temp_gradient_15_50": temp_50 - temp_15,
            "pressure_gradient_15_50": pressure_50 - pressure_15,
            "pm25_ground_future": pm25_ground_future,
        })

    return pd.DataFrame(rows)


# ═════════════════════════════════════════════════════════════════════════════
# REAL DATA LOADER — builds vertical profiles from aerosense.db flight logs
# ═════════════════════════════════════════════════════════════════════════════

def load_real_flights(db_paths: list) -> pd.DataFrame:
    """
    Load one or more aerosense.db SQLite files, bin readings into
    altitude bands, and construct vertical-profile feature rows.

    NOTE: Building (profile_now -> ground_future) pairs from real data
    requires either:
      (a) multiple flights at the same site at different times, or
      (b) a single long flight where the drone revisits ground level
          periodically (profile at T, ground reading at T+HORIZON_MIN)

    This loader implements approach (b) as the simplest path: it finds
    every "profile window" (one sample per altitude band within a short
    time span) and pairs it with the nearest ground-level (lowest band)
    reading HORIZON_MIN later in the same flight.
    """
    all_rows = []

    for db_path in db_paths:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("""
            SELECT timestamp, alt_m, pm25, temperature, humidity, pressure
            FROM pollution_points
            WHERE gps_quality > 0 AND pm25 >= 0 AND quality_flag & 1 = 0
            ORDER BY timestamp
        """, conn)
        conn.close()

        if df.empty:
            continue

        df["band"] = df["alt_m"].apply(_nearest_band)
        df = df.dropna(subset=["band"])

        # Group into ~2-minute windows, take mean reading per band per window
        df["window"] = (df["timestamp"] // 120).astype(int)
        profiles = df.groupby(["window", "band"]).agg(
            timestamp=("timestamp", "mean"),
            pm25=("pm25", "mean"),
            temp=("temperature", "mean"),
            humidity=("humidity", "mean"),
            pressure=("pressure", "mean"),
        ).reset_index()

        windows = sorted(profiles["window"].unique())

        for w in windows:
            wp = profiles[profiles["window"] == w]
            bands_present = set(wp["band"])
            if not all(b in bands_present for b in ALTITUDE_BANDS):
                continue  # incomplete profile, skip

            row = {"flight_id": db_path}
            ts_now = wp["timestamp"].mean()
            row["timestamp"] = datetime.fromtimestamp(ts_now, tz=timezone.utc).isoformat()
            row["hour_of_day"] = datetime.fromtimestamp(ts_now, tz=timezone.utc).hour

            for b in ALTITUDE_BANDS:
                b_int = int(b)
                wb = wp[wp["band"] == b]
                row[f"pm25_{b_int}"]      = float(wb["pm25"].iloc[0])
                row[f"temp_{b_int}"]      = float(wb["temp"].iloc[0])
                row[f"pressure_{b_int}"]  = float(wb["pressure"].iloc[0])
                row[f"humidity_{b_int}"]  = float(wb["humidity"].iloc[0])

            row["temp_gradient_15_50"]     = row["temp_50"] - row["temp_15"]
            row["pressure_gradient_15_50"] = row["pressure_50"] - row["pressure_15"]

            # Find ground reading ~HORIZON_MIN later
            target_ts = ts_now + HORIZON_MIN * 60
            future = df[(df["band"] == GROUND_BAND) &
                        (df["timestamp"] >= target_ts - 60) &
                        (df["timestamp"] <= target_ts + 60)]
            if future.empty:
                continue

            row["pm25_ground_future"] = float(future["pm25"].mean())
            all_rows.append(row)

    return pd.DataFrame(all_rows)


def _nearest_band(alt: float) -> float | None:
    for b in ALTITUDE_BANDS:
        if abs(alt - b) <= BAND_TOLERANCE:
            return b
    return None


# ═════════════════════════════════════════════════════════════════════════════
# MODEL TRAINING & EVALUATION
# ═════════════════════════════════════════════════════════════════════════════

def train_and_evaluate(df: pd.DataFrame, model_type: str = "rf"):
    print(f"\n{'='*60}")
    print(f"  AeroSense Vertical Profile Predictor")
    print(f"{'='*60}")
    print(f"  Samples available : {len(df)}")
    print(f"  Prediction horizon: {HORIZON_MIN} minutes")
    print(f"  Model             : {'XGBoost' if model_type=='xgb' and HAS_XGB else 'RandomForest'}")
    print(f"{'='*60}\n")

    if len(df) < 6:
        print("⚠️  Too few samples for train/test split.")
        print("    Need at least ~6 profile windows. Run with --sim for a demo,")
        print("    or collect more flight data at varying times of day.\n")
        return None

    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]

    test_size = 0.25 if len(df) >= 12 else max(1/len(df), 0.2)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    if model_type == "xgb" and HAS_XGB:
        model = xgb.XGBRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            random_state=42, verbosity=0)
    else:
        model = RandomForestRegressor(
            n_estimators=100, max_depth=5, random_state=42)

    model.fit(X_train_s, y_train)
    y_pred = model.predict(X_test_s)

    mae = mean_absolute_error(y_test, y_pred)
    r2  = r2_score(y_test, y_pred) if len(y_test) > 1 else float("nan")

    # Cross-validation (more honest with small datasets)
    n_folds = min(5, len(df))
    if n_folds >= 3:
        cv = KFold(n_splits=n_folds, shuffle=True, random_state=42)
        cv_scores = cross_val_score(model, scaler.fit_transform(X), y,
                                     cv=cv, scoring="neg_mean_absolute_error")
        cv_mae = -cv_scores.mean()
        cv_std = cv_scores.std()
    else:
        cv_mae = cv_std = float("nan")

    print(f"  Test set ({len(y_test)} samples):")
    print(f"    MAE  : {mae:.2f} µg/m³")
    print(f"    R²   : {r2:.3f}")
    print(f"\n  {n_folds}-fold cross-validation:")
    print(f"    MAE  : {cv_mae:.2f} ± {cv_std:.2f} µg/m³")

    # Feature importance
    print(f"\n  Feature importance (top 5):")
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS)
    for feat, imp in importances.sort_values(ascending=False).head(5).items():
        bar = "█" * int(imp * 40)
        print(f"    {feat:28s} {imp:.3f} {bar}")

    print(f"\n{'='*60}")
    print("  INTERPRETATION GUIDE")
    print(f"{'='*60}")
    print("""
  If temp_gradient_15_50 or pressure_gradient_15_50 rank highly,
  the model has learned that the temperature/pressure DIFFERENCE
  between altitude bands (i.e., atmospheric stability) is predictive
  of future ground PM2.5 — consistent with inversion-layer physics.

  HONEST CAVEAT:
  With """ + str(len(df)) + """ samples, this is a PROOF-OF-CONCEPT.
  MAE of a few µg/m³ on synthetic data demonstrates the PIPELINE
  works end-to-end. Real-world validation requires multiple flights
  at the same site across different times of day — the more diverse
  the diurnal coverage, the more the model can learn genuine
  stability-driven patterns vs. noise.
""")

    return {"model": model, "scaler": scaler, "mae": mae, "r2": r2,
            "cv_mae": cv_mae, "importances": importances}


# ═════════════════════════════════════════════════════════════════════════════
# PREDICTION ON NEW PROFILE
# ═════════════════════════════════════════════════════════════════════════════

def predict_single(model, scaler, profile: dict) -> float:
    """
    Predict future ground PM2.5 from a single vertical profile dict.
    profile keys must match FEATURE_COLUMNS.
    """
    X = pd.DataFrame([profile])[FEATURE_COLUMNS]
    X_s = scaler.transform(X)
    return float(model.predict(X_s)[0])


# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="AeroSense vertical profile -> ground PM2.5 predictor")
    parser.add_argument("--sim", action="store_true",
                        help="Generate synthetic multi-flight data and train on it")
    parser.add_argument("--db", nargs="+", default=None,
                        help="Path(s) to aerosense.db SQLite file(s)")
    parser.add_argument("--n-flights", type=int, default=24,
                        help="Number of synthetic flights to generate (--sim mode)")
    parser.add_argument("--model", choices=["rf", "xgb"], default="rf",
                        help="Model type: rf (RandomForest) or xgb (XGBoost)")
    parser.add_argument("--export-csv", default=None,
                        help="Export the training dataframe to CSV")
    args = parser.parse_args()

    if args.sim:
        print(f"Generating {args.n_flights} synthetic flight profiles...")
        df = generate_synthetic_flights(n_flights=args.n_flights)
        print(f"Regimes: {df['regime'].value_counts().to_dict()}\n")
    elif args.db:
        print(f"Loading real flight data from: {args.db}")
        df = load_real_flights(args.db)
        if df.empty:
            print("\n⚠️  No complete vertical profiles found in the provided DB(s).")
            print("    A 'complete profile' needs samples at ~15m, ~30m, AND ~50m")
            print("    within the same ~2-minute window, plus a ground-level")
            print(f"    reading ~{HORIZON_MIN} min later.")
            print("\n    Falling back to --sim demo data so you can see the pipeline:\n")
            df = generate_synthetic_flights(n_flights=args.n_flights)
    else:
        # Try auto-discovering DBs, else fall back to sim
        candidates = glob.glob("data/aerosense/*.db") + glob.glob("**/aerosense.db", recursive=True)
        if candidates:
            print(f"Auto-discovered: {candidates}")
            df = load_real_flights(candidates)
            if df.empty:
                df = generate_synthetic_flights(n_flights=args.n_flights)
        else:
            print("No --sim or --db specified, and no aerosense.db found.")
            print("Running with synthetic demo data (--sim equivalent):\n")
            df = generate_synthetic_flights(n_flights=args.n_flights)

    if args.export_csv:
        df.to_csv(args.export_csv, index=False)
        print(f"Exported training data to {args.export_csv}")

    result = train_and_evaluate(df, model_type=args.model)

    if result:
        # Save model and scaler for live dashboard integration
        import pickle
        # Ensure data folder exists
        os.makedirs("data", exist_ok=True)
        model_out = "data/aerosense_model.pkl"
        try:
            with open(model_out, "wb") as f:
                pickle.dump(result, f)
            print(f"  Model successfully saved to {model_out}\n")
        except Exception as e:
            print(f"  ⚠️ Error saving model: {e}\n")

        # Demo prediction on a hypothetical morning-inversion profile
        print(f"{'='*60}")
        print("  EXAMPLE PREDICTION")
        print(f"{'='*60}")
        example_profile = {
            "pm25_15": 22.0, "pm25_30": 45.0, "pm25_50": 70.0,
            "temp_15": 27.5, "temp_30": 29.0, "temp_50": 30.5,
            "pressure_15": 1011.0, "pressure_30": 1010.2, "pressure_50": 1009.5,
            "humidity_15": 70, "humidity_30": 67, "humidity_50": 64,
            "temp_gradient_15_50": 3.0,
            "pressure_gradient_15_50": -1.5,
            "hour_of_day": 7,
        }
        pred = predict_single(result["model"], result["scaler"], example_profile)
        print(f"""
  Scenario: 7am, strong inversion detected
    Ground PM2.5 NOW        : {example_profile['pm25_15']:.1f} µg/m³
    PM2.5 at 50m (trapped)  : {example_profile['pm25_50']:.1f} µg/m³
    Temp gradient (50-15m)  : +{example_profile['temp_gradient_15_50']:.1f}°C (stable/inverted)

  PREDICTED ground PM2.5 in {HORIZON_MIN} min: {pred:.1f} µg/m³

  Interpretation: The model predicts ground PM2.5 will RISE from
  {example_profile['pm25_15']:.1f} toward the elevated {example_profile['pm25_50']:.1f} µg/m³
  level as the morning inversion breaks and trapped pollution mixes
  down — this is the "predict the descent" capability discussed
  conceptually, now implemented as a working pipeline.
""")


if __name__ == "__main__":
    main()
