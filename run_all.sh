#!/usr/bin/env bash
# ============================================================
#  Flight Delay Propagation Network — Full Pipeline Launcher
#
#  Usage:
#    bash run_all.sh                      # full run (skips Phase 1 if parquet exists)
#    bash run_all.sh --force-phase2       # skip Phase 1, re-run Phase 2 + viz
#    bash run_all.sh --force-all          # re-run everything including Phase 1
#    bash run_all.sh --viz-only           # just start the server (data already built)
#
#  Steps:
#    1. Phase 1 — run project_pipeline.ipynb → flights_clean.parquet
#    2. Phase 2 — run phase2_propagation.py  → network_graph.json, cascade_results.json
#    3. Phase 2 — run phase2_validate.py     → validation charts
#    4. Phase 3 — start python -m http.server
# ============================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────
PARQUET="./data/parquet/flights_clean.parquet"
DATA_DIR="./data"
PORT=8080
FORCE_ALL=false       # re-run Phase 1 even if parquet exists
FORCE_PHASE2=false    # skip Phase 1 but always re-run Phase 2
VIZ_ONLY=false        # skip both phases, just start the server

# ── Arg parsing ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --parquet)      PARQUET="$2";        shift 2 ;;
    --data_dir)     DATA_DIR="$2";       shift 2 ;;
    --port)         PORT="$2";           shift 2 ;;
    --force-all)    FORCE_ALL=true;      shift   ;;
    --force-phase2) FORCE_PHASE2=true;   shift   ;;
    --viz-only)     VIZ_ONLY=true;       shift   ;;
    -h|--help)
      echo "Usage: bash run_all.sh [OPTIONS]"
      echo ""
      echo "  (no flags)          Auto mode: skip Phase 1 if parquet exists, always run Phase 2"
      echo "  --force-phase2      Skip Phase 1, re-run Phase 2 pipeline + viz"
      echo "                        Use when: pipeline code changed, but raw data unchanged"
      echo "  --force-all         Re-run Phase 1 (notebook) AND Phase 2"
      echo "                        Use when: raw BTS CSV data has changed"
      echo "  --viz-only          Skip all pipeline steps, just start the HTTP server"
      echo "                        Use when: JSON outputs already exist from a prior run"
      echo ""
      echo "  --parquet PATH      Path to flights_clean.parquet  (default: $PARQUET)"
      echo "  --data_dir DIR      Output directory for JSON/CSV  (default: $DATA_DIR)"
      echo "  --port PORT         Port for the HTTP server       (default: $PORT)"
      exit 0 ;;
    *) shift ;;
  esac
done

