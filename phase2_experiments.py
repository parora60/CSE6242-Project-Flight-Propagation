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

    print("\n" + "=" * 60)
    print("All experiments complete.")
    print(f"CSV results saved in: {data_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 Experiments")
    parser.add_argument("--parquet", default="./data/parquet/flights_clean.parquet")
    parser.add_argument("--data_dir", default="data")
    args = parser.parse_args()
    main(args.parquet, args.data_dir)