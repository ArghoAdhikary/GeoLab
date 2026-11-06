<!-- example: Reservoir drawdown (transient) -->
<!-- check: Reservoir drawdown (transient) | 2 | critical.fos | 0.935 | 0.03 -->
<!-- example2: Rapid drawdown (Duncan-Wright-Wong) -->
<!-- check: Rapid drawdown (Duncan-Wright-Wong) | 0 | drawdown.stage1 | 2.548 | 0.02 -->
<!-- check: Rapid drawdown (Duncan-Wright-Wong) | 0 | drawdown.stage3 | 1.001 | 0.02 -->
# Tutorial 4 — Reservoir drawdown, two ways

When the water in front of a slope falls, the water inside the slope cannot follow at once. There are two
ways to analyse it in GeoLab:

* **A. Transient seepage** — follow the water level in the soil in time. Best for sand and silt, which drain
  during the drawdown.
* **B. Rapid drawdown (Duncan, Wright and Wong)** — the clay has no time to drain at all; its strength comes
  from consolidated-undrained tests.

## A. Transient seepage (drawdown over 5 days)

Open File > Open Example > *Reservoir drawdown (transient)* and look at its three analyses:

1. **Full reservoir (steady)** — total head 16 m on the upstream face, seepage face above it, groundwater
   16 m on the right.
2. **Drawdown (5 days)** — transient, child of 1. The reservoir boundary has a *value vs time* table:
   16 m at time 0, 4 m at 432 000 s (5 days). 20 time steps.
3. **Stability after drawdown** — slope stability, child of 2, pore pressures from the seepage at the last
   time step.

Press Shift+F5 (Solve All). In the results of analysis 2 move the time slider: the water level in the slope
lags behind the reservoir. Click a point inside the slope and open View > Graph to see its head against
time. Analysis 3 gives **F ≈ 0.94** — the slope is not safe after this drawdown.

## B. Rapid drawdown, three-stage method

![Rapid drawdown result](img/drawdown.png)

Open File > Open Example > *Rapid drawdown (Duncan-Wright-Wong)*:

1. The piezometric line is at the **full** reservoir level (16 m).
2. Define > Analyses > Rapid Drawdown tab: *three-stage method* ticked, level after drawdown 4 m.
3. Define > Materials > Clay fill: drained c' = 5 kPa, φ' = 30°, and the **R envelope** c_R = 2 kPa,
   φ_R = 10° (from CU tests).

Solve. The result lists:

| Stage | Meaning | F |
|---|---|---|
| 1 | Before drawdown, drained | 2.55 |
| 2 | After drawdown, undrained strength from stage 1 | 1.03 |
| 3 | Lower of drained and undrained strength on each slice | **1.00** |

Use the stage 3 value. The drop from 2.55 to 1.00 shows how dangerous a fast drawdown is for a clay slope.