# ── Colours ───────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }
skip()    { echo -e "${CYAN}[→]${NC} $*"; }
section() {
  echo ""
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "    $*"
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── Print run mode summary ────────────────────────────────
echo ""
echo -e "${CYAN}Flight Delay Propagation Network — Pipeline Launcher${NC}"
echo -e "  Parquet : $PARQUET"
echo -e "  Data dir: $DATA_DIR"
echo -e "  Port    : $PORT"
if   [[ "$VIZ_ONLY"    == true ]]; then echo -e "  Mode    : ${YELLOW}viz-only${NC} (skip all pipeline steps)"
elif [[ "$FORCE_ALL"   == true ]]; then echo -e "  Mode    : ${YELLOW}force-all${NC} (re-run Phase 1 + Phase 2)"
elif [[ "$FORCE_PHASE2" == true ]]; then echo -e "  Mode    : ${YELLOW}force-phase2${NC} (skip Phase 1, re-run Phase 2)"
else                                     echo -e "  Mode    : ${GREEN}auto${NC} (skip Phase 1 if parquet exists)"
fi

# ── EARLY EXIT: viz-only ─────────────────────────────────
if [[ "$VIZ_ONLY" == true ]]; then
  [[ -f "$DATA_DIR/network_graph.json"   ]] || error "network_graph.json missing — run without --viz-only first"
  [[ -f "$DATA_DIR/cascade_results.json" ]] || error "cascade_results.json missing — run without --viz-only first"
  [[ -f "index.html" ]]                    || error "index.html not found in current directory"
  section "🌐  Phase 3 — Starting Visualization Server"
  echo -e "  ${GREEN}Server starting …${NC}"
  echo -e "  Open: ${YELLOW}http://localhost:${PORT}${NC}"
  echo "  Press Ctrl+C to stop."
  echo ""
  python3 -m http.server "$PORT"
  exit 0
fi

# ── Dependency check ──────────────────────────────────────
section "🔍  Checking dependencies"
command -v python3 &>/dev/null || error "python3 not found. Install Python 3.9+."
command -v pip    &>/dev/null  || error "pip not found."
info "Python: $(python3 --version)"

if [[ -f requirements_phase2.txt ]]; then
  info "Installing Phase 2 requirements …"
  pip install -q -r requirements_phase2.txt
else
  warn "requirements_phase2.txt not found — skipping pip install"
fi

# nbconvert needed only if we might run Phase 1
RUN_PHASE1=false
if [[ "$FORCE_ALL" == true ]]; then
  RUN_PHASE1=true
elif [[ "$FORCE_PHASE2" == false && ! -f "$PARQUET" ]]; then
  RUN_PHASE1=true   # auto mode: parquet missing, must build it
fi

if [[ "$RUN_PHASE1" == true ]]; then
  if ! python3 -c "import nbconvert" &>/dev/null; then
    warn "nbconvert not found — installing …"
    pip install -q nbconvert
  fi
fi

# ── PHASE 1 — Notebook ────────────────────────────────────
section "📓  Phase 1 — Data Pipeline (project_pipeline.ipynb)"

if [[ "$RUN_PHASE1" == false ]]; then
  if [[ "$FORCE_PHASE2" == true ]]; then
    skip "Skipping Phase 1 (--force-phase2 set, reusing existing parquet)"
  elif [[ -f "$PARQUET" ]]; then
    skip "Parquet already exists — skipping Phase 1"
    skip "To rebuild the parquet from raw CSVs, use --force-all"
  fi
else
  # Running Phase 1
  if [[ "$FORCE_ALL" == true && -f "$PARQUET" ]]; then
    warn "--force-all: deleting existing parquet and rebuilding from source CSVs …"
    rm -f "$PARQUET"
  fi
  [[ -f "project_pipeline.ipynb" ]] || error "project_pipeline.ipynb not found. Cannot build parquet."
  info "Running project_pipeline.ipynb via nbconvert …"
  python3 -m nbconvert --to notebook --execute project_pipeline.ipynb \
    --output project_pipeline_executed.ipynb \
    --ExecutePreprocessor.timeout=3600
  info "Notebook executed → project_pipeline_executed.ipynb"
fi

# Gate: parquet must exist before Phase 2
[[ -f "$PARQUET" ]] || error "Parquet not found at $PARQUET — check Phase 1 output or provide --parquet PATH"

# ── PHASE 2 — Propagation pipeline ───────────────────────
section "⚙️   Phase 2 — Propagation Pipeline (phase2_propagation.py)"
[[ -f "phase2_propagation.py" ]] || error "phase2_propagation.py not found in current directory."

if [[ "$FORCE_PHASE2" == true || "$FORCE_ALL" == true ]]; then
  warn "Clearing previous Phase 2 outputs before rebuild …"
  rm -f  "$DATA_DIR/network_graph.json" \
         "$DATA_DIR/cascade_results.json" \
         "$DATA_DIR/propagation_events.csv"
  rm -rf "$DATA_DIR/monthly_graphs"
fi

python3 phase2_propagation.py --parquet "$PARQUET" --output "$DATA_DIR"
info "Phase 2 pipeline complete"

# ── PHASE 2 — Validation ─────────────────────────────────
section "🔬  Phase 2 — Validation & Charts (phase2_validate.py)"
if [[ -f "phase2_validate.py" ]]; then
  python3 phase2_validate.py --data_dir "$DATA_DIR"
  info "Validation complete — charts saved to $DATA_DIR/validation_charts/"
else
  warn "phase2_validate.py not found — skipping validation"
fi

# ── PHASE 3 — Visualization server ───────────────────────
section "🌐  Phase 3 — Starting Visualization Server"

[[ -f "$DATA_DIR/network_graph.json"   ]] || error "network_graph.json missing in $DATA_DIR"
[[ -f "$DATA_DIR/cascade_results.json" ]] || error "cascade_results.json missing in $DATA_DIR"
[[ -f "index.html" ]] || error "index.html not found in current directory"

echo ""
echo -e "  ${GREEN}All pipeline steps complete!${NC}"
echo ""
echo -e "  Open your browser to:  ${YELLOW}http://localhost:${PORT}${NC}"
echo "  Press Ctrl+C to stop the server."
echo ""
python3 -m http.server "$PORT"
