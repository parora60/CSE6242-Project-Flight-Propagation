# CSE6242-Project-Flight-Propagation

# Phase 2 – Flight Delay Propagation Network

## Overview

This phase takes `flights_clean.parquet` (Phase 1 output) and produces
structured JSON files ready to be consumed by the D3.js visualization in Phase 3.

The pipeline reconstructs aircraft rotation chains, detects delay propagation events
(where a late inbound aircraft causes the next flight on that tail to depart late),
builds a directed weighted network, computes graph centrality metrics, and runs
cascade simulations from the top hub airports.

---

## Files

| File | Description |
|---|---|
| `phase2_propagation.py` | Main pipeline – run this first |
| `phase2_validate.py` | Validation & charts – run after main pipeline |
| `requirements_phase2.txt` | Python dependencies |
| `docs/FINDINGS.md` | Phase 2 analytical findings and anomalies |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements_phase2.txt

# 2. Run the pipeline (adjust --parquet path as needed)
python phase2_propagation.py --parquet ./data/parquet/flights_clean.parquet --output data

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
| `data/validation_charts/` | PNG charts for midpoint report |

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
      "out_events": 33786,
      "in_events": 31200,
      "out_delay_min": 1716000.0,
      "in_delay_min": 1420000.0,
      "prop_risk_score": 50.8,
      "betweenness": 0.0345,
      "pagerank": 0.0421,
      "net_export": 2586,
      "total_out_flights": 320000,
      "total_in_flights": 318500,
      "prop_risk_norm": 0.106
    }
  ],
  "links": [
    {
      "source": "ATL",
      "target": "ORD",
      "event_count": 1820,
      "avg_delay": 48.4,
      "total_delay": 88088.0,
      "med_delay": 38.0,
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
  "DFW": [
    {
      "hop": 1,
      "newly_affected": ["ORD", "ATL", "LAX"],
      "wave": {"ORD": 7.5, "ATL": 6.2, "LAX": 5.8},
      "total_airports": 4,
      "total_delay": 19.5
    }
  ]
}
```

---

## Propagation Logic

A delay is considered **propagated** when either:

1. **Primary** – Flight N has `ARR_DELAY ≥ 15 min` AND the next flight by the
   same aircraft has `LATE_AIRCRAFT_DELAY ≥ 15 min`.

2. **Secondary (turnaround-aware)** – Flight N has `ARR_DELAY ≥ 15 min` AND
   Flight N+1 has `DEP_DELAY ≥ 15 min` but `LATE_AIRCRAFT_DELAY` is under-reported.

The **15-minute threshold** matches the BTS (Bureau of Transportation Statistics)
official definition of a delayed flight, filtering out gate holds and minor ATC
micro-delays that do not represent real operational disruptions.

The **propagated delay magnitude** = `min(ARR_DELAY_N, LATE_AIRCRAFT_DELAY_N+1)`
for primary events, or `min(ARR_DELAY_N, DEP_DELAY_N+1)` for secondary.

Chain-break transitions (from Phase 1's `CHAIN_BREAK` column) and all
cancelled/diverted flights are excluded from propagation detection.

---

## Metrics Reference

### Node Metrics

**`out_events`** — Raw count of propagation events originating at this airport (i.e.,
how many times a delayed inbound aircraft here caused the next departure to run late).
Pure volume measure. DFW at ~40,000 means 40,000 confirmed tail-chain propagations
in 2025. Used for: node sizing in D3, cascade seed selection.

**`prop_risk_score`** — Total outbound propagated minutes ÷ total outbound propagation
events. Measures average delay severity per propagation event. An airport scoring 56
means that when it propagates a delay, that delay averages 56 minutes. Does not
capture volume — a tiny airport with one 120-minute event scores higher than DFW.
Used for: node color heat in D3 (primary visual encoding per planning doc).

**`betweenness`** — Graph betweenness centrality computed over the directed weighted
network. Measures how often an airport sits on the shortest propagation path between
every other pair of airports. High betweenness = structural bottleneck. ORD scores
highest among hubs; KOA (Kona) scores high because Hawaiian routes are thin spokes
with no bypass alternatives. Used for: alternative node sizing, network analysis.

**`pagerank`** — Adapted from Google's PageRank algorithm. Treats the propagation
network as a weighted random walk: an airport scores high by receiving delays from
other high-scoring airports (recursive importance). DFW at ~0.054 means ~5.4% of
all random-walk time is spent at DFW. Differs from `out_events` in that it weights
*who* sends you delays, not just how many. Used for: systemic importance overlay,
detail panel ranking in D3.

**`net_export`** — `out_events - in_events`. Positive = net delay exporter (generates
more cascades than it absorbs); negative = net absorber. Used for: exporter vs
absorber classification in D3.

**`prop_risk_norm`** — `out_events / total_out_flights`. Fraction of outbound flights
that resulted in a propagation event. Normalizes for airport size so small and large
airports can be compared fairly.

### Node Metrics Summary Table (D3 visual encoding)

| Field | What it measures | D3 use |
|---|---|---|
| `out_events` | Volume of delay exported | Node size / cascade seed selection |
| `prop_risk_score` | Avg severity per propagation event | Node color heat (primary) |
| `betweenness` | Structural network bottleneck | Alternative node sizing |
| `pagerank` | Recursive systemic importance | Detail panel ranking |
| `net_export` | Exporter (+) vs absorber (−) | Node classification |
| `prop_risk_norm` | Risk normalized by total flights | Comparative risk overlay |

### Edge Metrics (D3 visual encoding)

| Field | What it measures | D3 use |
|---|---|---|
| `event_count` | Propagation frequency on this route | Edge thickness |
| `avg_delay` | Average delay transferred on this route | Edge opacity |
| `late_aircraft_events` | Events driven by late aircraft cause | Cause filter |
| `weather_events` | Events driven by weather cause | Cause filter |
| `nas_events` | Events driven by NAS (ATC/capacity) cause | Cause filter |
| `carrier_events` | Events driven by carrier cause | Cause filter |

---

## Cascade Simulation

The cascade simulation models what happens when a major hub experiences a systemic
15-minute delay shock. Starting from each of the top 20 airports (by total outbound
delay minutes), it propagates delays through the network using a BFS approach with:

- **Decay factor of 0.5** per hop (each airport receives at most 50% of the
  incoming delay, preventing unrealistic long-distance amplification)
- **Minimum 50 events** on a route for it to be cascade-eligible (filters noise routes)
- **Top 20 neighbors** per airport by event count (caps fan-out at major hubs)
- **Maximum 6 hops** before forced cutoff

Results show DFW/ORD reaching ~86-89 airports in 3 hops; CLT/DEN reaching ~74-88,
reflecting real differences in hub connectivity.

---

## Known Limitations

- **Cascade decay is linear** — the 0.5 factor is a modeling simplification;
  real propagation attenuation varies by route, carrier, and time of day.
- **December data absent** — the dataset covers January–November 2025 only.