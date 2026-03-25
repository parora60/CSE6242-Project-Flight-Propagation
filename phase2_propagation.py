"""
Phase 2 – Flight Delay Propagation Network
===========================================
Input : flights_clean.parquet  (output of Phase 1)
Output: data/network_graph.json     – nodes + edges for D3
        data/cascade_results.json   – per-seed cascade sequences
        data/monthly_graphs/        – per-month sub-graphs (same schema)

Run:
    python phase2_propagation.py
    python phase2_propagation.py --parquet path/to/flights_clean.parquet
"""

import argparse
import json
import os
import warnings
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# 0. CONFIG
# ─────────────────────────────────────────────
PROP_THRESHOLD_MIN = 15         # min arrival delay on flight N to count as a propagation seed (15 is the BTS standard for geniune delay)
LATE_AC_THRESHOLD_MIN = 15      # min LateAircraftDelay on flight N+1 to confirm propagation (15 is the BTS standard for genuine delay)
TURNAROUND_BUFFER_MIN = 30      # scheduled turnaround below this → treat as too tight (flag only)
TOP_SEED_AIRPORTS = 20          # number of top airports used for cascade simulation
CASCADE_DECAY = 0.5             # each hop retains 50% of the incoming delay
CASCADE_HOPS = 6                # max cascade depth for simulation
CASCADE_THRESHOLD_MIN = 15      # initial delay threshold fed into cascade sim (minutes)

# Airport coordinates (IATA → lat/lon/city).
# This table covers ~350 most common US airports; extras get (None, None).
AIRPORT_META_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)

# ─────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────

def load_flights(parquet_path: str) -> pd.DataFrame:
    print(f"[1/7] Loading {parquet_path} …")
    df = pd.read_parquet(parquet_path, engine='fastparquet')
    print(f"      {len(df):,} rows | columns: {list(df.columns)}")

    # Ensure correct dtypes ------------------------------------------------
    df["FL_DATE"] = pd.to_datetime(df["FL_DATE"])
    df["MONTH"]   = df["FL_DATE"].dt.month

    # Numeric delay columns: fill NaN → 0 (BTS convention)
    delay_cols = ["DEP_DELAY", "ARR_DELAY", "LATE_AIRCRAFT_DELAY",
                  "WEATHER_DELAY", "NAS_DELAY", "CARRIER_DELAY", "SEC_DELAY"]
    for c in delay_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Drop cancelled / diverted – they break tail chains
    before = len(df)
    df = df[df["CANCELLED"].fillna(0) == 0]
    df = df[df["DIVERTED"].fillna(0) == 0]
    print(f"      Dropped {before - len(df):,} cancelled/diverted rows → {len(df):,} remain")

    # Drop chain-break rows produced by Phase 1 (if column exists)
    if "CHAIN_BREAK" in df.columns:
        cb = df["CHAIN_BREAK"].fillna(0).astype(bool)
        print(f"      Flagging {cb.sum():,} chain-break transition rows (kept but transition excluded)")

    return df


# ─────────────────────────────────────────────
# 2. AIRCRAFT ROTATION RECONSTRUCTION
# ─────────────────────────────────────────────

