<!-- example: Earthquake + Newmark displacement -->
<!-- check: Earthquake + Newmark displacement | 0 | critical.fos | 1.634 | 0.02 -->
<!-- check: Earthquake + Newmark displacement | 0 | newmark.ky | 0.247 | 0.05 -->
# Tutorial 8 — Earthquake and Newmark displacement

**Goal:** shake a slope with a 0.25 g pulse and estimate how far it slides.
**Time:** 15 minutes. **Result:** static F ≈ 1.63, yield acceleration ≈ 0.25 g, permanent displacement a
few millimetres.

![Peak acceleration](img/dynamic.png)

Open File > Open Example > *Earthquake + Newmark displacement*. It is the slope of tutorial 1 with
c' = 10 kPa, φ' = 25° and dynamic properties (Dynamic tab of the material: damping 3 %, reference strain
5 × 10⁻⁴, maximum damping 15 %).

## 1. The dynamic analysis

* Type Equivalent Linear, time step 0.01 s, 4 iterations.
* Input acceleration: a table of time (s) and acceleration (g); here a 2 Hz pulse with a peak of 0.25 g
  around 3 s. Paste your own record into the table (two columns).
* Boundaries: base fixed in x and y, sides fixed in y.

## 2. The slope stability child

*Newmark deformation* is a slope stability analysis whose parent is the dynamic analysis. GeoLab finds
the critical surface (static F ≈ 1.63), its **yield acceleration** ky ≈ 0.25 g, and integrates the average
acceleration of the sliding mass above ky to get the permanent displacement.

## 3. Results

Shift+F5, then:

* Dynamic: peak acceleration contours (amplification towards the crest), the natural frequency in the
  report, the acceleration history at a clicked point (View > Graph).
* Newmark: View > Graph shows the average acceleration against ky and the displacement building up
  whenever the acceleration exceeds ky. The final value is only a few millimetres for this pulse.

**Try:** scale the input record to 0.4 g peak and solve again.
