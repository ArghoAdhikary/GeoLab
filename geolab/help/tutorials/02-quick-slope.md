<!-- quick: {"height": 8, "ratio": 2, "crest": 20, "toe": 20, "base": 5, "water": 3, "surcharge": 0, "layers": [{"name": "Clay", "c": 10, "phi": 25, "gamma": 18, "thickness": 5}, {"name": "Sand", "c": 0, "phi": 34, "gamma": 20, "thickness": 0}]} -->
<!-- check: @quick | 0 | critical.fos | 1.619 | 0.01 -->
<!-- check: @quick water=1 | 0 | critical.fos | 1.548 | 0.01 -->
<!-- check: @quick water=none | 0 | critical.fos | 1.719 | 0.01 -->
# Tutorial 2 — Quick Slope: a layered slope with water in one minute

**Goal:** let GeoLab draw and solve a two-layer slope with a water table, then see how the water changes F.
**Time:** 5 minutes. **Result:** F ≈ 1.62.

![Quick Slope dialog](img/quick_slope.png)

## 1. Fill in the Quick Slope dialog

File > New Quick Slope (Ctrl+Shift+N), or **Quick Slope** on the start page. Enter:

| Field | Value |
|---|---|
| Slope height | 8 m |
| Slope steepness | 2 (2 horizontal : 1 vertical) |
| Ground behind the crest | 20 m |
| Ground in front of the toe | 20 m |
| Soil below the toe | 5 m |
| Groundwater | tick *Water table*, 3 m below the crest |
| Load on the crest | 0 |

Soil layers (top to bottom), already filled in:

| Name | c' (kPa) | φ' (°) | γ (kN/m³) | Thickness (m) |
|---|---|---|---|---|
| Clay | 10 | 25 | 18 | 5 |
| Sand | 0 | 34 | 20 | (to the bottom) |

Keep *Solve straight away* ticked and click **Build slope**.

## 2. Look at the result

GeoLab draws the regions, the water table and the slip surface search, solves, and shows
**F ≈ 1.62** (Morgenstern-Price).

## 3. What does the water do?

1. Draw > Piezometric Line, or simply run Quick Slope again with a different water depth:
   * water 1 m below the crest: **F ≈ 1.55**
   * no water table (untick it): **F ≈ 1.72**
2. Higher water means higher pore pressure, lower effective stress and so lower shear strength on the slip
   surface.

Everything Quick Slope made can be edited afterwards like any other model (regions, materials, the water
line, the search).
