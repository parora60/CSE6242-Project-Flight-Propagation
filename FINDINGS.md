# Phase 2 – Analytical Findings

> This document captures notable findings, anomalies, and interpretations from the
> Phase 2 propagation network analysis. Intended for use in the midpoint report and
> final writeup. See `README.md` for metric definitions and pipeline documentation.

---

## Dataset

- **Source:** BTS on-time performance data, January–November 2025
- **Flights loaded:** 6,307,561 (after cancellations/diversions removed)
- **Propagation events detected:** 696,975 (using 15-minute BTS threshold)
- **Network:** 349 airports, 6,582 directed edges

---

## Finding 1 — Summer Is Peak Propagation Season (June–July)

Propagation events peak sharply in June (~63K events) and July (~65K events),
roughly 50% higher than the winter baseline of ~37–52K. Total propagated delay
follows the same pattern, peaking at ~4,900K minutes in July.

**Why this matters:** Summer convective weather (thunderstorms) is the primary driver.
Storms at hub airports like DFW, ORD, and ATL create ground stops that cascade
across the entire network because aircraft cannot recover between tight-turn
rotations. This is consistent with known FAA and BTS seasonal reporting.

**Report use:** Use the monthly trends chart to anchor the "when does propagation
peak?" narrative in the report introduction.

---

## Finding 2 — September Anomaly: High Events, Lowest Delay

September shows a clear anomaly: event count (~43K) is moderate but total
propagated delay crashes to its lowest point in the dataset (~2,050K minutes) —
lower even than January despite having more events.

**Interpretation:** Post-Labor Day traffic volume drops significantly. With fewer
flights scheduled, aircraft have more buffer time between rotations, meaning delays
that do propagate are shorter-lived and attenuate faster. The events still occur
(mechanical and carrier delays don't disappear) but they don't compound.

**Report use:** This is the strongest evidence in the data that *schedule density*
amplifies propagation severity independent of weather — worth one paragraph in the
analysis section.

---

## Finding 3 — DFW Is the Highest-Risk Hub by Every Volume Metric

DFW ranks #1 in out_events (40,672), #1 in prop_risk_score among major hubs
(56.2 min), and #2 in PageRank (0.054), behind only ORD in betweenness centrality
(0.1248 vs ORD's 0.1605).

**Why DFW dominates:** American Airlines operates a large connecting hub at DFW
with tight aircraft rotations. American's business model relies on high aircraft
utilization, which means any inbound delay has minimal buffer before the same
aircraft departs again.

**Report use:** DFW as the primary case study airport for the cascade animation
in the D3 visualization. When the demo shows a delay originating at DFW, it
reaches 89 airports in 3 hops — the widest reach of any seed.

---

## Finding 4 — KOA (Kona, Hawaii) Is a Structural Bottleneck

KOA (Ellison Onizuka Kona International) ranks #1 in betweenness centrality
(0.175), higher than DFW, ORD, or ATL.

**Why:** Hawaiian inter-island and mainland routes form long, thin spokes with
no bypass alternatives. Any propagation path that needs to reach Hawaiian
destinations *must* route through KOA or HNL. This makes KOA a structural
chokepoint even though its event volume is low. This is a classic example of
betweenness centrality capturing something out_events cannot: topological
bottleneck importance independent of traffic volume.

**Report use:** Use KOA vs DFW as a contrast example to explain why betweenness
and out_events measure different things. Good for the metrics explanation section.

---

## Finding 5 — Small Airports Dominate Average Severity (prop_risk_score)

GUM (Guam), MGW (Morgantown WV), ESC (Escanaba MI), and ABR (Aberdeen SD) top
the raw prop_risk_score ranking with scores of 80–130 minutes, far above DFW's 56.

**Why:** These airports have very few propagation events (< 200/year), so a single
long delay (international diversion, weather event, equipment swap) moves the
average dramatically. GUM's Pacific location means any propagation event involves
a multi-hour international flight with no quick recovery.

**This is not a bug** — it's a genuine property of the metric. An airport
averaging 130 minutes of propagated delay *per event* is genuinely severe when it
does propagate. The volume filter (≥1,000 out_events) in the validator isolates
this to show only high-volume airports in the primary table.

**Report use:** Explain as a feature of the metric design — prop_risk_score
and out_events are intentionally complementary. Include both in the visualization
so users can explore severity vs. frequency independently.

---

## Finding 6 — Primary vs. Secondary Event Split Confirms Threshold Validity

With the 1-minute threshold: 44% primary (confirmed LATE_AIRCRAFT_DELAY), 56%
secondary (inferred from departure delay only).

With the 15-minute threshold: 62% primary, 38% secondary.

**Interpretation:** Raising the threshold to 15 minutes selectively removed noisy
secondary events — small turnaround delays that were ambiguous — while retaining
the cleaner primary signal. The 62/38 split at 15 minutes is mechanistically
correct: the majority of genuine aircraft-driven propagations should show explicit
`LATE_AIRCRAFT_DELAY` coding in the BTS data.

**Report use:** Include this split as justification for the 15-minute threshold
choice in the methodology section.

---

## Finding 7 — Delay Cause Breakdown Shifts at 15-Minute Threshold

At 1-minute threshold:
- LATE_AIRCRAFT: 56.3%, NAS: 21.5%, CARRIER: 19.3%, WEATHER: 3.0%

At 15-minute threshold:
- LATE_AIRCRAFT: 36.4%, NAS: 29.7%, CARRIER: 29.1%, WEATHER: 4.8%

**Interpretation:** Sub-15-minute delays are overwhelmingly coded as LATE_AIRCRAFT
in the BTS data — likely reflecting gate holds and minor rotation slippage. At 15+
minutes, NAS (ATC, capacity, ground stops) and CARRIER (maintenance, crew) become
equally significant causes. Weather remains a small fraction by count but drives
the largest individual delays (visible in the max=1,505 min in Check 3).

**Report use:** The cause breakdown pie/bar chart in the D3 filter panel will be
more meaningful at the 15-minute threshold — users filtering by "Weather" will see
genuinely weather-driven cascades, not noise.

---

## Cascade Simulation Summary

| Seed | Airports Reached | Hops | Notes |
|---|---|---|---|
| DFW | 89 | 3 | Widest reach; American Airlines hub concentration |
| ORD | 86 | 3 | Highest betweenness; United hub |
| DEN | 88 | 3 | United hub; western gateway |
| ATL | 83 | 3 | Delta hub; Southeast spoke density |
| CLT | 75 | 3 | American hub; narrower regional reach |
| LAX | 89 | 3 | Tied with DFW; Pacific gateway effect |
| DCA | 75 | 3 | Constrained by slot controls and regional routes |

All seeds exhaust their cascade in exactly 3 hops, reflecting uniform hub-level
topology at the top of the network. Differentiation (75–89 airports) comes from
the density and strength of each hub's top-20 propagation routes.

---

## Open Items for Phase 3

- December 2025 data is absent from the dataset — note this in the report and
  visualization date range label
- The cascade simulation uses a simplified linear decay (0.5/hop) — flag as
  a modeling assumption in the report methodology section
