#!/usr/bin/env python3
"""
Flight Delay Propagation Network — Cross-Platform Pipeline Launcher
====================================================================
Works on Windows, macOS, and Linux. Requires only Python 3.9+.

Usage:
    python run_all.py                  # full run (skips Phase 1 if parquet exists)
    python run_all.py --force-phase2   # skip Phase 1, re-run Phase 2 + start server
    python run_all.py --force-all      # re-run everything including Phase 1
    python run_all.py --viz-only       # just start the server (data already built)
    python run_all.py --port 9090      # use a custom port (default: 8080)
"""

import argparse
import http.server
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path


# ── Colour helpers (skipped on Windows if not supported) ─────────────────────
def _supports_color():
    return sys.platform != "win32" or "ANSICON" in os.environ

GREEN  = "\033[0;32m"  if _supports_color() else ""
YELLOW = "\033[1;33m"  if _supports_color() else ""
RED    = "\033[0;31m"  if _supports_color() else ""
CYAN   = "\033[0;36m"  if _supports_color() else ""
NC     = "\033[0m"     if _supports_color() else ""

def info(msg):    print(f"{GREEN}[✓]{NC} {msg}")
def warn(msg):    print(f"{YELLOW}[!]{NC} {msg}")
def skip(msg):    print(f"{CYAN}[→]{NC} {msg}")
def section(msg): print(f"\n{'━'*60}\n    {msg}\n{'━'*60}")
def error(msg):
    print(f"{RED}[✗]{NC} {msg}")
    sys.exit(1)


# ── Install pip requirements ──────────────────────────────────────────────────
def pip_install(req_file: Path):
    info(f"Installing requirements from {req_file} …")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
        capture_output=False,
    )
    if result.returncode != 0:
        error("pip install failed. Check your Python environment and try again.")
    info("All requirements installed.")


# ── Run a Python script as a subprocess ──────────────────────────────────────
def run_script(script: Path, extra_args: list = None):
    cmd = [sys.executable, str(script)] + (extra_args or [])
    info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        error(f"{script.name} exited with code {result.returncode}.")


# ── Execute the Phase 1 Jupyter notebook via nbconvert ───────────────────────
def run_notebook(notebook: Path):
    # Ensure nbconvert + ipykernel are available
    for pkg in ("nbconvert", "ipykernel"):
        r = subprocess.run(
            [sys.executable, "-c", f"import {pkg}"],
            capture_output=True,
        )
        if r.returncode != 0:
            warn(f"{pkg} not found — installing …")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", pkg],
                check=True,
            )

    executed_nb = notebook.with_name("project_pipeline_executed.ipynb")
    cmd = [
        sys.executable, "-m", "nbconvert",
        "--to", "notebook",
        "--execute", str(notebook),
        "--output", str(executed_nb),
        "--ExecutePreprocessor.timeout=3600",
        # Force a fresh kernel so there are no stale-state issues
        "--ExecutePreprocessor.kernel_name=python3",
    ]
    info(f"Executing notebook (this may take several minutes) …")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        error("Notebook execution failed. Check project_pipeline_executed.ipynb for traceback.")
    info(f"Notebook executed → {executed_nb.name}")


