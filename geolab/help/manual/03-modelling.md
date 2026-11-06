# 3. Building a model

A model is built in the same order for every kind of analysis:

1. Project properties and units
2. Geometry (regions)
3. Materials, assigned to the regions
4. Water (piezometric line or a seepage analysis)
5. Boundary conditions and loads
6. Analysis settings
7. Verify and solve

## 3.1 Project properties and units

Define > Project Properties holds the title, author, description and the unit system:

| System | Length | Force | Stress | Unit weight |
|---|---|---|---|---|
| Metric | m | kN | kPa | kN/m³ |
| Imperial | ft | lbf | psf | pcf |

Time is always in seconds. Changing the unit system converts every value in the project (coordinates,
strengths, unit weights, loads, conductivities, structures, search limits). The few values that are not
converted (thermal, transport and air properties) are listed after the change so that they can be checked.

## 3.2 Geometry

**Draw > Regions** (Ctrl+Shift+R): click the corners of a soil region; close it by clicking the first point,
pressing Enter or right-clicking. Points snap to the grid and to the points of other regions, so
neighbouring regions share their edges. Draw each soil layer as its own region.

To enter exact coordinates, select a region and use **Modify > Edit Region Points**, or import a list of
points with **File > Import Region Points (CSV)**: one `x, y` pair per line.

Tips:

* Draw the model wide enough: for a slope, about 1.5 to 2 times the slope height in front of the toe and
  behind the crest, and at least one slope height below the toe.
* Regions must not overlap. Verify (F6) reports overlaps, gaps and regions with no material.

## 3.3 Materials

**Define > Materials** (Ctrl+M) lists the materials. One material holds all properties; only the tabs used by
the analyses in the project matter:

| Tab | Used by | Main properties |
|---|---|---|
| Strength | Slope stability | Strength model, unit weight, c', φ', φb |
| Probabilistic | Probabilistic slope stability | Distribution and standard deviations of c', φ', unit weight |
| Hydraulic | Seepage, consolidation | Hydraulic model, saturated conductivity, water contents, van Genuchten or Gardner parameters, mv |
| Stress | Stress-deformation, consolidation | Stress-strain model, E', ν, dilation, K0, Cam Clay, hyperbolic and Hardening Soil parameters |
| Dynamic | Earthquake | Damping, reference strain |
| Thermal | Heat transfer | Frozen and unfrozen conductivity and heat capacity, water content |
| Transport | Contaminant transport | Dispersivities, diffusion, adsorption Kd, decay |
| Air | Air flow | Dry-soil air conductivity |

Strength models for slope stability:

| Model | Use |
|---|---|
| Mohr-Coulomb | Drained strength c', φ' (most soils) |
| Undrained (φ = 0) | Clay in a short-term (end of construction) analysis: c = su |
| Undrained, strength increasing with depth | Normally consolidated clay: su grows from a datum |
| SHANSEP | su = S · OCR^m · σ'v from the vertical effective stress |
| Bilinear Mohr-Coulomb | Lower φ at high normal stress |
| Shear / normal function | Strength from a table of normal stress and shear strength |
| Generalized Hoek-Brown | Rock masses (UCS, GSI, mi, D) |
| Anisotropic | Strength that depends on the slice base angle |
| High strength | Material the slip surface may cross but never fails in (walls, piles) |
| Bedrock | Impenetrable: slip surfaces stop on it |

Stress-strain models for stress-deformation:

| Model | Use |
|---|---|
| Linear elastic | Stiffness only, no failure |
| Elastic-plastic (Mohr-Coulomb) | The usual model for drained and undrained loading, footings, excavations, strength reduction |
| Modified Cam Clay | Soft normally consolidated clay: stiffness and yield depend on the stress and on λ, κ, e0, OCR |
| Hyperbolic (Duncan-Chang) | Non-linear stiffness that falls as the soil approaches failure |
| Hardening Soil | Stress-dependent loading stiffness E50 and unloading stiffness Eur, failure by Mohr-Coulomb (excavations) |
| None (excluded) | The region is left out of the stress analysis |

**Draw > Materials**: choose the material in the Mode toolbar and click the regions to assign it.

## 3.4 Water

There are two ways to give pore water pressures:

* **Piezometric line** (Draw > Piezometric Line): click points from left to right. Below the line the pore
  pressure is hydrostatic; above it zero (or negative, if a suction friction angle φb is used).
* **A seepage analysis** as the parent: the child (slope or stress analysis) uses the computed pressures.
  Use this for dams, transient drawdown, rainfall and anything where the flow matters.

Slope analyses can also use an Ru coefficient.

## 3.5 Boundary conditions

**Draw > Boundary Conditions**: click along the edge the condition acts on and finish with Enter. The
dialog only offers the types that fit the current analysis:

| Group | Types |
|---|---|
| Hydraulic | Total head, pressure head, unit flux, total nodal flux, potential seepage face, infiltration with ponding, free drainage, climate (rain, evaporation, plant transpiration) |
| Stress | Fixed x, fixed y, fixed x and y, normal pressure, shear stress, force x / y, displacement y |
| Thermal | Temperature, heat flux, convective (h and air temperature) |
| Transport | Concentration, mass flux, free exit |
| Air | Air pressure, air flux |

A boundary condition can change with time (a value vs time table, for transient analyses), and can be
limited to some analyses with **Applies to** (for example, a footing load that acts only in the load
stage). Head boundaries above the water level act as potential seepage faces automatically.

Edges without a boundary condition are no-flow (seepage, heat, mass, air) or free (stress).

## 3.6 Loads, reinforcement and structures

* **Point Loads** and **Surcharge Loads** act in slope stability. In stress-deformation, loads are
  boundary conditions (normal pressure, shear stress, forces).
* **Reinforcement** (slope stability): anchors, nails, geosynthetics and piles with capacity, pullout
  resistance and spacing.
* **Structures** (stress-deformation): walls / beams, anchors / struts and geogrids (chapter 6).

## 3.7 Analyses and parents

Define > Analyses (Ctrl+Shift+A) lists the analyses with their settings. **Define > Add Analysis** adds a
new one; **Define > Add Child Analysis** adds one that uses the selected analysis as its parent:

| Parent | Child uses |
|---|---|
| Seepage | Pore pressures for slope stability and stress; flow velocities for transport; saturation for air flow; initial heads for a transient seepage |
| Stress (in situ or earlier stage) | Initial stresses of the next stage; stresses for the finite element slope method |
| Dynamic | Accelerations for Newmark displacement of a slope |
| Thermal | Initial temperatures for a later thermal analysis |

**Verify** (F6) checks the model and lists problems in plain words. **Solve** (F5) solves the current
analysis and its parents if they have no results; **Solve All** (Shift+F5) solves everything in order.
