# CSE6242 — Flight Delay Propagation Network

### Team 31 · Ayush Acharya · Fanwei Lu · Miguel A Barragan Cantor · Pranav Arora · Syed Muhammad Kamran Asghar

> Converts ~6.6 million US airline records into an interactive network map that reveals
> which airports and routes drive cascading delays across the country. Built entirely
> from public BTS on-time performance data (January–November 2025).

---

## Table of Contents

0. [Quick Start — Run Everything at Once](#0-quick-start--run-everything-at-once)
1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Phase 1 — Data Pipeline](#3-phase-1--data-pipeline)
4. [Phase 2 — Propagation Model & Experiments](#4-phase-2--propagation-model--experiments)
5. [Phase 3 — D3 Visualization](#5-phase-3--d3-visualization)
6. [Other Notes](#6-other-notes)

---

## 0. Quick Start — Run Everything at Once

### TL;DR:

- Run everything:
  ```bash
  python run_all.py
  # or: python3 run_all.py
  ```
- Open: [**http://localhost:8080**](http://localhost:8080) (opens automatically)
- Pipeline: Data → Network → Visualization (3 phases)
- Works on **Windows, macOS, and Linux** — no bash required

<details>
<summary><h3 style="display: inline;">More details:</h3></summary>

`run_all.py` is a single cross-platform Python script that installs dependencies,
runs the full pipeline (Phases 1 → 2 → validation), and launches the visualization
server. Works on Windows, macOS, and Linux — no bash or shell required.

### Prerequisites

- Python 3.9+ with `pip` (use `python3`/`pip3` if your system requires it)
- BTS CSV files placed in `data/csv/` (see §3.2 for download instructions)

### Common scenarios

**First time — build everything from raw CSVs:**

```bash
python run_all.py
# or: python3 run_all.py
```

Installs dependencies, runs the Phase 1 notebook to produce `flights_clean.parquet`,
runs the Phase 2 pipeline to build `network_graph.json` and `cascade_results.json`,
runs validation, then starts the server and opens your browser automatically. Phase 1
is skipped automatically on subsequent runs if the parquet already exists.

Open **http://localhost:8080** in your browser.

---

**Pipeline code changed, raw data unchanged** (most common during development):

```bash
python run_all.py --force-phase2
# or: python3 run_all.py --force-phase2
```

Skips the Phase 1 notebook (reuses the existing parquet), clears the previous
Phase 2 outputs, and rebuilds the network and cascade JSON files from scratch.
Use this whenever you update `phase2_propagation.py` and need fresh JSON outputs.

---

**Raw BTS CSV data changed** (new months added, source data updated):

```bash
python run_all.py --force-all
# or: python3 run_all.py --force-all
```

Deletes the existing parquet and re-runs Phase 1 from the raw CSVs, then runs
Phase 2. Use this when the underlying data — not just the pipeline code — has changed.

---

**JSON outputs already built — just open the visualization:**

```bash
python run_all.py --viz-only
# or: python3 run_all.py --viz-only
```

Skips all pipeline steps and immediately starts the HTTP server. Requires
`data/network_graph.json` and `data/cascade_results.json` to already exist.

---

### All flags

| Flag             | When to use                                                            |
| ---------------- | ---------------------------------------------------------------------- |
| _(none)_         | Auto mode — skips Phase 1 if parquet exists, always runs Phase 2       |
| `--force-phase2` | Pipeline code changed; rebuild network/cascade from existing parquet   |
| `--force-all`    | Raw CSV data changed; delete parquet and rebuild everything            |
| `--viz-only`     | Data already built; skip pipeline and start server immediately         |
| `--parquet PATH` | Use a parquet file at a non-default path                               |
| `--data_dir DIR` | Write/read JSON outputs to a non-default directory (default: `./data`) |
| `--port PORT`    | Start the HTTP server on a different port (default: `8080`)            |

### Run phases individually

If you prefer to run each phase manually rather than through `run_all.py`:

```bash
# Phase 1 — run the notebook
pip install nbconvert ipykernel        # or: pip3 install ...
jupyter nbconvert --to notebook --execute project_pipeline.ipynb \
    --ExecutePreprocessor.kernel_name=python3

# Phase 2 — build the network
pip install -r requirements_phase2.txt  # or: pip3 install ...
python phase2_propagation.py --parquet ./data/parquet/flights_clean.parquet
# or: python3 phase2_propagation.py ...

# Phase 2 — validate outputs and generate charts
python phase2_validate.py              # or: python3 phase2_validate.py

# Phase 2 — scalability & sensitivity experiments (optional)
python phase2_experiments.py --parquet ./data/parquet/flights_clean.parquet
# or: python3 phase2_experiments.py ...

# Phase 3 — start the visualization server
python -m http.server 8080             # or: python3 -m http.server 8080
# Open http://localhost:8080
```

## </details>

## 1. Project Overview

Standard flight metrics treat each flight in isolation. This project instead follows how one
late aircraft affects every subsequent flight on that tail number — reconstructing the real
chain of cause-and-effect through the national network. The pipeline runs in three phases:

| Phase       | What it does                                                                        | Primary output                               |
| ----------- | ----------------------------------------------------------------------------------- | -------------------------------------------- |
| **Phase 1** | Ingest & clean 11 months of raw BTS CSVs                                            | `flights_clean.parquet`                      |
| **Phase 2** | Reconstruct rotation chains, detect propagation events, build network, run cascades | `network_graph.json`, `cascade_results.json` |
| **Phase 3** | Serve an interactive D3 map of the propagation network                              | `index.html`                                 |

---

## 2. Repository Structure

```
.
├── data/
│   ├── csv/                          # Raw BTS monthly CSV files (not committed)
│   └── parquet/                      # Phase 1 outputs
│       ├── flights_clean.parquet     # Main file consumed by Phase 2
│       ├── flights_cancelled.parquet
│       ├── flights_diverted.parquet
│       └── ingestion_report.csv
│
├── project_pipeline.ipynb            # Phase 1 — data ingestion & cleaning notebook
│
├── phase2_propagation.py             # Phase 2 — main propagation pipeline
├── phase2_validate.py                # Phase 2 — validation checks & charts
├── phase2_experiments.py             # Phase 2 — scalability & sensitivity experiments
├── requirements_phase2.txt           # Phase 2 Python dependencies
│
├── index.html                        # Phase 3 — D3 visualization (standalone)
│
└── docs/
    └── FINDINGS.md                   # Analytical findings and anomalies
```

**Phase 2 pipeline outputs** (written to `data/` by `phase2_propagation.py`):

| File                                        | Description                                            |
| ------------------------------------------- | ------------------------------------------------------ |
| `data/network_graph.json`                   | Full-year node/edge graph (349 airports, 6,582 routes) |
| `data/monthly_graphs/network_month_XX.json` | Per-month sub-graphs (11 files, Jan–Nov)               |
| `data/cascade_results.json`                 | Cascade animation step sequences                       |
| `data/propagation_events.csv`               | Raw propagation event audit log                        |
| `data/validation_charts/`                   | PNG summary charts from `phase2_validate.py`           |
| `data/experiment_*.csv`                     | CSVs from `phase2_experiments.py`                      |

---

## 3. Phase 1 — Data Pipeline

### 3.1 What it does

`project_pipeline.ipynb` ingests all monthly BTS on-time performance CSV files,
cleans and validates the data, reconstructs the column structure needed for Phase 2's
tail-chain algorithm, and exports a clean Parquet file.

<details>
<summary><h3 style="display: inline;">Breaking down the pipeline:</h3></summary>

### 3.2 Setup & Running

**Prerequisites:** Python with Anaconda (pandas, numpy, matplotlib included). Only extra
dependency is `pyarrow` for Parquet export.

```bash
pip install pyarrow --quiet
```

**Data download:** Download BTS on-time performance CSV files (one per month, Jan–Nov 2025)
from the [Bureau of Transportation Statistics](https://www.transtats.bts.gov/DL_SelectFields.aspx).
Place all files in `data/csv/`.

**Run:** Open and run `project_pipeline.ipynb` cell by cell, or run all cells at once.
The notebook is self-contained and prints status after each step.

### 3.3 Pipeline Steps

The notebook runs 9 cells in sequence:

| Cell | Step               | What happens                                                                                                                                                                                    |
| ---- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0    | Library imports    | pandas, numpy, pathlib, glob                                                                                                                                                                    |
| 1    | Configuration      | Sets `DATA_DIR`, column renames, the 25 `KEEP_COLS`, and the 15-min `DELAY_THRESHOLD`                                                                                                           |
| 2    | File discovery     | Lists all CSVs found in `DATA_DIR`, shows sizes and column counts                                                                                                                               |
| 3    | Load & merge       | Reads each CSV as `dtype=str`, normalizes column names, applies renames, concatenates all months                                                                                                |
| 4    | Null handling      | Drops rows with null/invalid `TAIL_NUM`; splits cancelled/diverted flights into separate frames; fills delay cause nulls with 0                                                                 |
| 5    | Type conversions   | Converts `FL_DATE` to datetime; `CRS_DEP_TIME` etc. to hhmm integers with `_MIN` variants; delay columns to signed floats; adds derived columns (`MONTH`, `YEAR`, `IS_WEEKEND`, `FL_DATE_ONLY`) |
| 6    | Validation checks  | 7 checks (see §3.4 below)                                                                                                                                                                       |
| 7    | Validation summary | Prints all check results in one table                                                                                                                                                           |
| 8    | Export             | Writes `flights_clean.parquet`, `flights_cancelled.parquet`, `flights_diverted.parquet`, `ingestion_report.csv`                                                                                 |
| 9    | EDA sanity check   | 4-panel chart: flights per month, top-20 origins, LATE_AIRCRAFT_DELAY distribution, delay rate by carrier                                                                                       |

### 3.4 Validation Checks

| Check | What it tests                                                                                                                              |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 1     | `ARR_TIME_MIN > DEP_TIME_MIN` for non-overnight flights; overnight legs flagged `IS_OVERNIGHT=1`                                           |
| 2     | Geographic chain consistency: `DEST` of flight N = `ORIGIN` of flight N+1 for same aircraft same day. Broken links flagged `CHAIN_BREAK=1` |
| 3     | `ORIGIN` and `DEST` match the pattern `^[A-Z]{3}$` (valid IATA codes)                                                                      |
| 4     | Sum of delay cause columns ≤ `ARR_DELAY` + 5 min tolerance                                                                                 |
| 5     | `DAY_OF_WEEK` matches day derived from `FL_DATE`; auto-corrected from `FL_DATE` if mismatch                                                |
| 6     | `LATE_AIRCRAFT_DELAY > 0` only when `ARR_DELAY > 0`                                                                                        |
| 7     | Monthly flight counts are consistent (flags any month > 30% below median)                                                                  |

### 3.5 Key Columns in `flights_clean.parquet`

| Column                                          | Type     | Description                                                        |
| ----------------------------------------------- | -------- | ------------------------------------------------------------------ |
| `FL_DATE`                                       | datetime | Flight date                                                        |
| `TAIL_NUM`                                      | str      | Aircraft tail number — key for rotation chain reconstruction       |
| `OP_CARRIER`                                    | str      | Operating carrier IATA code                                        |
| `ORIGIN` / `DEST`                               | str      | Origin/destination IATA airport codes                              |
| `DEP_DELAY` / `ARR_DELAY`                       | float    | Signed minutes (negative = early)                                  |
| `LATE_AIRCRAFT_DELAY`                           | float    | Minutes of delay attributed to late inbound aircraft               |
| `CARRIER_DELAY` / `WEATHER_DELAY` / `NAS_DELAY` | float    | Other delay cause minutes                                          |
| `CHAIN_BREAK`                                   | int      | 1 = broken tail chain at this flight (DEST of prior ≠ ORIGIN here) |
| `IS_OVERNIGHT`                                  | int      | 1 = departs before midnight, arrives after                         |
| `DEP_TIME_MIN` / `ARR_TIME_MIN`                 | Int64    | Clock times as minutes since midnight                              |
| `MONTH` / `YEAR` / `IS_WEEKEND`                 | int      | Derived time features                                              |

### 3.6 Phase 1 → Phase 2 Handoff Checklist

Before passing the Parquet to Phase 2, verify:

- [ ] All 11 months present (Check 7 shows no low-count months)
- [ ] Chain break rate reviewed and accepted (Check 2)
- [ ] ORIGIN/DEST are valid IATA codes (Check 3 passed with 0 violations)
- [ ] `TAIL_NUM` has no nulls (enforced in Cell 4)
- [ ] `IS_OVERNIGHT` and `CHAIN_BREAK` columns present
- [ ] Validation summary shows no unresolved ⚠️ items

```python
# Phase 2 entry point
import pandas as pd
df = pd.read_parquet('./data/parquet/flights_clean.parquet')
```

 </details>

## 4. Phase 2 — Propagation Model & Experiments

### 4.1 Setup

```bash
pip install -r requirements_phase2.txt
```

### 4.2 Running the Pipeline

```bash
# Main pipeline — run first
python phase2_propagation.py \
    --parquet ./data/parquet/flights_clean.parquet \
    --output data

# Validate outputs + generate summary charts
python phase2_validate.py --data_dir data

# Scalability & sensitivity experiments — run after pipeline
python phase2_experiments.py \
    --parquet ./data/parquet/flights_clean.parquet \
    --data_dir data
```

### 4.3 Propagation Logic

The pipeline reconstructs **aircraft rotation chains** by sorting flights within each
`TAIL_NUM` by date and departure time. Consecutive flights on the same tail form a chain;
broken links (flagged `CHAIN_BREAK=1` in Phase 1) are excluded.

A delay is considered **propagated** when either:

1. **Primary** — Flight N has `ARR_DELAY ≥ 15 min` AND the next flight by the same
   aircraft has `LATE_AIRCRAFT_DELAY ≥ 15 min` (explicitly coded by BTS).

2. **Secondary (turnaround-aware)** — Flight N has `ARR_DELAY ≥ 15 min` AND Flight N+1
   has `DEP_DELAY ≥ 15 min` but `LATE_AIRCRAFT_DELAY` is under-reported.

The **15-minute threshold** matches the BTS official definition of a delayed flight.
The **propagated delay magnitude** is `min(ARR_DELAY_N, LATE_AIRCRAFT_DELAY_N+1)` for
primary events, or `min(ARR_DELAY_N, DEP_DELAY_N+1)` for secondary.

**Result:** 6,307,561 active flights → 696,975 propagation events → 349-airport directed
network with 6,582 weighted edges.

### 4.4 Network Metrics

#### Node Metrics

| Field             | What it measures                                                                        | Visualization use                  |
| ----------------- | --------------------------------------------------------------------------------------- | ---------------------------------- |
| `out_events`      | Raw count of propagation events originating here                                        | Node size, cascade seed selection  |
| `prop_risk_score` | Total outbound propagated minutes ÷ events (avg severity)                               | Node color heat (primary encoding) |
| `betweenness`     | How often this airport lies on the shortest propagation path between other pairs        | Alternative node sizing            |
| `pagerank`        | Recursive importance — scores high by receiving delays from other high-scoring airports | Detail panel ranking               |
| `net_export`      | `out_events − in_events`; positive = net exporter, negative = absorber                  | Node classification                |
| `prop_risk_norm`  | `out_events / total_out_flights`; fraction of departures that caused a propagation      | Comparative risk overlay           |

Key distinction: `out_events` measures _how often_ an airport exports delays; `prop_risk_score`
measures _how bad_ each export is. DFW leads in volume (~40K events); small airports like
GUM (Guam) lead in severity because one long international diversion dominates their average.

#### Edge Metrics

| Field                                                                       | What it measures                        | Visualization use     |
| --------------------------------------------------------------------------- | --------------------------------------- | --------------------- |
| `event_count`                                                               | Propagation frequency on this route     | Edge thickness        |
| `avg_delay`                                                                 | Average delay transferred on this route | Edge opacity          |
| `late_aircraft_events` / `weather_events` / `nas_events` / `carrier_events` | Breakdown by delay cause                | Cause breakdown chart |

### 4.5 Cascade Simulation

Models a systemic 15-minute delay shock spreading from a seed hub using BFS with:

- **Decay factor 0.5 per hop** — each downstream airport receives ≤50% of incoming delay.
- **Minimum 50 events** on a route to be cascade-eligible (filters noise routes).
- **Top 20 neighbors** per airport by event count (caps fan-out at major hubs).
- **Maximum 6 hops** before forced cutoff.

| Seed | Airports reached | Hops | Notes                                             |
| ---- | ---------------- | ---- | ------------------------------------------------- |
| DFW  | 89               | 3    | Widest reach; American Airlines hub concentration |
| LAX  | 89               | 3    | Tied with DFW; Pacific gateway effect             |
| ORD  | 86               | 3    | Highest betweenness; United hub                   |
| DEN  | 88               | 3    | United hub; western gateway                       |
| ATL  | 83               | 3    | Delta hub; Southeast spoke density                |
| CLT  | 75               | 3    | American hub; narrower regional reach             |
| DCA  | 75               | 3    | Constrained by slot controls                      |

### 4.6 JSON Schema

#### `network_graph.json`

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
      "late_aircraft_events": 1540,
      "weather_events": 210,
      "nas_events": 310,
      "carrier_events": 180
    }
  ]
}
```

Monthly files (`network_month_XX.json`) share the same schema with `"month": 1–11`.

#### `cascade_results.json`

```json
{
  "DFW": [
    {
      "hop": 1,
      "newly_affected": ["ORD", "ATL", "LAX"],
      "wave": { "ORD": 7.5, "ATL": 6.2, "LAX": 5.8 },
      "total_airports": 4,
      "total_delay": 19.5
    }
  ]
}
```

### 4.7 Experiments (`phase2_experiments.py`)

Run after the main pipeline. Reads existing outputs only — does **not** modify any
pipeline data or JSON files. Results saved as separate CSVs.

<details>
<summary><h4 style="display: inline;">Click to see experiments:</h4></summary>

#### Experiment 1 — Scalability

Measures `build_network()` runtime as the dataset grows from 1 to 11 months (steps:
1, 2, 3, 6, 9, 11). Filters already-computed propagation events, rebuilds the network
at each step, records node count, edge count, and wall-clock time.

**Output:** `data/experiment_scalability.csv` — `months`, `events`, `nodes`, `edges`, `time_s`  
**Report use:** Evidence of computational tractability; shows the pipeline scales linearly.

#### Experiment 2 — Threshold Sensitivity

Re-runs propagation detection at 1, 15, and 30-minute thresholds. Compares event
counts, primary/secondary split, median/mean delay, and DFW's risk score. At 1 min,
only 44% of events are primary (confirmed `LATE_AIRCRAFT_DELAY`); at 15 min that rises
to 62% — confirming the threshold removes noise while retaining the genuine signal.

**Output:** `data/experiment_threshold_sensitivity.csv` — `threshold_min`, `total_events`, `primary_pct`, `median_delay`, `mean_delay`, `dfw_risk_score`  
**Report use:** Quantitative justification for the 15-minute threshold choice.

#### Experiment 3 — Network Stability

Checks whether the top-10 airports by `prop_risk_score` are consistent across months.
Reads the 11 monthly JSONs, extracts top-10 high-volume airports (≥500 out-events)
per month, computes appearance counts and month-over-month Jaccard similarity. Mean
Jaccard ≥ 0.7 = stable metric.

**Output:** `data/experiment_network_stability.csv` — `airport`, `months_in_top10`, `stability` (High / Medium / Low)  
**Report use:** Satisfies the second success criterion — high-impact airports remain
consistent across months.

</details>

## 5. Phase 3 — D3 Visualization

`index.html` is a fully self-contained file with no build step or npm install. It loads
`network_graph.json` and `cascade_results.json` from the `data/` folder at runtime via
`fetch()`.

### 5.1 Running Locally

```bash
# From the project root (index.html and data/ must be in the same directory)
python -m http.server 8080
# or: python3 -m http.server 8080
```

Open **http://localhost:8080** in your browser. The `data/` folder must contain
`network_graph.json` and `cascade_results.json`. Opening `index.html` directly as a
`file://` URL will fail — browsers block `fetch()` on local file paths.

<details>
<summary><h3 style="display: inline;">View full interface reference →</h3></summary>

### 5.2 Interface Layout

| Area             | Description                                                                            |
| ---------------- | -------------------------------------------------------------------------------------- |
| **Top bar**      | Title, dataset date range (Jan–Nov 2025), and live counters for airports/routes/events |
| **Left sidebar** | Mode switcher, active mode controls, scrollable ranked airport list                    |
| **Map canvas**   | Albers USA projection — zoomable, pannable, fully interactive                          |
| **Detail panel** | Top-right overlay — opens on click, shows full metrics for the selected airport        |

### 5.3 View Modes

Switch between the three tabs at the top of the sidebar.

**Risk Score** — Nodes sized and colored by `prop_risk_score` (average delay severity per
propagation event). Red = high risk (score > 65), orange = medium (35–65), green = low (< 35).
Left panel shows Top 10 by risk score. Best for seeing which airports export the most
_severe_ delays.

**Volume** — Nodes sized by raw `out_events` count. Left panel shows Top 10 by event volume.
Best for seeing the highest-_frequency_ propagation sources.

**Cascade** — Animate a delay shock spreading from a seed airport. Select a seed from the
dropdown and press **Play Cascade**. The selected seed airport is immediately highlighted
with a pulsing red ring on the map. Particles travel along routes hop-by-hop from their
actual propagating source airports (not just the seed); the left panel updates in real time
with affected airports and estimated delay.

### 5.4 Interactions

| Action                               | Result                                                                                    |
| ------------------------------------ | ----------------------------------------------------------------------------------------- |
| **Hover** airport node               | Tooltip: risk score, event counts, PageRank, betweenness, coordinates                    |
| **Click** airport node               | Opens detail panel with full metrics + delay cause breakdown + outbound route highlight   |
| **Click** left panel row             | Flies map to that airport and opens its detail panel                                      |
| **Scroll** on map                    | Zoom in / out                                                                             |
| **Click and drag**                   | Pan                                                                                       |
| **+** / **−** / **⊡** (bottom-right) | Zoom in, zoom out, reset view                                                             |
| **? How to use** (bottom-left)       | Opens help overlay                                                                        |
| **Click map background**             | Dismisses detail panel, clears selection highlight                                        |
| **Click airport during cascade**     | Inspects that airport's metrics without clearing cascade results or changing the seed     |

### 5.5 Outbound Route Highlight

Clicking any airport highlights its top outbound delay routes as cyan arcs. Arc intensity
(color brightness and opacity) scales with route event count — the strongest propagation
corridors are vivid cyan, lighter routes fade toward pale blue. A cyan ring marks each
destination airport.

A **Routes slider** appears at the bottom of the detail panel when an airport is selected.
Drag it to control how many outbound routes are shown (1 to the airport's total). The map
updates in real time. Airports with only one outbound route show a quiet text note instead
of a slider.

In **Cascade mode** after a simulation has run, clicking any airport shows its outbound
connections softly overlaid on the cascade results — the cascade node colors remain visible
in the background so you can cross-reference which affected airports connect to the one
you're exploring.

### 5.6 Detail Panel

Available across all three tabs. Shows:

- Risk score, risk tier (High / Medium / Low), and expected delay
- Out-events and in-events
- Net export (positive = delay exporter, negative = absorber)
- PageRank and betweenness centrality
- Lat/lon coordinates
- **Delay cause breakdown** — proportional bar chart (Late Aircraft, NAS/ATC, Carrier,
  Weather), aggregated from all outbound edges for that airport
- **ⓘ icons** on every metric — hover to see a plain-English definition of what that
  metric means

### 5.7 Cascade Simulation Details

Select a seed airport from the dropdown — a pulsing red ring marks the seed location on
the map immediately so you can orient yourself before pressing Play. Changing the seed
resets all cascade visuals and updates the preview ring.

During playback, each hop's particles radiate from their actual source airports (the
airports in the previous wave that have a real route to each destination), not always from
the seed. This means the animation correctly shows delay spreading outward from multiple
hubs simultaneously at later hops.

Controls:

| Control        | Effect                                                   |
| -------------- | -------------------------------------------------------- |
| **Play Cascade** | Starts or stops the simulation                         |
| **Stop**       | Halts and resets node colors                             |
| **Replay**     | Resets and restarts from the same seed                   |
| **Edge Filter** slider | Sets minimum route event count for cascade eligibility — higher = fewer, stronger routes only |

The hop progress dots below the Play button show total hops; filled dots = completed,
white dot = current hop.

### 5.8 Edge Rendering

Edges are curved paths between airports. Thickness encodes `event_count` (thicker = more
frequent propagation). Color interpolates from blue (low frequency) to orange/red (high
frequency). In cascade mode, active propagation routes animate with orange cascade-edge
overlays.

When an airport is selected outside cascade mode, the base edge layer dims to 6% opacity
so the highlighted cyan outbound routes stand out clearly. In cascade mode with results
active, the base layer stays visible to preserve the cascade color context.

</details>

---

## 6. Other Notes

- **December 2025 data absent** — the BTS dataset covers January–November 2025 only.
  Label the date range accordingly in all report figures.
- **Cascade decay is linear** — the 0.5 per-hop factor is a modeling simplification;
  real attenuation varies by route, carrier, time of day, and schedule buffer.
- **Delay cause breakdown** in the detail panel aggregates across outbound edges; it
  reflects the cause mix on routes _departing_ the selected airport, not delays _arriving_
  at it.
- **Visualization requires a local server** — opening `index.html` as a `file://` URL
  fails due to browser CORS restrictions on `fetch()`. Always serve via `python -m http.server` (or `python3 -m http.server`).
- **Chain break rate** — BTS tail-number sequences contain gaps (aircraft swaps, data
  reporting gaps). These are flagged `CHAIN_BREAK=1` and excluded from propagation
  detection in Phase 2.