# ── Simple HTTP server (serves current directory) ────────────────────────────
def start_server(port: int):
    handler = http.server.SimpleHTTPRequestHandler

    # Suppress the default per-request log spam
    class QuietHandler(handler):
        def log_message(self, fmt, *args):
            pass

    server = http.server.HTTPServer(("", port), QuietHandler)

    url = f"http://localhost:{port}"
    print()
    print(f"  {GREEN}Visualization server running at:{NC}")
    print(f"  {YELLOW}{url}{NC}")
    print("  Press Ctrl+C to stop.\n")

    # Try to open the browser automatically
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Flight Delay Propagation Network — cross-platform pipeline launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  (no flags)          Auto: skip Phase 1 if parquet exists, always run Phase 2
  --force-phase2      Skip Phase 1, re-run Phase 2 pipeline then start server
  --force-all         Re-run Phase 1 (notebook) AND Phase 2
  --viz-only          Skip all pipeline steps, just start the HTTP server
        """,
    )
    parser.add_argument("--parquet",      default="./data/parquet/flights_clean.parquet")
    parser.add_argument("--data_dir",     default="./data")
    parser.add_argument("--port",         type=int, default=8080)
    parser.add_argument("--force-all",    action="store_true")
    parser.add_argument("--force-phase2", action="store_true")
    parser.add_argument("--viz-only",     action="store_true")
    args = parser.parse_args()

    parquet  = Path(args.parquet)
    data_dir = Path(args.data_dir)
    port     = args.port

    print(f"\n{CYAN}Flight Delay Propagation Network — Pipeline Launcher{NC}")
    print(f"  Python  : {sys.version.split()[0]}")
    print(f"  Parquet : {parquet}")
    print(f"  Data dir: {data_dir}")
    print(f"  Port    : {port}")
    if args.viz_only:
        print(f"  Mode    : {YELLOW}viz-only{NC}")
    elif args.force_all:
        print(f"  Mode    : {YELLOW}force-all{NC}")
    elif args.force_phase2:
        print(f"  Mode    : {YELLOW}force-phase2{NC}")
    else:
        print(f"  Mode    : {GREEN}auto{NC}")

    # ── viz-only shortcut ────────────────────────────────────────────────────
    if args.viz_only:
        for f, label in [
            (data_dir / "network_graph.json",   "network_graph.json"),
            (data_dir / "cascade_results.json", "cascade_results.json"),
            (Path("index.html"),                "index.html"),
        ]:
            if not f.exists():
                error(f"{label} not found — run without --viz-only first.")
        section("Phase 3 — Starting Visualization Server")
        start_server(port)
        return

    # ── install Python requirements ──────────────────────────────────────────
    section("Step 1 — Installing Python Requirements")
    req_file = Path("requirements_phase2.txt")
    if req_file.exists():
        pip_install(req_file)
    else:
        warn("requirements_phase2.txt not found — skipping pip install")

    # ── Phase 1 decision ─────────────────────────────────────────────────────
    run_phase1 = False
    if args.force_all:
        run_phase1 = True
    elif not args.force_phase2 and not parquet.exists():
        run_phase1 = True   # auto mode: parquet missing

    section("Step 2 — Phase 1: Data Pipeline (project_pipeline.ipynb)")
    if run_phase1:
        if args.force_all and parquet.exists():
            warn("--force-all: removing existing parquet to rebuild from source CSVs …")
            parquet.unlink()
        nb = Path("project_pipeline.ipynb")
        if not nb.exists():
            error("project_pipeline.ipynb not found. Cannot build parquet.")
        run_notebook(nb)
    else:
        if args.force_phase2:
            skip("Skipping Phase 1 (--force-phase2 set, reusing existing parquet)")
        elif parquet.exists():
            skip("Parquet already exists — skipping Phase 1")
            skip("Use --force-all to rebuild from raw CSVs")

    if not parquet.exists():
        error(f"Parquet not found at {parquet} — check Phase 1 output or use --parquet PATH")

    # ── Phase 2 — propagation pipeline ──────────────────────────────────────
    section("Step 3 — Phase 2: Propagation Pipeline (phase2_propagation.py)")
    prop_script = Path("phase2_propagation.py")
    if not prop_script.exists():
        error("phase2_propagation.py not found.")

    if args.force_phase2 or args.force_all:
        warn("Clearing previous Phase 2 outputs before rebuild …")
        for f in ["network_graph.json", "cascade_results.json", "propagation_events.csv"]:
            p = data_dir / f
            if p.exists():
                p.unlink()
        monthly = data_dir / "monthly_graphs"
        if monthly.exists():
            shutil.rmtree(monthly)

    run_script(prop_script, ["--parquet", str(parquet), "--output", str(data_dir)])
    info("Phase 2 pipeline complete")

    # ── Phase 2 — validation ─────────────────────────────────────────────────
    section("Step 4 — Phase 2: Validation & Charts (phase2_validate.py)")
    val_script = Path("phase2_validate.py")
    if val_script.exists():
        run_script(val_script, ["--data_dir", str(data_dir)])
        info(f"Validation complete — charts saved to {data_dir}/validation_charts/")
    else:
        warn("phase2_validate.py not found — skipping validation")

    # ── Phase 3 — visualization server ───────────────────────────────────────
    section("Step 5 — Phase 3: Visualization Server")
    for f, label in [
        (data_dir / "network_graph.json",   "network_graph.json"),
        (data_dir / "cascade_results.json", "cascade_results.json"),
        (Path("index.html"),                "index.html"),
    ]:
        if not f.exists():
            error(f"{label} missing — check pipeline outputs.")

    info("All pipeline steps complete!")
    start_server(port)


if __name__ == "__main__":
    main()
