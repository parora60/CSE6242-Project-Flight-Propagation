================================================================================
Flight Delay Propagation Network
Team 031 — Ayush Acharya, Fanwei Lu, Miguel A Barragan Cantor,
           Pranav Arora, Syed Muhammad Kamran Asghar
CSE6242 / CX4242 — Data and Visual Analytics, Spring 2026
================================================================================

DESCRIPTION
-----------
This package transforms ~6.3 million U.S. domestic flight records (BTS
On-Time Performance, January–November 2025) into an interactive network
visualization that reveals which airports and routes drive cascading delays
across the national air traffic system.

We reconstruct aircraft rotation chains from tail-number sequences to
identify 696,975 propagation events — instances where a delay on one flight
carries forward to the next flight operated by the same aircraft. These events
form a directed weighted graph (349 airports, 6,582 routes) enriched with
PageRank, betweenness centrality, propagation risk score, and propagation
probability, rendered as an interactive D3.js map.

The tool offers three view modes: Risk Score (node color/size encode average
propagated delay severity), Volume (raw outbound propagation count), and
Cascade (animated BFS simulation of a delay shock spreading hop-by-hop from
any selected hub). Clicking an airport opens a detail panel with all six node
metrics, a delay-cause breakdown, and adjustable route highlighting.

Key findings: DFW and LAX each reach 89 airports in 3 cascade hops; KOA
(Kona, HI) tops betweenness centrality due to its structural bottleneck role
in Hawaiian inter-island routes; summer months (June–July) produce ~50% more
propagation events than winter baselines.

INSTALLATION
------------
Requirements: Python 3.9 or higher (no other installs needed).

All Python dependencies are installed automatically when you run the execution
command below. To install them manually:

    pip install -r requirements_phase2.txt
    # or, on systems that require it:
    pip3 install -r requirements_phase2.txt

EXECUTION
---------
The simplest way to launch the full pipeline and visualization:

    python run_all.py
    # or, on systems that require it:
    python3 run_all.py

This single command will:
  1. Install all Python dependencies (requirements_phase2.txt)
  2. Run project_pipeline.ipynb to produce flights_clean.parquet
     (skipped automatically if the parquet already exists)
  3. Run phase2_propagation.py to build network_graph.json and
     cascade_results.json
  4. Run phase2_validate.py to generate validation charts
  5. Start a local HTTP server and open the visualization in your browser
     at http://localhost:8080

Additional options:

    python run_all.py --viz-only       # skip pipeline, just launch the server
                                       # (use when JSON outputs already exist)

    python run_all.py --force-phase2   # skip Phase 1 (data pipeline), re-run
                                       # Phase 2 (algorithm) + launch server

    python run_all.py --force-all      # re-run everything including Phase 1

    python run_all.py --port 9090      # use a different port

Note: The visualization must be served via HTTP — opening index.html directly
as a file:// URL will fail due to browser CORS restrictions.

DEMO VIDEO
----------
https://youtu.be/QB2HpBAaoSM

================================================================================
