# 4. Slope stability

![Critical slip surface of the homogeneous slope](img/slope.png)

## 4.1 Methods

The **Settings** tab of a slope analysis chooses the method. All methods divide the sliding mass into
vertical slices:

| Method | Equilibrium | Notes |
|---|---|---|
| Ordinary (Fellenius) | Moment | Ignores interslice forces; conservative, for comparison only |
| Bishop Simplified | Moment | Circular surfaces; good for most slopes |
| Janbu Simplified / corrected / Generalized | Force | Non-circular surfaces; corrected uses the f0 factor |
| Spencer | Moment and force | Constant interslice force angle |
| Morgenstern-Price | Moment and force | Interslice function (half-sine, constant, clipped sine, trapezoidal, user) |
| Corps of Engineers 1 and 2, Lowe-Karafiath | Force | Assumed interslice force directions |
| Sarma | Moment and force | Vertical slices with seismic coefficient |
| Finite element stress | — | Uses the stresses of a stress-deformation parent along the slip surface |

The result lists the factor of safety of every method on the critical surface, so a single solve shows how
much the methods differ.

## 4.2 Slip surface searches

The **Slip Surface** tab chooses how trial surfaces are generated:

| Search | Draw with | Use |
|---|---|---|
| Entry and exit | Draw > Slip Surface Entry and Exit: two ranges on the ground surface | The easiest: circles enter in one range and exit in the other |
| Grid and radius | Draw > Slip Surface Grid plus radius range | Classic search over a grid of centres |
| Grid and tangent lines | Grid plus horizontal tangent lines | Circles tangent to a layer boundary |
| Block | Two grids | Wedge (block) surfaces along a weak layer |
| Auto locate | Nothing | GeoLab chooses the ranges from the slope shape |
| Fully specified | Points of one surface | Check one given surface |

The **Optimization** tab refines the critical surface into a non-circular shape (lower F, usually by a
few percent). The Convergence tab sets the number of slices.

## 4.3 Loads and cracks

* Seismic coefficients kh and kv (pseudo-static).
* Tension crack: a fixed depth, or where the slice base is steeper than an angle; the crack can be partly
  filled with water.
* Point loads, surcharges and reinforcement from the Draw menu.

## 4.4 Probabilistic and sensitivity analysis

In the **Distribution** tab tick *Probabilistic analysis*, choose the number of samples, and give the
standard deviations in the Probabilistic tab of each material. GeoLab repeats the factor of safety
calculation on the critical surface with Monte Carlo samples and reports the mean F, its standard
deviation, the reliability index and the probability of failure (F < 1).

The same tab has a **Sensitivity** section: choose one property (cohesion, φ or unit weight of a material)
and a range; the result shows F for each value (View > Graph).

## 4.5 Rapid drawdown (Duncan, Wright and Wong)

When a reservoir is lowered quickly, a clay embankment has no time to drain. The **Rapid Drawdown** tab
turns on the three-stage method:

1. Draw the piezometric line at the **full** reservoir level.
2. Enter the reservoir level **after** drawdown.
3. In each clay material, enter the R envelope (c_R, φ_R) from consolidated-undrained tests. Free-draining
   materials (sand, gravel) keep c_R = φ_R = 0 and use their drained strength.

Stage 1 computes the effective stresses before drawdown; stage 2 the undrained strength from them; stage 3
takes the lower of the drained and undrained strength on each slice. The result shows F for each stage —
use the stage 3 value.

For a reservoir lowered slowly, use a transient seepage analysis as the parent instead (see the tutorial
*Reservoir drawdown*).

## 4.6 Earthquake: Newmark displacement

Make the slope analysis a child of a dynamic analysis. GeoLab computes the yield acceleration of the
critical surface and integrates the average acceleration of the sliding mass above it to give the
permanent (Newmark) displacement. View > Graph shows the acceleration and displacement in time.

## 4.7 Reading the results

* The critical surface and its F are drawn; View > Show Trial Slip Surfaces shows all valid trials coloured
  by F; View > Show Slices shows the slices.
* View > Slice Information lists the forces on each slice.
* View > Report (Ctrl+R) gives all inputs and results as text.
