# CSE6242-Project-Flight-Propagation

# Phase 2 – Flight Delay Propagation Network

## Overview

This phase takes `flights_clean.parquet` (Phase 1 output) and produces
structured JSON files ready to be consumed by the D3.js visualization in Phase 3.

---

## Files

| File | Description |
|---|---|
| `phase2_propagation.py` | Main pipeline – run this first |
| `phase2_validate.py` | Validation & charts – run after main pipeline |
| `requirements_phase2.txt` | Python dependencies |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements_phase2.txt

# 2. Run the pipeline  (adjust --parquet path as needed)
python phase2_propagation.py --parquet ./data/clean/flights_clean.parquet --output data

# 3. Validate outputs + generate charts
python phase2_validate.py --data_dir data
```

---

## Output Files for D3

| File | Used for |
|---|---|
| `data/network_graph.json` | Full-year node/edge graph (map + metrics) |
| `data/monthly_graphs/network_month_XX.json` | Per-month sub-graphs (month filter) |
| `data/cascade_results.json` | Cascade animation step sequences |
| `data/propagation_events.csv` | Raw audit log (not needed by D3) |

---

## JSON Schema

### `network_graph.json`

```json
{
  "month": null,
  "nodes": [
    {
      "id": "ATL",
      "city": "Atlanta",
      "state": "GA",
      "lat": 33.6407,
      "lon": -84.4277,
      "out_events": 42310,
      "in_events": 38200,
      "out_delay_min": 1204000.0,
      "in_delay_min": 980000.0,
      "prop_risk_score": 28.4,
      "betweenness": 0.0842,
      "pagerank": 0.0531,
      "net_export": 4110,
      "total_out_flights": 320000,
      "total_in_flights": 318500,
      "prop_risk_norm": 0.132
    }
  ],
  "links": [
    {
      "source": "ATL",
      "target": "ORD",
      "event_count": 1820,
      "avg_delay": 28.4,
      "total_delay": 51688.0,
      "med_delay": 22.0,
      "late_aircraft_events": 1540,
      "weather_events": 210,
      "nas_events": 310,
      "carrier_events": 180
    }
  ]
}
```

### `cascade_results.json`

```json
{
  "ATL": [
    {
      "hop": 1,
      "newly_affected": ["ORD", "DFW", "LAX"],
      "wave": {"ORD": 12.4, "DFW": 9.1, "LAX": 7.8},
      "total_airports": 4,
      "total_delay": 29.3
    },
    ...
  ]
}
```

---

## Propagation Logic

A delay is considered **propagated** when either:

1. **Primary** – Flight N has `ARR_DELAY ≥ 1 min` AND the next flight by the
   same aircraft has `LATE_AIRCRAFT_DELAY ≥ 1 min`.

2. **Secondary (turnaround-aware)** – Flight N has `ARR_DELAY ≥ 1 min` AND
   Flight N+1 has `DEP_DELAY ≥ 1 min` but LateAircraftDelay is under-reported.

The **propagated delay magnitude** = `min(ARR_DELAY_N, LATE_AIRCRAFT_DELAY_N+1)`
for primary events, or `min(ARR_DELAY_N, DEP_DELAY_N+1)` for secondary.

Chain-break transitions (from Phase 1's `CHAIN_BREAK` column) and all
cancelled/diverted flights are excluded from propagation detection.

---

## Node Metrics (for D3 visual encoding)

| Field | D3 use |
|---|---|
| `prop_risk_score` | Node radius / color heat |
| `betweenness` | Alternative node sizing |
| `pagerank` | Systemic importance overlay |
| `net_export` | Exporter (+) vs absorber (−) classification |
| `prop_risk_norm` | Normalised risk (events / total flights) |

## Edge Metrics (for D3 visual encoding)

| Field | D3 use |
|---|---|
| `event_count` | Edge thickness |
| `avg_delay` | Edge opacity |
| `late_aircraft_events` | Filter: late aircraft cause |
| `weather_events` | Filter: weather cause |
| `nas_events` | Filter: NAS cause |
| `carrier_events` | Filter: carrier cause |
