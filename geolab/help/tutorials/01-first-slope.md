<!-- example: Homogeneous slope (benchmark) -->
<!-- check: Homogeneous slope (benchmark) | 0 | critical.fos | 0.987 | 0.01 -->
# Tutorial 1 — Your first slope

**Goal:** draw a simple 10 m high slope from scratch, give it a soil, and find its factor of safety.
**Time:** 10 minutes. **Result:** F ≈ 0.99 (this is the ACADS 1(a) benchmark; the published answer is about 1.0).

![The finished model](img/tut_first_slope.png)

## 1. Start a project

1. File > New Project (or on the start page choose **Metric** and click **Slope stability**).
2. Define > Project Properties: type a title, for example *My first slope*.

## 2. Draw the ground

1. Draw > Regions (or click step **1 Draw the ground** in the step guide).
2. Click these six points in order. The coordinates are shown in the status bar at the bottom; points snap
   to the 1 m grid.

   | Point | x (m) | y (m) |
   |---|---|---|
   | 1 | 0 | 0 |
   | 2 | 70 | 0 |
   | 3 | 70 | 15 |
   | 4 | 40 | 15 |
   | 5 | 20 | 5 |
   | 6 | 0 | 5 |

3. Click point 1 again (or press Enter) to close the region. Press F to zoom to fit.

If a point lands in the wrong place, choose Modify > Edit Region Points and type the numbers.

## 3. The soil

1. Define > Materials (Ctrl+M). Select the first material and set:
   * Name: *Clayey sand*
   * Strength model: Mohr-Coulomb
   * Unit weight: 20 kN/m³
   * Cohesion c': 3 kPa
   * Friction angle φ': 19.6°
2. Close the dialog. If the region is not yet coloured, choose Draw > Materials and click inside it.

## 4. Where the slope can slide

1. Draw > Slip Surface Entry and Exit.
2. Click two points on the crest (the top surface, for example x = 40 and x = 60) for the **entry** range,
   then two points on the toe (x = 5 and x = 20) for the **exit** range.

Slip circles start in the entry range and end in the exit range. (The example file uses ranges found
automatically by GeoLab, which gives the same answer.)

## 5. Solve

1. Press **F6** (Verify). It should say the model is ready.
2. Press **F5** (Solve). The Solve Manager shows the progress.

## 6. Results

* GeoLab switches to the Results view and draws the critical slip surface with **F = 0.99**
  (Morgenstern-Price).
* View > Report (Ctrl+R) lists F by every method on the same surface: Ordinary and Janbu Simplified give
  about 0.94-0.95; Bishop, Spencer and Morgenstern-Price agree at 0.99.
* View > Show Trial Slip Surfaces shows all trial circles coloured by F.

**Try:** raise c' to 10 kPa and solve again — F rises to about 1.36. Change the method in Define > Analyses.

Open the finished model with File > Open Example > *Homogeneous slope (benchmark)*.
