<!-- example: Earth dam: seepage + stability -->
<!-- check: Earth dam: seepage + stability | 0 | inflow | 2.654e-6 | 0.03 -->
<!-- check: Earth dam: seepage + stability | 1 | critical.fos | 1.205 | 0.02 -->
# Tutorial 3 — Earth dam: seepage, then stability

**Goal:** compute the steady flow through a homogeneous dam and use its pore pressures in the stability of
the downstream slope.
**Time:** 20 minutes. **Result:** seepage ≈ 2.65 × 10⁻⁶ m³/s per metre of dam; downstream F ≈ 1.21.

![Total head and phreatic surface](img/seepage.png)

## 1. Project and geometry

1. Start page: Metric, **Seepage**.
2. Draw > Regions — the foundation: (0, 0), (100, 0), (100, 5), (0, 5).
3. Draw > Regions — the dam: (10, 5), (45, 20), (55, 20), (90, 5).

## 2. Materials

| Property | Compacted fill (dam) | Foundation |
|---|---|---|
| Unit weight | 19.5 | 20 |
| c' / φ' | 10 / 28 | 5 / 32 |
| Hydraulic model | Gardner | Gardner |
| Saturated conductivity k | 1 × 10⁻⁶ m/s | 5 × 10⁻⁷ m/s |
| Gardner α | 3 | 3 |

Assign them with Draw > Materials.

## 3. Boundary conditions

Draw > Boundary Conditions, click along each edge, Enter, then choose the type:

| Name | Points | Type | Value |
|---|---|---|---|
| Reservoir | (0, 5) → (10, 5) → (42.67, 19) | Total head | 19 m |
| Tailwater | (90, 5) → (100, 5) | Total head | 5 m |
| Downstream face | (55, 20) → (90, 5) | Potential seepage face | — |

The reservoir boundary follows the upstream face up to the water level (elevation 19 m).

## 4. Solve the seepage

In Define > Analyses set the mesh element size to 1.5 m and the analysis type to Steady-State. Press F5.
Results: total head contours, the phreatic surface, flow vectors (View > Show Flow Vectors). The report
gives the inflow ≈ **2.65 × 10⁻⁶ m³/s/m** (about 0.23 m³ per day per metre of dam).

## 5. Downstream stability

1. Select the seepage analysis and choose Define > Add Child Analysis > Slope stability.
2. In its settings: pore water pressure *From seepage analysis*, method Morgenstern-Price.
3. Draw > Slip Surface Entry and Exit: entry on the crest and upper downstream face (x = 50 to 62), exit on
   the lower face and ground beyond the toe (x = 78 to 95).
4. Solve: **F ≈ 1.21**.

Compare: give the slope analysis no pore pressure (None) and solve — F is higher. Water in the dam reduces
its stability.
