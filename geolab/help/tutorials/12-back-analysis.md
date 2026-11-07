<!-- example: Homogeneous slope (benchmark) -->
<!-- check: Homogeneous slope (benchmark) | 0 | critical.fos | 0.987 | 0.01 -->
# Tutorial 12 — Back-analysis of a failed slope, then the redesign

**Goal:** find the soil strength from a slope that failed, then the smallest change that makes it safe.
**Time:** 10 minutes. **Result:** c' = 3.2 kPa at failure; the c'–φ' line; the drainage or the flatter slope
needed for F = 1.5.

## 1. The failed slope

1. **File > Open Example > Homogeneous slope (benchmark)** and solve it (F5).
   - F = 0.987 with c' = 3 kPa and φ' = 19.6°.
   - Suppose this slope failed last monsoon: at failure F was 1.0.
2. **Design > Back-Analysis**:
   - material *Clayey sand*, find *Cohesion c'*, factor of safety at failure 1.0
   - leave *c-phi line* ticked
3. Run. GeoLab answers **c' = 3.22 kPa gives F = 1.000**. This is the strength the soil really had, as long
   as the friction angle is right.
4. The table under it is the **c-phi line**: every pair on it explains the failure equally well.

| φ' (°) | c' (kPa) for F = 1 |
|---|---|
| 15 | about 7.0 |
| 19.6 | 3.2 |
| 25 | about 0.2 |

A laboratory friction angle picks the point. Press **Use this value in the model** to keep c' = 3.22 kPa.

## 2. Redesign for F = 1.5

The slope has to be rebuilt with F ≥ 1.5 (long term, AS and BNBC).

1. **Design > What-If Sliders**: move *Cohesion ×* and *tan(phi) ×* to feel how far F = 1.5 is.
2. **Design > Design Optimizer**:
   - *Largest crest load that still meets the target*, target 0.9: about 19 kPa. This is how much load the
     slope could carry before F dropped to 0.9.
   - For a Quick Slope model, *Slope steepness* gives the flatter slope and *Berm width* the bench that
     is needed.
   - For a model with a water table, *Lower the water table by* gives the drainage depth.
3. Press **Use this design**, solve, and confirm F with the full search.

## 3. Calibrating permeability the same way

**Tools > Calibrate k from Piezometers** works like the back-analysis but for seepage. Enter the heads
measured in piezometers. GeoLab changes k until the seepage analysis matches them. Try it on the *Earth
dam* example: measure the computed heads at two points, change k of the fill, and let GeoLab find it again.
