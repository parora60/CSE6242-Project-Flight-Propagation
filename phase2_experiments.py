"""
Phase 2 - Scalability & Sensitivity Experiments
================================================
Run AFTER phase2_propagation.py has been run at least once.
This file does NOT modify the main pipeline or output files.

Usage:
    python phase2_experiments.py --parquet ./data/parquet/flights_clean.parquet --data_dir data
"""

import argparse
import time
import json
import pandas as pd
import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# Import directly from the main pipeline — no duplication
from phase2_propagation import (
    load_flights,
    reconstruct_rotations,
    detect_propagation_events,
    load_airport_meta,
    build_network,
    PROP_THRESHOLD_MIN,
)


# ─────────────────────────────────────────────
# EXPERIMENT 1 — Scalability
# ─────────────────────────────────────────────

def experiment_scalability(events: pd.DataFrame, meta: pd.DataFrame):
    """
    Measures build_network() runtime as dataset size increases.
    Uses already-computed events filtered by month count — no re-running
    the full pipeline, no changes to main code.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 1 — Scalability (runtime vs dataset size)")
    print("=" * 60)
    print(f"  {'Months':<10} {'Events':>12} {'Nodes':>8} {'Edges':>8} {'Time (s)':>10}")
    print("  " + "-" * 52)

    results = []
    for n_months in [1, 2, 3, 6, 9, 11]:
        subset = events[events["MONTH"] <= n_months]
        start = time.time()
        g = build_network(subset, meta, month=None)
        elapsed = time.time() - start
        results.append({
            "months": n_months,
            "events": len(subset),
            "nodes": len(g["nodes"]),
            "edges": len(g["links"]),
            "time_s": round(elapsed, 2),
        })
        print(f"  {n_months:<10} {len(subset):>12,} {len(g['nodes']):>8} "
              f"{len(g['links']):>8} {elapsed:>10.2f}s")

    # Save results
    df = pd.DataFrame(results)
    df.to_csv("data/experiment_scalability.csv", index=False)
    print(f"\n  ✓ Results saved → data/experiment_scalability.csv")
    return df


# ─────────────────────────────────────────────
# EXPERIMENT 2 — Threshold Sensitivity
# ─────────────────────────────────────────────

def experiment_threshold_sensitivity(pairs: pd.DataFrame, meta: pd.DataFrame):
    """
    Runs propagation detection and network build at three thresholds
    (1, 15, 30 min) to show 15 min is the stable, principled choice.
    Does NOT touch the main pipeline config — uses local overrides.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 2 — Threshold Sensitivity")
    print("=" * 60)
    print(f"  {'Threshold':<12} {'Events':>10} {'Primary%':>10} "
          f"{'Median':>8} {'Mean':>8} {'DFW Score':>12}")
    print("  " + "-" * 64)

    results = []
    for threshold in [1, 15, 30]:
        # Temporarily override thresholds without touching the config
        import phase2_propagation as p2
        orig_prop = p2.PROP_THRESHOLD_MIN
        orig_late = p2.LATE_AC_THRESHOLD_MIN
        p2.PROP_THRESHOLD_MIN = threshold
        p2.LATE_AC_THRESHOLD_MIN = threshold

        events = detect_propagation_events(pairs)

        # Restore originals immediately
        p2.PROP_THRESHOLD_MIN = orig_prop
        p2.LATE_AC_THRESHOLD_MIN = orig_late

        primary_pct = 100 * events["is_primary"].mean()
        median_delay = events["prop_delay_min"].median()
        mean_delay = events["prop_delay_min"].mean()

        # Get DFW risk score from network
        g = build_network(events, meta, month=None)
        dfw_node = next((n for n in g["nodes"] if n["id"] == "DFW"), None)
        dfw_score = dfw_node["prop_risk_score"] if dfw_node else 0

        results.append({
            "threshold_min": threshold,
            "total_events": len(events),
            "primary_pct": round(primary_pct, 1),
            "median_delay": round(median_delay, 1),
            "mean_delay": round(mean_delay, 1),
            "dfw_risk_score": round(dfw_score, 1),
        })
        print(f"  {threshold:<12} {len(events):>10,} {primary_pct:>9.1f}% "
              f"{median_delay:>8.1f} {mean_delay:>8.1f} {dfw_score:>12.1f}")

    df = pd.DataFrame(results)
    df.to_csv("data/experiment_threshold_sensitivity.csv", index=False)
    print(f"\n  ✓ Results saved → data/experiment_threshold_sensitivity.csv")
    return df


