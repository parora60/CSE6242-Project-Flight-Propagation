"""
Phase 2 – Validation & Diagnostics
====================================
Run AFTER phase2_propagation.py to verify outputs and generate
summary charts for the mid-point report.

Usage:
    python phase2_validate.py
    python phase2_validate.py --data_dir path/to/data
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def check_exists(path: str, label: str) -> bool:
    ok = Path(path).exists()
    status = "✓" if ok else "✗  MISSING"
    print(f"  [{status}]  {label:45s}  {path}")
    return ok


# ─────────────────────────────────────────────
# CHECK 1 – File existence
# ─────────────────────────────────────────────

def check_files(data_dir: str):
    print("\n[CHECK 1] Output files present")
    print("-" * 70)
    all_ok = True
    all_ok &= check_exists(f"{data_dir}/network_graph.json",      "Full-year network graph")
    all_ok &= check_exists(f"{data_dir}/cascade_results.json",    "Cascade simulation results")
    all_ok &= check_exists(f"{data_dir}/propagation_events.csv",  "Raw propagation events")

    monthly_dir = Path(f"{data_dir}/monthly_graphs")
    if monthly_dir.exists():
        months = sorted(monthly_dir.glob("network_month_*.json"))
        print(f"  [{'✓' if months else '✗'}]  Monthly graphs: {len(months)} files found")
    else:
        print("  [✗]  monthly_graphs/ directory missing")
        all_ok = False

    if all_ok:
        print("  → All required files present ✓")
    else:
        print("  → ⚠  Some files missing – re-run phase2_propagation.py")
    return all_ok


# ─────────────────────────────────────────────
# CHECK 2 – Network structure
# ─────────────────────────────────────────────

def check_network_structure(data_dir: str):
    print("\n[CHECK 2] Network structure")
    print("-" * 70)
    g = load_json(f"{data_dir}/network_graph.json")

    nodes = g["nodes"]
    links = g["links"]

    print(f"  Nodes (airports)  : {len(nodes)}")
    print(f"  Edges (routes)    : {len(links)}")

    # Check all link sources/targets exist as nodes
    node_ids = {n["id"] for n in nodes}
    broken = [(l["source"], l["target"]) for l in links
              if l["source"] not in node_ids or l["target"] not in node_ids]
    if broken:
        print(f"  ⚠  {len(broken)} edges reference unknown nodes: {broken[:5]}")
    else:
        print("  ✓ All edge endpoints have matching nodes")

    # Check geo coverage
    with_coords = sum(1 for n in nodes if n.get("lat") is not None)
    print(f"  Nodes with lat/lon : {with_coords}/{len(nodes)} ({100*with_coords/len(nodes):.0f}%)")

    # Degree stats
    out_events = [n["out_events"] for n in nodes]
    in_events  = [n["in_events"]  for n in nodes]
    print(f"  Out-events range   : {min(out_events)} – {max(out_events):,}  "
          f"(mean {np.mean(out_events):.0f})")
    print(f"  In-events range    : {min(in_events)} – {max(in_events):,}  "
          f"(mean {np.mean(in_events):.0f})")

    # Top 10 by risk score
    top = sorted(nodes, key=lambda n: n["prop_risk_score"], reverse=True)[:10]
    print("\n  Top 10 airports by Propagation Risk Score:")
    print(f"  {'IATA':<6} {'City':<20} {'RiskScore':>10} {'OutEvents':>10} "
          f"{'BetweenC':>10} {'PageRank':>10}")
    print("  " + "-" * 70)
    for n in top:
        print(f"  {n['id']:<6} {n['city']:<20} {n['prop_risk_score']:>10.1f} "
              f"{n['out_events']:>10,} {n['betweenness']:>10.4f} {n['pagerank']:>10.4f}")


# ─────────────────────────────────────────────
# CHECK 3 – Propagation events audit
# ─────────────────────────────────────────────

def check_events(data_dir: str):
    print("\n[CHECK 3] Propagation events audit")
    print("-" * 70)
    path = f"{data_dir}/propagation_events.csv"
    if not Path(path).exists():
        print("  ⚠  File missing – skipping")
        return

    ev = pd.read_csv(path, nrows=500_000)   # sample for speed
    print(f"  Rows loaded (sample) : {len(ev):,}")

    if "prop_delay_min" in ev.columns:
        print(f"  prop_delay_min stats : "
              f"min={ev['prop_delay_min'].min():.0f}  "
              f"median={ev['prop_delay_min'].median():.0f}  "
              f"mean={ev['prop_delay_min'].mean():.0f}  "
              f"max={ev['prop_delay_min'].max():.0f}  min")

    if "is_primary" in ev.columns:
        pct = 100 * ev["is_primary"].mean()
        print(f"  Primary (LateAC)     : {pct:.0f}%  "
              f"| Secondary (turnaround): {100-pct:.0f}%")

    if "dominant_cause" in ev.columns:
        print("\n  Dominant cause breakdown:")
        cause_counts = ev["dominant_cause"].value_counts(normalize=True) * 100
        for cause, pct in cause_counts.items():
            print(f"    {cause:<25} {pct:>5.1f}%")

    if "MONTH" in ev.columns:
        print("\n  Events by month:")
        monthly = ev.groupby("MONTH").size()
        for m, cnt in monthly.items():
            bar = "█" * int(cnt / monthly.max() * 30)
            print(f"    Month {int(m):02d}:  {cnt:>8,}  {bar}")


# ─────────────────────────────────────────────
# CHECK 4 – Cascade sanity
# ─────────────────────────────────────────────

def check_cascades(data_dir: str):
    print("\n[CHECK 4] Cascade simulation sanity")
    print("-" * 70)
    path = f"{data_dir}/cascade_results.json"
    if not Path(path).exists():
        print("  ⚠  File missing – skipping")
        return

    cascades = load_json(path)
    print(f"  Seeds simulated : {len(cascades)}")

    for seed, steps in list(cascades.items())[:5]:
        depths = len(steps)
        if steps:
            final_airports = steps[-1]["total_airports"]
            final_delay    = steps[-1]["total_delay"]
        else:
            final_airports, final_delay = 0, 0
        print(f"  {seed}: depth={depths} hops, "
              f"final_airports={final_airports}, "
              f"total_delay_at_final_hop={final_delay:.0f} min")


# ─────────────────────────────────────────────
# CHART 1 – Top airports bar chart
# ─────────────────────────────────────────────

def plot_top_airports(data_dir: str, out_dir: str):
    g = load_json(f"{data_dir}/network_graph.json")
    nodes = pd.DataFrame(g["nodes"])
    top = nodes.nlargest(20, "out_events")

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Top 20 Airports – Propagation Metrics", fontsize=14, fontweight="bold")

    metrics = [
        ("out_events",      "Out-Events (Delay Export Count)",   "#E63946"),
        ("prop_risk_score", "Propagation Risk Score (avg min)",  "#2A9D8F"),
        ("betweenness",     "Betweenness Centrality",            "#457B9D"),
    ]
    for ax, (col, title, color) in zip(axes, metrics):
        sub = nodes.nlargest(20, col)
        ax.barh(sub["id"], sub[col], color=color, alpha=0.85)
        ax.set_xlabel(title)
        ax.set_title(title)
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    path = f"{out_dir}/phase2_top_airports.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  ✓ Chart saved → {path}")


# ─────────────────────────────────────────────
# CHART 2 – Monthly event counts
# ─────────────────────────────────────────────

def plot_monthly_trends(data_dir: str, out_dir: str):
    monthly_dir = Path(f"{data_dir}/monthly_graphs")
    if not monthly_dir.exists():
        return

    month_data = []
    for path in sorted(monthly_dir.glob("network_month_*.json")):
        g = load_json(str(path))
        month = g.get("month")
        total_events = sum(l["event_count"] for l in g["links"])
        total_delay  = sum(l["total_delay"]  for l in g["links"])
        month_data.append({"month": month,
                           "total_events": total_events,
                           "total_delay": total_delay,
                           "n_edges": len(g["links"])})

    if not month_data:
        return

    df = pd.DataFrame(month_data).sort_values("month")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax2 = ax1.twinx()

    x = range(len(df))
    ax1.bar(x, df["total_events"], color="#E63946", alpha=0.7, label="Propagation Events")
    ax2.plot(x, df["total_delay"] / 1000, color="#457B9D", marker="o",
             linewidth=2, label="Total Delay (k min)")

    ax1.set_xticks(list(x))
    ax1.set_xticklabels([month_names[m - 1] for m in df["month"]])
    ax1.set_xlabel("Month (2025)")
    ax1.set_ylabel("# Propagation Events", color="#E63946")
    ax2.set_ylabel("Total Propagated Delay (thousands of min)", color="#457B9D")
    ax1.set_title("Monthly Propagation Activity", fontsize=13, fontweight="bold")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    path = f"{out_dir}/phase2_monthly_trends.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Chart saved → {path}")


# ─────────────────────────────────────────────
# CHART 3 – Cascade depth comparison
# ─────────────────────────────────────────────

def plot_cascade_depth(data_dir: str, out_dir: str):
    path = f"{data_dir}/cascade_results.json"
    if not Path(path).exists():
        return

    cascades = load_json(path)
    seeds, max_depths, final_airports = [], [], []
    for seed, steps in cascades.items():
        seeds.append(seed)
        max_depths.append(len(steps))
        final_airports.append(steps[-1]["total_airports"] if steps else 0)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Cascade Simulation Summary", fontsize=13, fontweight="bold")

    axes[0].bar(seeds, max_depths, color="#F4A261", edgecolor="white")
    axes[0].set_xlabel("Seed Airport")
    axes[0].set_ylabel("Cascade Depth (hops)")
    axes[0].set_title("Cascade Depth by Seed")
    axes[0].tick_params(axis="x", rotation=45)

    axes[1].bar(seeds, final_airports, color="#2A9D8F", edgecolor="white")
    axes[1].set_xlabel("Seed Airport")
    axes[1].set_ylabel("Airports Reached")
    axes[1].set_title("Total Airports Reached by Cascade")
    axes[1].tick_params(axis="x", rotation=45)

    plt.tight_layout()
    chart_path = f"{out_dir}/phase2_cascade_summary.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Chart saved → {chart_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main(data_dir: str):
    out_dir = f"{data_dir}/validation_charts"
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    files_ok = check_files(data_dir)
    if not files_ok:
        print("\n⚠  Cannot run further checks – fix missing files first.")
        return

    check_network_structure(data_dir)
    check_events(data_dir)
    check_cascades(data_dir)

    print("\n[CHARTS] Generating validation charts …")
    plot_top_airports(data_dir, out_dir)
    plot_monthly_trends(data_dir, out_dir)
    plot_cascade_depth(data_dir, out_dir)

    print(f"\n{'='*60}")
    print("Phase 2 validation complete.")
    print(f"Charts saved in: {out_dir}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 Validation")
    parser.add_argument("--data_dir", default="data",
                        help="Directory containing Phase 2 JSON outputs")
    args = parser.parse_args()
    main(args.data_dir)
