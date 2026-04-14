================================================================================
Flight Delay Propagation Network
Team 031 — Ayush Acharya, Fanwei Lu, Miguel A Barragan Cantor,
           Pranav Arora, Syed Muhammad Kamran Asghar
CSE6242 / CX4242 — Data and Visual Analytics, Spring 2026
================================================================================

DESCRIPTION
-----------
This package converts approximately 6.3 million U.S. domestic flight records
(BTS On-Time Performance data, January–November 2025) into an interactive
network visualization that reveals which airports and routes drive cascading
delays across the national flight network.

Instead of treating delays as isolated events, we reconstruct aircraft rotation
chains from tail-number sequences to directly observe 696,975 propagation
events — instances where a delay on one flight carries forward to the next
flight on the same aircraft. These events are modeled as a directed weighted
graph (349 airports, 6,582 routes), enriched with network centrality metrics
(PageRank, betweenness centrality, propagation risk score, propagation
probability), and rendered in an interactive D3.js map visualization.

The tool has three main view modes:
  - Risk Score mode: node color and size encode average propagated delay
    severity per event (prop_risk_score)
  - Volume mode: node size encodes raw count of outbound propagation events
  - Cascade mode: animated BFS simulation of a delay shock spreading from a
    selected hub airport, hop by hop across the network

Clicking any airport opens a detail panel with all six node metrics, a delay
cause breakdown (Late Aircraft / NAS-ATC / Carrier / Weather), outbound route
highlighting, and an adjustable routes slider.

Key findings: DFW and LAX each reach 89 airports in 3 cascade hops; KOA (Kona,
HI) tops betweenness centrality despite low event volume due to its structural
bottleneck role in Hawaiian inter-island routes; summer months (June–July) drive
~50% more propagation events than winter baselines.

The pipeline runs in three phases:
  Phase 1 — Data ingestion and cleaning  (project_pipeline.ipynb)
  Phase 2 — Propagation model and experiments  (phase2_propagation.py,
             phase2_validate.py, phase2_experiments.py)
  Phase 3 — Interactive D3 visualization  (index.html)

INSTALLATION
------------
Requirements:
  - Python 3.9 or higher
  - pip

Install Python dependencies:

    pip install -r requirements_phase2.txt

The visualization (Phase 3) requires only a local HTTP server — no additional
install needed. All D3.js dependencies are loaded from a CDN.

To run Phase 1 (notebook), nbconvert is also needed:

    pip install nbconvert

EXECUTION
---------
The fastest way to view the visualization (all pre-built outputs are included):

    python -m http.server 8080
    # Then open: http://localhost:8080

NOTE: The visualization must be served via a local HTTP server. Opening
index.html directly as a file:// URL will fail due to browser CORS
restrictions on fetch() calls.

--- Full pipeline options ---

Option A — Run the full pipeline from scratch:

    bash run_all.sh

This script will:
  1. Install all Python dependencies
  2. Execute project_pipeline.ipynb to produce flights_clean.parquet
  3. Run phase2_propagation.py to build network_graph.json and
     cascade_results.json
  4. Run phase2_validate.py to generate validation charts
  5. Start the visualization server at http://localhost:8080

Option B — Skip to visualization (JSON outputs already included):

    bash run_all.sh --viz-only

Option C — Re-run Phase 2 only (pipeline code changed, raw data unchanged):

    bash run_all.sh --force-phase2

Option D — Run phases manually:

    # Phase 2 only (assumes parquet already exists)
    pip install -r requirements_phase2.txt
    python phase2_propagation.py --parquet ./data/parquet/flights_clean.parquet

    # Validation charts
    python phase2_validate.py

    # Experiment charts (generates experiment1/2/3 PNG files in data/validation_charts/)
    python phase2_experiments.py --parquet ./data/parquet/flights_clean.parquet

DATA
----
The raw BTS On-Time Performance CSV files for January–November 2025 are
included in data/csv/. No additional download is required to run the full
pipeline. If you need to re-download them, monthly files are available at:

    https://www.transtats.bts.gov/DL_SelectFields.aspx

Select "Reporting Carrier On-Time Performance" and download one CSV per month.

The pre-built JSON outputs (network_graph.json, cascade_results.json) needed
to run the visualization are included in data/ and work immediately with the
--viz-only option or by starting the HTTP server directly.

DEMO VIDEO
----------
[Optional — include YouTube URL here if recorded]

================================================================================