# ─────────────────────────────────────────────
# EXPERIMENT 3 — Network Stability Across Months
# ─────────────────────────────────────────────

def experiment_network_stability(data_dir: str):
    """
    Checks whether top-10 airports by prop_risk_score are consistent
    across months. High overlap = stable, reliable metric.
    Reads already-generated monthly JSONs — no recomputation needed.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 3 — Network Stability (top airports across months)")
    print("=" * 60)

    monthly_dir = Path(f"{data_dir}/monthly_graphs")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov"]

    top_per_month = {}
    for path in sorted(monthly_dir.glob("network_month_*.json")):
        with open(path) as f:
            g = json.load(f)
        month = g["month"]
        # Top 10 by prop_risk_score, min 500 out_events for the month
        top = sorted(
            [n for n in g["nodes"] if n["out_events"] >= 500],
            key=lambda n: n["prop_risk_score"],
            reverse=True
        )[:10]
        top_per_month[month] = {n["id"] for n in top}

    # Count how many months each airport appears in the top 10
    all_airports = set()
    for s in top_per_month.values():
        all_airports |= s

    appearance_counts = {
        ap: sum(1 for s in top_per_month.values() if ap in s)
        for ap in all_airports
    }

    # Print ranked by appearance count
    ranked = sorted(appearance_counts.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  {'Airport':<8} {'Months in Top 10':>18} {'Stability':>12}")
    print("  " + "-" * 42)
    for ap, count in ranked[:15]:
        bar = "█" * count
        stability = "High" if count >= 9 else "Medium" if count >= 6 else "Low"
        print(f"  {ap:<8} {count:>12}/11         {stability:>8}  {bar}")

    # Jaccard similarity between consecutive months (https://www.ibm.com/think/topics/jaccard-similarity)
    print(f"\n  Month-to-month Jaccard similarity (top-10 overlap):")
    months = sorted(top_per_month.keys())
    similarities = []
    for i in range(len(months) - 1):
        a = top_per_month[months[i]]
        b = top_per_month[months[i+1]]
        jaccard = len(a & b) / len(a | b)
        similarities.append(jaccard)
        m1 = month_names[months[i]-1]
        m2 = month_names[months[i+1]-1]
        print(f"    {m1}→{m2}: {jaccard:.2f}  {'█' * int(jaccard * 20)}")

    print(f"\n  Mean Jaccard similarity: {np.mean(similarities):.2f}  "
          f"(1.0 = identical, 0.0 = no overlap)")

    # Save
    results = [{"airport": ap, "months_in_top10": cnt,
                "stability": "High" if cnt >= 9 else "Medium" if cnt >= 6 else "Low"}
               for ap, cnt in ranked]
    pd.DataFrame(results).to_csv("data/experiment_network_stability.csv", index=False)
    print(f"\n  ✓ Results saved → data/experiment_network_stability.csv")


# ─────────────────────────────────────────────
# CHART GENERATION
# ─────────────────────────────────────────────

CHART_STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": "#f8f9fa",
    "axes.edgecolor": "#cccccc",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#e0e0e0",
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
}


def plot_experiment_scalability(data_dir: str, out_dir: str):
    """Chart for Experiment 1: runtime and edge count vs. months of data."""
    path = Path(f"{data_dir}/experiment_scalability.csv")
    if not path.exists():
        print(f"  ⚠  {path} not found — skipping scalability chart")
        return

    df = pd.read_csv(path)
    with plt.rc_context(CHART_STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        fig.suptitle(
            "Experiment 1 — Pipeline Scalability",
            fontsize=14, fontweight="bold", y=1.01
        )

        # Left: runtime vs. events
        ax = axes[0]
        ax.plot(df["events"] / 1_000, df["time_s"], color="#E63946",
                marker="o", linewidth=2, markersize=7)
        for _, row in df.iterrows():
            ax.annotate(f"{int(row['months'])}mo",
                        (row["events"] / 1_000, row["time_s"]),
                        textcoords="offset points", xytext=(6, 4),
                        fontsize=9, color="#555555")
        ax.set_xlabel("Propagation Events (thousands)")
        ax.set_ylabel("Build Time (seconds)")
        ax.set_title("Build Time vs. Dataset Size")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x:.0f}K"))

        # Right: edge count vs. months
        ax2 = axes[1]
        color_edges = "#457B9D"
        color_nodes = "#2A9D8F"
        ax2.bar(df["months"], df["edges"], color=color_edges,
                alpha=0.8, label="Edges")
        ax2_twin = ax2.twinx()
        ax2_twin.plot(df["months"], df["nodes"], color=color_nodes,
                      marker="s", linewidth=2, markersize=7, label="Nodes")
        ax2.set_xlabel("Months Included")
        ax2.set_ylabel("Network Edges", color=color_edges)
        ax2_twin.set_ylabel("Network Nodes", color=color_nodes)
        ax2.set_title("Network Growth vs. Months of Data")
        ax2.tick_params(axis="y", labelcolor=color_edges)
        ax2_twin.tick_params(axis="y", labelcolor=color_nodes)
        ax2.set_xticks(df["months"].tolist())

        lines1, labels1 = ax2.get_legend_handles_labels()
        lines2, labels2 = ax2_twin.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc="lower right",
                   fontsize=9)

        plt.tight_layout()
        out_path = f"{out_dir}/experiment1_scalability.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close()
    print(f"  ✓ Chart saved → {out_path}")


def plot_experiment_threshold(data_dir: str, out_dir: str):
    """Chart for Experiment 2: threshold sensitivity comparison."""
    path = Path(f"{data_dir}/experiment_threshold_sensitivity.csv")
    if not path.exists():
        print(f"  ⚠  {path} not found — skipping threshold chart")
        return

    df = pd.read_csv(path)
    labels = [f"{t} min" for t in df["threshold_min"]]
    x = np.arange(len(labels))
    width = 0.28

    with plt.rc_context(CHART_STYLE):
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle(
            "Experiment 2 — Propagation Threshold Sensitivity",
            fontsize=14, fontweight="bold", y=1.01
        )

        # Panel 1: event count + primary %
        ax = axes[0]
        bars = ax.bar(x, df["total_events"] / 1_000, color=["#E63946", "#2A9D8F", "#457B9D"],
                      width=0.5, alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel("Total Events (thousands)")
        ax.set_title("Total Propagation Events")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda val, _: f"{val:.0f}K"))
        for bar, pct in zip(bars, df["primary_pct"]):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 3,
                    f"{pct:.0f}% primary",
                    ha="center", va="bottom", fontsize=9, color="#333333")

        # Panel 2: median vs mean delay
        ax2 = axes[1]
        ax2.bar(x - width / 2, df["median_delay"], width, label="Median delay",
                color="#F4A261", alpha=0.9)
        ax2.bar(x + width / 2, df["mean_delay"], width, label="Mean delay",
                color="#E76F51", alpha=0.9)
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels)
        ax2.set_ylabel("Propagated Delay (min)")
        ax2.set_title("Delay Statistics by Threshold")
        ax2.legend(fontsize=9)

        # Panel 3: DFW risk score
        ax3 = axes[2]
        colors = ["#E63946" if t == 15 else "#aaaaaa" for t in df["threshold_min"]]
        ax3.bar(x, df["dfw_risk_score"], color=colors, width=0.5, alpha=0.9)
        ax3.set_xticks(x)
        ax3.set_xticklabels(labels)
        ax3.set_ylabel("DFW Risk Score (avg min/event)")
        ax3.set_title("DFW Risk Score by Threshold")
        ax3.text(1, df[df["threshold_min"] == 15]["dfw_risk_score"].values[0] + 1,
                 "← selected", ha="center", fontsize=9, color="#E63946")

        plt.tight_layout()
        out_path = f"{out_dir}/experiment2_threshold_sensitivity.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close()
    print(f"  ✓ Chart saved → {out_path}")


def plot_experiment_stability(data_dir: str, out_dir: str):
    """Chart for Experiment 3: network stability across months."""
    path = Path(f"{data_dir}/experiment_network_stability.csv")
    if not path.exists():
        print(f"  ⚠  {path} not found — skipping stability chart")
        return

    # Take top 15 by count (descending), then reverse so highest appears at TOP of barh chart
    df = pd.read_csv(path).sort_values("months_in_top10", ascending=False).head(15)
    df = df.iloc[::-1].reset_index(drop=True)  # reverse: barh renders last row at top

    color_map = {"High": "#2A9D8F", "Medium": "#F4A261", "Low": "#E63946"}
    bar_colors = [color_map.get(s, "#aaaaaa") for s in df["stability"]]

    with plt.rc_context(CHART_STYLE):
        fig, ax = plt.subplots(figsize=(12, 6))
        bars = ax.barh(df["airport"], df["months_in_top10"],
                       color=bar_colors, alpha=0.88, height=0.65)
        ax.set_xlabel("Months in Top 10 by Propagation Risk Score (out of 11)")
        ax.set_title(
            "Experiment 3 — Network Stability: Consistent High-Risk Airports Across Months"
        )
        ax.set_xlim(0, 12)
        ax.axvline(x=9, color="#2A9D8F", linestyle="--", linewidth=1.2,
                   label="High stability threshold (≥9/11 months)")
        ax.axvline(x=6, color="#F4A261", linestyle=":", linewidth=1.2,
                   label="Medium stability threshold (≥6/11 months)")

        # Annotate each bar — bars and df rows are in the same order
        for bar, (_, row) in zip(bars, df.iterrows()):
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                    f"{int(row['months_in_top10'])}/11  [{row['stability']}]",
                    va="center", fontsize=9, color="#444444")

        # Legend: green=High (most consistent), orange=Medium, red=Low (least consistent)
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#2A9D8F", alpha=0.88, label="High (≥9 months) — most consistent"),
            Patch(facecolor="#F4A261", alpha=0.88, label="Medium (6–8 months)"),
            Patch(facecolor="#E63946", alpha=0.88, label="Low (<6 months) — least consistent"),
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

        plt.tight_layout()
        out_path = f"{out_dir}/experiment3_network_stability.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close()
    print(f"  ✓ Chart saved → {out_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main(parquet_path: str, data_dir: str):
    print("Loading data for experiments (reuses main pipeline functions) ...")

    # Load once, reuse across all experiments
    df = load_flights(parquet_path)
    pairs = reconstruct_rotations(df)

    # Use the standard 15-min events for scalability experiment
    events = detect_propagation_events(pairs)
    all_airports = sorted(set(events["ORIGIN"]) | set(events["DEST"]))
    meta = load_airport_meta(all_airports)

    # Run all three experiments
    experiment_scalability(events, meta)
    experiment_threshold_sensitivity(pairs, meta)
    experiment_network_stability(data_dir)

    # Generate experiment charts
    out_dir = Path(f"{data_dir}/validation_charts")
    out_dir.mkdir(parents=True, exist_ok=True)
    print("\n[CHARTS] Generating experiment charts ...")
    plot_experiment_scalability(data_dir, str(out_dir))
    plot_experiment_threshold(data_dir, str(out_dir))
    plot_experiment_stability(data_dir, str(out_dir))

    print("\n" + "=" * 60)
    print("All experiments and charts complete.")
    print(f"CSV results saved in: {data_dir}/")
    print(f"Charts saved in:      {data_dir}/validation_charts/")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 Experiments")
    parser.add_argument("--parquet", default="./data/parquet/flights_clean.parquet")
    parser.add_argument("--data_dir", default="data")
    args = parser.parse_args()
    main(args.parquet, args.data_dir)