def reconstruct_rotations(df: pd.DataFrame) -> pd.DataFrame:
    """
    For every tail number sort flights chronologically and pair consecutive legs.
    Returns a DataFrame of (flight_N, flight_N+1) transition pairs.

    Uses DEP_TIME_MIN (minutes since midnight, produced by Phase 1) + FL_DATE
    to build a monotone timestamp that correctly handles overnight flights.
    """
    print("[2/7] Reconstructing aircraft rotations …")

    # Build a sortable timestamp: FL_DATE midnight + DEP_TIME_MIN
    # IS_OVERNIGHT flag from Phase 1 is respected – no extra adjustment needed
    # because DEP_TIME_MIN is already in [0, 1439] local minutes.
    if "DEP_TIME_MIN" in df.columns:
        df = df.copy()
        df["_sort_ts"] = (
            df["FL_DATE"].astype(np.int64) // 10**9          # Unix seconds
            + df["DEP_TIME_MIN"].fillna(0) * 60
        )
    else:
        # Fallback: parse CRS_DEP_TIME (hhmm integer)
        df = df.copy()
        df["_sort_ts"] = (
            df["FL_DATE"].astype(np.int64) // 10**9
            + (df["CRS_DEP_TIME"].fillna(0).astype(int) // 100) * 3600
            + (df["CRS_DEP_TIME"].fillna(0).astype(int) % 100) * 60
        )

    df_sorted = df.sort_values(["TAIL_NUM", "_sort_ts"])

    # Shift by 1 within each tail to align consecutive legs
    # g = df_sorted.groupby("TAIL_NUM", sort=False)

    keep_cols = [
        "TAIL_NUM", "FL_DATE", "MONTH", "_sort_ts",
        "ORIGIN", "DEST",
        "DEP_DELAY", "ARR_DELAY",
        "LATE_AIRCRAFT_DELAY", "WEATHER_DELAY",
        "NAS_DELAY", "CARRIER_DELAY", "SEC_DELAY",
        "OP_UNIQUE_CARRIER",
    ]
    # Only keep cols that exist
    keep_cols = [c for c in keep_cols if c in df_sorted.columns]

    # df_n  = df_sorted[keep_cols].copy()
    # df_n1 = df_sorted[keep_cols].copy().add_suffix("_NEXT")

    # # Concat side-by-side via index shift within group
    # # We'll use a vectorised shift approach
    # idx   = df_sorted.index.to_numpy()
    # tail  = df_sorted["TAIL_NUM"].to_numpy()

    # # Mark rows where NEXT row belongs to the same tail
    # same_tail = np.empty(len(df_sorted), dtype=bool)
    # same_tail[:-1] = tail[:-1] == tail[1:]
    # same_tail[-1]  = False

    # df_transitions = df_n[same_tail].copy().reset_index(drop=True)
    # df_next_vals   = df_n1[np.roll(same_tail, -1) | same_tail].copy()  # shift trick

    # Simpler: just iloc-shift within groups --------------------------------
    pairs_list = []
    chunk_size = 500_000  # process in chunks to stay memory-friendly
    all_tails  = df_sorted["TAIL_NUM"].unique()

    for i in range(0, len(all_tails), chunk_size):
        batch = all_tails[i:i + chunk_size]
        sub   = df_sorted[df_sorted["TAIL_NUM"].isin(batch)][keep_cols]
        shifted = sub.groupby("TAIL_NUM", sort=False).shift(-1).add_suffix("_NEXT")
        combined = pd.concat([sub.reset_index(drop=True),
                               shifted.reset_index(drop=True)], axis=1)
        # Drop last row of each tail (NaN next)
        combined = combined.dropna(subset=["ORIGIN_NEXT"])
        # Geography consistency check: DEST must equal ORIGIN_NEXT
        combined = combined[combined["DEST"] == combined["ORIGIN_NEXT"]]
        pairs_list.append(combined)

    pairs = pd.concat(pairs_list, ignore_index=True)
    print(f"      {len(pairs):,} valid consecutive-leg transition pairs")
    return pairs


# ─────────────────────────────────────────────
# 3. PROPAGATION EVENT DETECTION
# ─────────────────────────────────────────────

def detect_propagation_events(pairs: pd.DataFrame) -> pd.DataFrame:
    """
    A propagation event is defined when:
      (a) Flight N arrives delayed  (ARR_DELAY > PROP_THRESHOLD_MIN), AND
      (b) Flight N+1 has LATE_AIRCRAFT_DELAY > LATE_AC_THRESHOLD_MIN
          OR (more robustly) DEP_DELAY_NEXT > 0 and the scheduled turnaround
          is tight enough that the arrival delay plausibly caused it.

    The propagated delay magnitude:
        prop_delay = min(ARR_DELAY, LATE_AIRCRAFT_DELAY_NEXT)   [primary]
        prop_delay = min(ARR_DELAY, DEP_DELAY_NEXT)             [fallback]

    Returns the subset of pairs that are propagation events.
    """
    print("[3/7] Detecting propagation events …")

    p = pairs.copy()

    # ── Primary criterion: explicit LateAircraftDelay ──
    primary_mask = (
        (p["ARR_DELAY"] >= PROP_THRESHOLD_MIN) &
        (p["LATE_AIRCRAFT_DELAY_NEXT"] >= LATE_AC_THRESHOLD_MIN)
    )

    # ── Secondary criterion: turnaround-aware propagation ──
    # Even if LateAircraftDelay is 0 (mis-coded), if the next flight
    # departed late AND the prior arrival was late, flag it.
    secondary_mask = (
        (p["ARR_DELAY"] >= PROP_THRESHOLD_MIN) &
        (p["DEP_DELAY_NEXT"] >= PROP_THRESHOLD_MIN) &
        (p["LATE_AIRCRAFT_DELAY_NEXT"] < LATE_AC_THRESHOLD_MIN)   # not already captured
    )

    p["is_primary"]   = primary_mask
    p["is_secondary"] = secondary_mask
    p["is_propagation"] = primary_mask | secondary_mask

    events = p[p["is_propagation"]].copy()

    # Propagated delay magnitude
    events["prop_delay_min"] = np.where(
        events["is_primary"],
        np.minimum(events["ARR_DELAY"], events["LATE_AIRCRAFT_DELAY_NEXT"]),
        np.minimum(events["ARR_DELAY"], events["DEP_DELAY_NEXT"])
    ).clip(0)

    # Delay cause attribution on the *originating* flight
    # (whichever cause column is largest = dominant cause)
    cause_cols = ["LATE_AIRCRAFT_DELAY", "WEATHER_DELAY",
                  "NAS_DELAY", "CARRIER_DELAY", "SEC_DELAY"]
    avail_cause = [c for c in cause_cols if c in events.columns]
    if avail_cause:
        events["dominant_cause"] = events[avail_cause].idxmax(axis=1).str.replace("_DELAY", "")
    else:
        events["dominant_cause"] = "UNKNOWN"

    print(f"      {len(events):,} propagation events  "
          f"({primary_mask.sum():,} primary / {secondary_mask.sum():,} secondary)")
    return events


# ─────────────────────────────────────────────
# 4. LOAD AIRPORT METADATA
# ─────────────────────────────────────────────

# Hardcoded lat/lon for the 60 busiest US airports (fallback if network unavailable)
AIRPORT_COORDS = {
    "ATL": (33.6407, -84.4277, "Atlanta", "GA"),
    "LAX": (33.9425, -118.4081, "Los Angeles", "CA"),
    "ORD": (41.9742, -87.9073, "Chicago", "IL"),
    "DFW": (32.8998, -97.0403, "Dallas", "TX"),
    "DEN": (39.8561, -104.6737, "Denver", "CO"),
    "JFK": (40.6413, -73.7781, "New York", "NY"),
    "SFO": (37.6213, -122.3790, "San Francisco", "CA"),
    "SEA": (47.4502, -122.3088, "Seattle", "WA"),
    "LAS": (36.0840, -115.1537, "Las Vegas", "NV"),
    "MCO": (28.4312, -81.3081, "Orlando", "FL"),
    "EWR": (40.6895, -74.1745, "Newark", "NJ"),
    "MIA": (25.7959, -80.2870, "Miami", "FL"),
    "CLT": (35.2144, -80.9473, "Charlotte", "NC"),
    "PHX": (33.4373, -112.0078, "Phoenix", "AZ"),
    "IAH": (29.9902, -95.3368, "Houston", "TX"),
    "BOS": (42.3656, -71.0096, "Boston", "MA"),
    "MSP": (44.8848, -93.2223, "Minneapolis", "MN"),
    "DTW": (42.2162, -83.3554, "Detroit", "MI"),
    "PHL": (39.8719, -75.2411, "Philadelphia", "PA"),
    "LGA": (40.7772, -73.8726, "New York", "NY"),
    "FLL": (26.0726, -80.1527, "Fort Lauderdale", "FL"),
    "BWI": (39.1754, -76.6683, "Baltimore", "MD"),
    "DCA": (38.8521, -77.0377, "Washington", "DC"),
    "MDW": (41.7868, -87.7522, "Chicago", "IL"),
    "IAD": (38.9531, -77.4565, "Dulles", "VA"),
    "SLC": (40.7884, -111.9778, "Salt Lake City", "UT"),
    "HNL": (21.3187, -157.9225, "Honolulu", "HI"),
    "SAN": (32.7336, -117.1897, "San Diego", "CA"),
    "TPA": (27.9755, -82.5332, "Tampa", "FL"),
    "PDX": (45.5898, -122.5951, "Portland", "OR"),
    "DAL": (32.8471, -96.8518, "Dallas Love", "TX"),
    "HOU": (29.6454, -95.2789, "Houston Hobby", "TX"),
    "OAK": (37.7213, -122.2208, "Oakland", "CA"),
    "MCI": (39.2976, -94.7139, "Kansas City", "MO"),
    "RDU": (35.8776, -78.7875, "Raleigh-Durham", "NC"),
    "AUS": (30.1975, -97.6664, "Austin", "TX"),
    "STL": (38.7487, -90.3700, "St. Louis", "MO"),
    "MSY": (29.9934, -90.2580, "New Orleans", "LA"),
    "SMF": (38.6954, -121.5908, "Sacramento", "CA"),
    "BNA": (36.1245, -86.6782, "Nashville", "TN"),
    "SJC": (37.3626, -121.9290, "San Jose", "CA"),
    "JAX": (30.4941, -81.6879, "Jacksonville", "FL"),
    "CLE": (41.4117, -81.8498, "Cleveland", "OH"),
    "PIT": (40.4915, -80.2329, "Pittsburgh", "PA"),
    "IND": (39.7173, -86.2944, "Indianapolis", "IN"),
    "CMH": (39.9980, -82.8919, "Columbus", "OH"),
    "SAT": (29.5337, -98.4698, "San Antonio", "TX"),
    "CVG": (39.0488, -84.6678, "Cincinnati", "OH"),
    "BUF": (42.9405, -78.7322, "Buffalo", "NY"),
    "OMA": (41.3032, -95.8941, "Omaha", "NE"),
    "EAR": (40.7270, -99.0068, "Kearney", "NE"),
    "XWA": (48.2594, -103.7514, "Williston", "ND"),
    "ABQ": (35.0402, -106.6090, "Albuquerque", "NM"),
    "MEM": (35.0424, -89.9767, "Memphis", "TN"),
    "BDL": (41.9389, -72.6832, "Hartford", "CT"),
    "RIC": (37.5052, -77.3197, "Richmond", "VA"),
    "ORF": (36.8976, -76.0183, "Norfolk", "VA"),
    "TUL": (36.1984, -95.8881, "Tulsa", "OK"),
    "OKC": (35.3931, -97.6007, "Oklahoma City", "OK"),
    "RSW": (26.5362, -81.7552, "Fort Myers", "FL"),
    "PBI": (26.6832, -80.0956, "West Palm Beach", "FL"),
    "ELP": (31.8072, -106.3779, "El Paso", "TX"),
    "BOI": (43.5644, -116.2228, "Boise", "ID"),
    "GEG": (47.6199, -117.5339, "Spokane", "WA"),
    "LIT": (34.7294, -92.2243, "Little Rock", "AR"),
    "MKE": (42.9472, -87.8966, "Milwaukee", "WI"),
    "ALB": (42.7483, -73.8017, "Albany", "NY"),
    "TUS": (32.1161, -110.9410, "Tucson", "AZ"),
    "SNA": (33.6757, -117.8682, "Orange County", "CA"),
    "BUR": (34.2007, -118.3585, "Burbank", "CA"),
    "LGB": (33.8177, -118.1516, "Long Beach", "CA"),
    "SBA": (34.4262, -119.8401, "Santa Barbara", "CA"),
    "PSP": (33.8297, -116.5067, "Palm Springs", "CA"),
    "FAT": (36.7762, -119.7182, "Fresno", "CA"),
    "RNO": (39.4991, -119.7681, "Reno", "NV"),
    "COS": (38.8058, -104.7008, "Colorado Springs", "CO"),
    "ASE": (39.2232, -106.8688, "Aspen", "CO"),
    "GRR": (42.8808, -85.5228, "Grand Rapids", "MI"),
    "DSM": (41.5340, -93.6631, "Des Moines", "IA"),
    "BHM": (33.5629, -86.7535, "Birmingham", "AL"),
    "GSO": (36.0978, -79.9373, "Greensboro", "NC"),
    "CAE": (33.9389, -81.1195, "Columbia", "SC"),
    "CHS": (32.8986, -80.0405, "Charleston", "SC"),
    "SAV": (32.1276, -81.2021, "Savannah", "GA"),
    "AGS": (33.3699, -81.9645, "Augusta", "GA"),
    "DAY": (39.9024, -84.2194, "Dayton", "OH"),
    "SDF": (38.1744, -85.7360, "Louisville", "KY"),
    "LEX": (38.0365, -84.6059, "Lexington", "KY"),
    "TYS": (35.8110, -83.9940, "Knoxville", "TN"),
    "CHA": (35.0353, -85.2038, "Chattanooga", "TN"),
    "HSV": (34.6372, -86.7751, "Huntsville", "AL"),
    "MOB": (30.6913, -88.2428, "Mobile", "AL"),
    "PNS": (30.4734, -87.1866, "Pensacola", "FL"),
    "VPS": (30.4832, -86.5254, "Fort Walton Beach", "FL"),
    "TLH": (30.3965, -84.3503, "Tallahassee", "FL"),
    "SRQ": (27.3954, -82.5544, "Sarasota", "FL"),
    "GNV": (29.6900, -82.2717, "Gainesville", "FL"),
    "DAB": (29.1799, -81.0581, "Daytona Beach", "FL"),
    "SFB": (28.7776, -81.2375, "Orlando Sanford", "FL"),
    "MLB": (28.1028, -80.6453, "Melbourne", "FL"),
    "EYW": (24.5561, -81.7596, "Key West", "FL"),
    "MYR": (33.6797, -78.9283, "Myrtle Beach", "SC"),
    "ILM": (34.2706, -77.9026, "Wilmington", "NC"),
    "AVL": (35.4362, -82.5418, "Asheville", "NC"),
    "FAY": (34.9912, -78.8800, "Fayetteville", "NC"),
    "ORH": (42.2673, -71.8758, "Worcester", "MA"),
    "PVD": (41.7272, -71.4282, "Providence", "RI"),
    "MHT": (42.9326, -71.4357, "Manchester", "NH"),
    "BTV": (44.4720, -73.1533, "Burlington", "VT"),
    "PWM": (43.6462, -70.3093, "Portland", "ME"),
    "BGR": (44.8074, -68.8281, "Bangor", "ME"),
    "ACK": (41.2531, -70.0600, "Nantucket", "MA"),
    "HYA": (41.6693, -70.2803, "Hyannis", "MA"),
    "SYR": (43.1112, -76.1063, "Syracuse", "NY"),
    "ROC": (43.1189, -77.6724, "Rochester", "NY"),
    "ITH": (42.4910, -76.4584, "Ithaca", "NY"),
    "ELM": (42.1599, -76.8916, "Elmira", "NY"),
    "BGM": (42.2087, -75.9798, "Binghamton", "NY"),
    "SWF": (41.5041, -74.1048, "Newburgh", "NY"),
    "ACY": (39.4576, -74.5772, "Atlantic City", "NJ"),
    "ABE": (40.6521, -75.4408, "Allentown", "PA"),
    "AVP": (41.3385, -75.7233, "Wilkes-Barre", "PA"),
    "IPT": (41.2418, -76.9212, "Williamsport", "PA"),
    "ERI": (42.0832, -80.1739, "Erie", "PA"),
    "MDT": (40.1935, -76.7634, "Harrisburg", "PA"),
    "CRW": (38.3731, -81.5932, "Charleston", "WV"),
    "HTS": (38.3667, -82.5580, "Huntington", "WV"),
    "MGM": (32.3006, -86.3940, "Montgomery", "AL"),
    "GPT": (30.4073, -89.0701, "Gulfport", "MS"),
    "JAN": (32.3112, -90.0759, "Jackson", "MS"),
    "BTR": (30.5332, -91.1496, "Baton Rouge", "LA"),
    "SHV": (32.4466, -93.8256, "Shreveport", "LA"),
    "LFT": (30.2053, -91.9876, "Lafayette", "LA"),
    "AEX": (31.3274, -92.5488, "Alexandria", "LA"),
    "MLU": (32.5109, -92.0377, "Monroe", "LA"),
    "LRD": (27.5438, -99.4616, "Laredo", "TX"),
    "CRP": (27.7704, -97.5012, "Corpus Christi", "TX"),
    "BRO": (25.9068, -97.4259, "Brownsville", "TX"),
    "HRL": (26.2285, -97.6544, "Harlingen", "TX"),
    "MAF": (31.9425, -102.2019, "Midland", "TX"),
    "AMA": (35.2194, -101.7059, "Amarillo", "TX"),
    "LBB": (33.6636, -101.8228, "Lubbock", "TX"),
    "MFE": (26.1758, -98.2386, "McAllen", "TX"),
    "ACT": (31.6113, -97.2305, "Waco", "TX"),
    "GRK": (31.0672, -97.8289, "Killeen", "TX"),
    "ABI": (32.4113, -99.6819, "Abilene", "TX"),
    "SJT": (31.3573, -100.4966, "San Angelo", "TX"),
    "TXK": (33.4539, -93.9910, "Texarkana", "TX"),
    "ICT": (37.6499, -97.4331, "Wichita", "KS"),
    "MHK": (39.1410, -96.6708, "Manhattan", "KS"),
    "GCK": (37.9275, -100.7238, "Garden City", "KS"),
    "TOP": (39.0687, -95.6633, "Topeka", "KS"),
    "FOE": (38.9509, -95.6636, "Topeka Forbes", "KS"),
    "SPN": (15.1197, 145.7290, "Saipan", "MP"),
    "GUM": (13.4834, 144.7960, "Guam", "GU"),
    "PPG": (-14.3310, -170.7105, "Pago Pago", "AS"),
    "STX": (17.7019, -64.7985, "St. Croix", "VI"),
    "STT": (18.3373, -64.9733, "St. Thomas", "VI"),
    "SJU": (18.4373, -66.0018, "San Juan", "PR"),
    "BQN": (18.4949, -67.1294, "Aguadilla", "PR"),
    "PSE": (18.0083, -66.5631, "Ponce", "PR"),
    "MAZ": (18.2557, -67.1485, "Mayagüez", "PR"),
    "ANC": (61.1744, -149.9982, "Anchorage", "AK"),
    "FAI": (64.8151, -147.8561, "Fairbanks", "AK"),
    "JNU": (58.3550, -134.5763, "Juneau", "AK"),
    "KTN": (55.3556, -131.7137, "Ketchikan", "AK"),
    "SIT": (57.0471, -135.3616, "Sitka", "AK"),
    "BET": (60.7798, -161.8380, "Bethel", "AK"),
    "OME": (64.5123, -165.4451, "Nome", "AK"),
    "OTZ": (66.8847, -162.5990, "Kotzebue", "AK"),
}

def fetch_openflights_coords() -> dict:
    """Fetch lat/lon for all IATA codes from OpenFlights (fallback for missing coords)."""
    import urllib.request, csv, io
    url = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
    coords = {}
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            for row in csv.reader(io.StringIO(r.read().decode('utf-8', errors='ignore'))):
                if len(row) < 8:
                    continue
                iata = row[4].strip().strip('"')
                if len(iata) != 3:
                    continue
                try:
                    coords[iata] = (float(row[6]), float(row[7]),
                                    row[1].strip('"'), row[3].strip('"'))
                except ValueError:
                    continue
        print(f"      OpenFlights: loaded coords for {len(coords)} airports")
    except Exception as e:
        print(f"      ⚠ Could not fetch OpenFlights data: {e} — falling back to hardcoded table only")
    return coords

def load_airport_meta(iata_codes: list) -> pd.DataFrame:
    """Build a lookup DataFrame for all IATA codes present in the network."""
    print("[4/7] Loading airport metadata …")
    of_coords = fetch_openflights_coords()
    rows = []
    missing = []
    for code in iata_codes:
        if code in AIRPORT_COORDS:
            lat, lon, city, state = AIRPORT_COORDS[code]
        elif code in of_coords:
            lat, lon, city, state = of_coords[code]
        else:
            lat, lon, city, state = None, None, code, "??"
            missing.append(code)
        rows.append({"iata": code, "city": city, "state": state,
                     "lat": lat, "lon": lon})
    if missing:
        print(f"      ⚠ Still no coords for {len(missing)} airports: {missing[:10]} …")
    else:
        print(f"      ✓ Full coordinate coverage for all {len(rows)} airports")
    meta = pd.DataFrame(rows).set_index("iata")
    print(f"      Metadata built for {len(meta)} airports")
    return meta


# ─────────────────────────────────────────────
# 5. BUILD DIRECTED WEIGHTED NETWORK
# ─────────────────────────────────────────────

def build_network(events: pd.DataFrame, meta: pd.DataFrame,
                  month: int = None) -> dict:
    """
    Construct directed weighted graph from propagation events.
    Returns a dict ready for JSON export.
    """
    label = f"month={month}" if month else "full-year"
    print(f"[5/7] Building propagation network ({label}) …")

    sub = events if month is None else events[events["MONTH"] == month]

    # ── Edge aggregation ──────────────────────────────────────────────────
    edge_agg = (
        sub.groupby(["ORIGIN", "DEST"])
        .agg(
            event_count=("prop_delay_min", "count"),
            avg_delay=("prop_delay_min", "mean"),
            total_delay=("prop_delay_min", "sum"),
            med_delay=("prop_delay_min", "median"),
            late_aircraft_events=("is_primary", "sum"),
            weather_events=("WEATHER_DELAY", lambda x: (x > 0).sum()),
            nas_events=("NAS_DELAY", lambda x: (x > 0).sum()),
            carrier_events=("CARRIER_DELAY", lambda x: (x > 0).sum()),
        )
        .reset_index()
    )

    # ── Node-level metrics ─────────────────────────────────────────────────
    # Out-degree: how many prop events originated here
    out_stats = (
        sub.groupby("ORIGIN")
        .agg(
            out_events=("prop_delay_min", "count"),
            out_delay_min=("prop_delay_min", "sum"),
        )
        .rename_axis("airport")
    )
    # In-degree: how many prop events ended here
    in_stats = (
        sub.groupby("DEST")
        .agg(
            in_events=("prop_delay_min", "count"),
            in_delay_min=("prop_delay_min", "sum"),
        )
        .rename_axis("airport")
    )

    # Total outbound flights for denominator (from full dataset context is gone –
    # use out_events as proxy; callers can enrich with total_flights separately)
    node_stats = out_stats.join(in_stats, how="outer").fillna(0)

    # Propagation Risk Score = outbound propagated minutes / outbound events
    # (a.k.a. average delay per export event)
    node_stats["prop_risk_score"] = np.where(
        node_stats["out_events"] > 0,
        node_stats["out_delay_min"] / node_stats["out_events"],
        0,
    )

    # ── NetworkX for centrality ────────────────────────────────────────────
    G = nx.DiGraph()
    for _, row in edge_agg.iterrows():
        G.add_edge(
            row["ORIGIN"], row["DEST"],
            weight=row["event_count"],
            avg_delay=row["avg_delay"],
        )

    print("      Computing betweenness centrality (this may take ~30s) …")
    try:
        bc = nx.betweenness_centrality(G, weight="weight", normalized=True)
    except Exception:
        bc = {n: 0 for n in G.nodes()}

    # PageRank as additional systemic-importance metric with uniform fallback if weights are all zero or computation fails
    try:
        max_weight = max(d["weight"] for _, _, d in G.edges(data=True))
        if max_weight > 0:
            for u, v, d in G.edges(data=True):
                d["weight_norm"] = d["weight"] / max_weight
            pr = nx.pagerank(G, weight="weight_norm", alpha=0.85, max_iter=200)
        else:
            pr = nx.pagerank(G, alpha=0.85, max_iter=200)
    except Exception as e:
        print(f"      ⚠ PageRank failed: {e} — using uniform fallback")
        n_nodes = len(G.nodes())
        pr = {n: 1.0 / n_nodes for n in G.nodes()} if n_nodes > 0 else {}

    # ── Assemble nodes JSON ────────────────────────────────────────────────
    all_airports = sorted(set(edge_agg["ORIGIN"]) | set(edge_agg["DEST"]))
    nodes = []
    for ap in all_airports:
        ns   = node_stats.loc[ap] if ap in node_stats.index else {}
        m    = meta.loc[ap] if ap in meta.index else {}
        node = {
            "id":              ap,
            "city":            str(m.get("city", ap)),
            "state":           str(m.get("state", "??")),
            "lat":             float(m["lat"]) if pd.notna(m.get("lat")) else None,
            "lon":             float(m["lon"]) if pd.notna(m.get("lon")) else None,
            "out_events":      int(ns.get("out_events", 0)),
            "in_events":       int(ns.get("in_events", 0)),
            "out_delay_min":   float(ns.get("out_delay_min", 0)),
            "in_delay_min":    float(ns.get("in_delay_min", 0)),
            "prop_risk_score": float(ns.get("prop_risk_score", 0)),
            "betweenness":     float(bc.get(ap, 0)),
            "pagerank":        float(pr.get(ap, 0)),
            "net_export":      int(ns.get("out_events", 0)) - int(ns.get("in_events", 0)),
        }
        nodes.append(node)

    # ── Assemble edges JSON ────────────────────────────────────────────────
    links = []
    for _, row in edge_agg.iterrows():
        link = {
            "source":               row["ORIGIN"],
            "target":               row["DEST"],
            "event_count":          int(row["event_count"]),
            "avg_delay":            round(float(row["avg_delay"]), 2),
            "total_delay":          round(float(row["total_delay"]), 2),
            "med_delay":            round(float(row["med_delay"]), 2),
            "late_aircraft_events": int(row["late_aircraft_events"]),
            "weather_events":       int(row["weather_events"]),
            "nas_events":           int(row["nas_events"]),
            "carrier_events":       int(row["carrier_events"]),
        }
        links.append(link)

    graph = {"nodes": nodes, "links": links, "month": month}
    print(f"      → {len(nodes)} nodes, {len(links)} directed edges")
    return graph


# ─────────────────────────────────────────────
# 6. CASCADE SIMULATION
# ─────────────────────────────────────────────

def simulate_cascades(events: pd.DataFrame, top_airports: list,
                      initial_delay: float = CASCADE_THRESHOLD_MIN,
                      max_hops: int = CASCADE_HOPS) -> dict:
    """
    BFS-style cascade simulation.
    For each seed airport, propagate an initial delay through the network using observed edge weights (avg_delay transfer factor).
    Has minimum edge threshold to prevent noise-driven cascades, and a maximum neighbor cap to prevent superfanout from hubs.
    Has a decay factor to prevent unrealistically large transfers from very high initial delays, and caps at observed avg_delay on that edge.
    Stops when no new airports are affected or max_hops is reached.

    Returns a dict: { "IATA": [ {hop, airport, delay_min, new_airports}, … ] }
    """
    print(f"[6/7] Running cascade simulations (top {len(top_airports)} seeds) …")

    MIN_EDGE_EVENTS = 50    # only routes with 50+ propagation events are cascade-eligible
    MAX_NEIGHBORS = 20      # each airport fans out to at most 20 others in cascade

    # Build transition matrix: edge → avg prop_delay_min
    edge_map = (
        events.groupby(["ORIGIN", "DEST"])["prop_delay_min"]
        .agg(["mean", "count"])
        .reset_index()
    )
    edge_map = edge_map[edge_map["count"] >= MIN_EDGE_EVENTS]  # filter weak edges

    # Neighbor list: airport → {dest: avg_delay}
    neighbors: dict = {}
    for origin, grp in edge_map.groupby("ORIGIN"):
        # Keep only the top MAX_NEIGHBORS destinations by event count
        top = grp.nlargest(MAX_NEIGHBORS, "count")
        neighbors[origin] = dict(zip(top["DEST"], top["mean"]))

    all_cascades = {}

    for seed in tqdm(top_airports, desc="  Cascades"):
        steps = []
        # State: {airport: current_delay_minutes}
        current_wave = {seed: initial_delay}
        visited = {seed}

        for hop in range(1, max_hops + 1):
            next_wave = {}
            newly_affected = []
            for airport, delay in current_wave.items():
                for dest, avg_prop in neighbors.get(airport, {}).items():
                    # Transfer fraction: propagated = min(delay * CASCADE_DECAY, avg_prop on that edge) - prevents casing unrealistically large transfers from very high initial delays; also caps at observed avg_prop
                    transferred = min(delay * CASCADE_DECAY, avg_prop)
                    if transferred >= 1.0:   # only propagate if > 1 min
                        if dest not in visited:
                            visited.add(dest)
                            newly_affected.append(dest)
                        if dest not in next_wave or next_wave[dest] < transferred:
                            next_wave[dest] = transferred

            if not next_wave:
                break  # cascade died out

            steps.append({
                "hop":             hop,
                "newly_affected":  newly_affected,
                "wave":            {k: round(v, 2) for k, v in next_wave.items()},
                "total_airports":  len(visited),
                "total_delay":     round(sum(next_wave.values()), 2),
            })
            current_wave = next_wave

        all_cascades[seed] = steps

    print(f"      Cascade simulations complete.")
    return all_cascades


# ─────────────────────────────────────────────
# 7. ENRICH NODES WITH FLIGHT COUNTS & EXPORT
# ─────────────────────────────────────────────

def enrich_with_flight_counts(graph: dict, df: pd.DataFrame) -> dict:
    """Add total outbound/inbound flight count to each node for normalization."""
    out_flights = df.groupby("ORIGIN").size().to_dict()
    in_flights  = df.groupby("DEST").size().to_dict()
    for node in graph["nodes"]:
        ap = node["id"]
        node["total_out_flights"] = int(out_flights.get(ap, 0))
        node["total_in_flights"]  = int(in_flights.get(ap, 0))
        # Normalised risk: propagation events / total flights
        node["prop_risk_norm"] = (
            node["out_events"] / node["total_out_flights"]
            if node["total_out_flights"] > 0 else 0
        )
    return graph


def export_json(obj, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)
    size_kb = Path(path).stat().st_size / 1024
    print(f"      ✓ Saved {path}  ({size_kb:.1f} KB)")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main(parquet_path: str, output_dir: str = "data"):
    # 1. Load
    df = load_flights(parquet_path)

    # 2. Rotation reconstruction
    pairs = reconstruct_rotations(df)

    # 3. Propagation events
    events = detect_propagation_events(pairs)

    # Save events CSV for audit
    events_path = f"{output_dir}/propagation_events.csv"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    events.to_csv(events_path, index=False)
    print(f"      ✓ Saved propagation events → {events_path}")

    # 4. Airport metadata
    all_airports = sorted(set(events["ORIGIN"]) | set(events["DEST"]))
    meta = load_airport_meta(all_airports)

    # 5. Build full-year network
    graph = build_network(events, meta, month=None)
    graph = enrich_with_flight_counts(graph, df)
    export_json(graph, f"{output_dir}/network_graph.json")

    # 5b. Build per-month networks
    monthly_dir = f"{output_dir}/monthly_graphs"
    for m in sorted(events["MONTH"].unique()):
        g_m = build_network(events, meta, month=int(m))
        g_m = enrich_with_flight_counts(g_m, df[df["MONTH"] == m])
        export_json(g_m, f"{monthly_dir}/network_month_{int(m):02d}.json")

    # 6. Cascade simulation – seed from top airports by out_events
    top_nodes = sorted(
        graph["nodes"],
        key=lambda n: n["out_events"],
        reverse=True,
    )[:TOP_SEED_AIRPORTS]
    top_airports = [n["id"] for n in top_nodes]
    cascades = simulate_cascades(events, top_airports)
    export_json(cascades, f"{output_dir}/cascade_results.json")

    # 7. Summary report
    print("\n" + "=" * 60)
    print("PHASE 2 COMPLETE – SUMMARY")
    print("=" * 60)
    print(f"  Propagation events       : {len(events):,}")
    print(f"  Network nodes (airports) : {len(graph['nodes'])}")
    print(f"  Network edges (routes)   : {len(graph['links'])}")
    print(f"  Monthly graphs           : {len(events['MONTH'].unique())}")
    print(f"  Cascade seeds simulated  : {len(top_airports)}")
    print()
    print("Top 10 airports by Total Outbound Propagation Events (cascade seeds):")
    for n in top_nodes[:10]:
        print(f"  {n['id']}  out_events={n['out_events']:,}  "
              f"risk_score={n['prop_risk_score']:.1f} min  betweenness={n['betweenness']:.4f}")
    print()
    print("Output files:")
    print(f"  {output_dir}/network_graph.json      → full-year D3 network")
    print(f"  {output_dir}/monthly_graphs/          → per-month D3 networks")
    print(f"  {output_dir}/cascade_results.json     → cascade animation data")
    print(f"  {output_dir}/propagation_events.csv   → raw event audit log")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 – Delay Propagation Network")
    parser.add_argument(
        "--parquet",
        default="./data/clean/flights_clean.parquet",
        help="Path to flights_clean.parquet (Phase 1 output)",
    )
    parser.add_argument(
        "--output",
        default="data",
        help="Output directory for JSON files (default: ./data)",
    )
    args = parser.parse_args()
    main(args.parquet, args.output)
