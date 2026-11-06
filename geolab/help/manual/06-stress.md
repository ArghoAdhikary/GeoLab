# 6. Stress-deformation and consolidation

![Anchored excavation: wall moment and anchor force](img/excavation.png)

## 6.1 Types of stress analysis

| Type | Use |
|---|---|
| In Situ | Initial stresses from gravity (Gravity Activation) or the K0 procedure. The first stage of every stress model. |
| Load-Deformation | A change: a load, a footing displacement, an excavation, a fill, a structure. Starts from its parent's stresses. |
| Coupled Stress/PWP (consolidation) | Settlement and excess pore pressure dissipation in time |

Turn on *Compute strength reduction factor of safety* in an in situ analysis to find F by reducing c' and
tan φ' until the model fails (strength reduction method).

## 6.2 Supports and loads

Every stress model needs supports: usually **Fixed x** on the sides and **Fixed x and y** on the base.
Loads are boundary conditions: normal pressure (a fill or foundation), shear stress, forces, or a
prescribed displacement (a rigid footing pushed down). Use **Applies to** so a load acts only in its stage.

Load steps (Stress tab) divide the change into increments. Non-linear models need several. If a step does
not converge, GeoLab halves it automatically (down to 1/64 of a step) before giving up.

## 6.3 Construction stages: excavation and fill

All stages use one mesh. A region that is not present in a stage — dug out, or not built yet — is unticked
in **Analysis settings > Construction Stage**:

1. Stage 1, In Situ: all regions present except future fill.
2. Stage 2, Load-Deformation, child of stage 1: untick the soil dug out in the first lift.
3. Stage 3: untick the next lift as well, and so on.

Dug-out soil releases the stresses it carried onto the remaining soil (the excavation floor heaves, a wall
moves in). A region that appears in a stage (fill) adds its weight. Regions not present are drawn hatched
and are left out of the results.

Draw each lift as its own region so it can be removed separately.

## 6.4 Structures: walls, anchors and geogrids

**Draw > Structures**: click along the structure and finish with Enter. The dialog chooses:

| Type | Behaviour | Properties |
|---|---|---|
| Beam / wall | Bending and axial (Euler-Bernoulli) | EA, EI per metre run |
| Anchor / strut | Axial only | EA, out-of-plane spacing, prestress when installed |
| Geogrid | Tension only (no compression) | EA per metre run |

Tick the stages the structure is present in (empty = all). An anchor's prestress acts in the stage in which
it is installed. Forces carry on into later stages. Results: the axial force (tension +) and for walls the
bending moment and shear, drawn next to the structure and listed in the report.

Structures are attached to the soil (no interface slip) and stay elastic.

## 6.5 Soil models

See 3.3 for the list. Practical choices:

* Footings and slopes: Mohr-Coulomb with a realistic E (or su with φ = 0 for undrained clay).
* Excavations: Hardening Soil (E50 for loading, Eur ≈ 3 E50 for unloading) gives more realistic heave and
  wall movement than Mohr-Coulomb.
* Soft clay under fills: Modified Cam Clay (λ, κ, e0, OCR).

## 6.6 Consolidation

A Coupled Stress/PWP analysis solves deformation and pore water flow together. It needs the stress
properties and the hydraulic conductivity of each material, a drainage boundary (a head boundary on the
drained surface) and the time steps. The soil can yield (Mohr-Coulomb) during consolidation. Results:
excess pore pressure contours in time, settlement history at the monitor point (View > Graph).

## 6.7 Results

Contours of displacements, total and effective stresses, principal stresses, deviator stress, pore
pressure; the deformed mesh (View > Show Deformed Mesh); yielded zones (View > Show Yielded Zones);
reactions; structure forces.
