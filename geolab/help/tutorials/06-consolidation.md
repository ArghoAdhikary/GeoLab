<!-- example: Consolidation under a fill -->
<!-- check: Consolidation under a fill | 0 | settlement_first | 0.0209 | 0.05 -->
<!-- check: Consolidation under a fill | 0 | settlement_last | 0.0558 | 0.05 -->
# Tutorial 6 — Consolidation under a fill

**Goal:** see how a clay layer settles in time under a 60 kPa fill as excess pore pressure drains away.
**Time:** 15 minutes. **Result:** immediate settlement ≈ 21 mm, after one year ≈ 56 mm.

![Excess pore pressure](img/consolidation.png)

## 1. Model

1. Start page: Metric, **Stress-deformation**.
2. Region: (0, 0), (30, 0), (30, 8), (0, 8) — an 8 m clay layer, half model (symmetry at x = 0).
3. Material *Clay*: E = 5 000 kPa, ν = 0.3, unit weight 18, hydraulic conductivity k = 1 × 10⁻⁹ m/s.

## 2. Boundaries

| Name | Edge | Type | Value |
|---|---|---|---|
| Left side, Right side | the vertical edges | Fixed x | — |
| Base | (0, 0) → (30, 0) | Fixed x and y | — |
| Fill load | (10, 8) → (0, 8) | Normal pressure | 60 kPa |
| Drained surface | (0, 8) → (30, 8) | Total head | 8 m (water at the surface) |

The base and sides are undrained (no hydraulic boundary), so water leaves only through the top.

## 3. Analysis

Define > Analyses: type **Coupled Stress/PWP (consolidation)**, duration 3.15 × 10⁷ s (1 year), 30 time
steps, growth ratio 1.2 (short steps at first), mesh 1 m.

## 4. Results

* Move the time slider: the excess pore pressure under the fill starts near 60 kPa and drains from the top.
* View > Graph: the settlement at the monitor point grows from **21 mm** (immediate, undrained) to
  **56 mm** after one year.

**Try:** k = 1 × 10⁻⁸ m/s — consolidation is ten times faster.
