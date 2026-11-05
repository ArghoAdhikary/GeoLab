# Feature status

"Tested" means covered by an automated test in `tests/` or checked by running the built app.
Accuracy is checked against closed-form solutions and published benchmarks (the same kind of
problems commercial programs use in their verification manuals). No result has been compared
directly with another vendor's software.

## Implemented

### Slope stability (limit equilibrium)

| Feature | Verified by |
|---|---|
| Ordinary, Bishop, Janbu simplified (uncorrected and with f0), Janbu generalized, Spencer, Morgenstern-Price (half-sine, constant, clipped sine, trapezoidal, data points), Corps of Engineers #1 and #2, Lowe-Karafiath, Sarma | ACADS 1(a): all within 1.5 % of M-P 0.984 (referee ~1.00), `test_slope_advanced.py` |
| Griffiths & Lane 2:1 slope: Bishop 1.386 (published 1.38) | `test_strength_reduction_matches_limit_equilibrium` |
| Strength models: Mohr-Coulomb, undrained, undrained increasing with depth, SHANSEP, bilinear, shear/normal function, generalized Hoek-Brown, anisotropic, high strength, bedrock; unsaturated strength (phi-b) | equivalence tests, Hoek-Brown envelope vs closed form |
| Pore pressure: piezometric line, Ru, seepage (steady or transient), ponded water | fully submerged c = 0 slope equals the dry slope (within 0.5 %) |
| Seismic kh and kv, surcharges, point loads | `test_slope.py` |
| Reinforcement: anchors (bonded length), nails, geosynthetics, piles; F-dependent or not; pullout limited by bond beyond the slip surface | `test_reinforcement_raises_fos`, anchor bond test |
| Tension crack by depth or base angle, with water | `test_tension_crack_with_water_lowers_fos` |
| Searches: entry and exit, grid and radius, grid and tangent lines, block, auto locate, fully specified circles and polylines; optimization | search tests; optimized surface independent of slice count |
| Slice boundaries at every slip-surface vertex and ground corner | `test_optimization_is_slice_independent_and_lower` |
| Finite element stress method (stresses from a stress analysis) | within 5 % of LE and strength reduction (`test_examples.py`) |
| Probabilistic (normal, lognormal, uniform), sensitivity | `test_lognormal_probabilistic`, `test_slope.py` |
| Newmark sliding-block displacement from a dynamic analysis | rectangular pulse vs closed form (0.5 %) |

### Seepage (finite element)

| Feature | Verified by |
|---|---|
| Steady and transient, saturated / unsaturated (Gardner, van Genuchten-Mualem), storage from mv | Terzaghi diffusion at Tv = 0.05, 0.2, 0.6 within 1.5 %; mass balance < 2 % for unsaturated infiltration |
| Head (time functions), pressure head, unit flux, nodal flux, seepage face, infiltration with ponding review, free drainage | `test_seep.py`, `test_seep_transient.py` |
| Head boundaries above the water level become seepage faces (drawdown) | drawdown example |
| Flux sections | matches boundary flow (0.1 %) |
| Automatic time-step cutting when a step does not converge | infiltration into dry soil |
| Climate boundary: rainfall and potential evaporation vs time, actual evaporation from surface suction (Kelvin / Wilson-Fredlund-Barbour), ponding and runoff | wet soil evaporates at the potential rate (1 %), dry soil less; rain = runoff + infiltration; water balance < 2 % (`test_climate.py`) |

### Stress-deformation (6-node triangles, plane strain)

| Feature | Verified by |
|---|---|
| In situ (gravity) with effective stresses below the water table | sigma_v = gamma z, K0 on effective stress (2 %) |
| Load-deformation in steps, pressure / shear / force / displacement boundaries, reactions | 1D compression exact (0.1 %) |
| Elastic-perfectly plastic Mohr-Coulomb (non-associated), viscoplastic algorithm | Prandtl strip footing 5.10 su vs 5.14 su exact |
| Strength reduction factor of safety | Griffiths & Lane slope 1.36 (published ~1.4) |
| Coupled Biot consolidation | Terzaghi excess pore pressure and degree of consolidation (2-3 %) |
| Modified Cam Clay (critical state) with pressure-dependent stiffness and hardening | isotropic compression on the NCL, unloading on the URL, undrained shear to q = M p' and p' = p0 2^-(lambda-kappa)/lambda (2 %); FE column = element test (2 %) |
| Duncan-Chang hyperbolic (E-nu) with unload-reload modulus | drained triaxial curve equals the hyperbola (1 %) |
| Nonlinear solver: Newton iterations with the elastoplastic tangent, sub-stepped stress integration | `test_soilmodels.py` |

### Dynamic (earthquake)

| Feature | Verified by |
|---|---|
| Newmark time integration, consistent mass, Rayleigh damping per element, base acceleration | layer natural frequency Vs/4H (2 %) |
| Equivalent linear (hyperbolic G/Gmax and damping) | runs to convergence in the example |
| Amplification | 1 / cos(wH/Vs) below resonance (3 %) |

### Thermal, contaminant transport, air flow

| Feature | Verified by |
|---|---|
| Conduction with freezing / thawing (enthalpy, chord capacity, line search) | erfc solution (0.15 C); Stefan frost front (1.4 %); energy balance < 0.01 % |
| Temperature, heat flux and convective boundaries, time functions | series-resistance convection (0.1 %) |
| Advection-dispersion with adsorption and decay; streamline stabilization when needed | Ogata-Banks (0.02 abs); retardation front |
| Particle tracking | travel distance v t / R (2 %) |
| Air flow (steady / transient) with saturation from seepage | exact steady flux |

### Application

| Feature | Verified by |
|---|---|
| Start page, project explorer with parent / child analyses, properties, solve manager | built app, `test_ui.py` |
| Drawing tools incl. reinforcement and flux sections; undo / redo | `test_ui.py` |
| Materials dialog with tabs per physics; analysis settings per analysis type; boundary conditions limited to one analysis | `test_ui.py` |
| Results: any field, any saved time, deformed mesh, yield zones, vectors, particle paths, point read-out, graphs vs time | `test_results_view_for_every_analysis_type` |
| Files: `.slab`, JSON, CSV (every nodal field), PNG, PDF, printing; command-line batch solver | `test_io.py` |
| AI Slope Builder (Claude) | fake client only |
| Windows and macOS builds | GitHub Actions |

## Not implemented

| Feature | Notes |
|---|---|
| 3D geometry and 3D analyses | 2D only. |
| Vegetation / transpiration, snow, density-dependent flow, freezing-induced water migration | Climate covers rainfall, evaporation, ponding and runoff. |
| Hardening Soil, hysteretic cyclic models, liquefaction / pore pressure generation in dynamic analysis | Static models: linear, Mohr-Coulomb, Modified Cam Clay, hyperbolic. |
| Structural elements in stress analysis (beams, anchors, geogrids) | Reinforcement exists in slope stability only. |
| Staged construction (adding / removing regions between stages) | Stages share one geometry. |
| Consolidation with plasticity; Cam Clay / hyperbolic in the in situ stage | Consolidation is linear elastic; nonlinear models apply in load-deformation stages (in situ uses E and nu). |
| Rapid drawdown by the Duncan-Wright-Wong method | Use transient seepage then slope stability. |
| Unit conversion when switching unit systems | Switching relabels values. |
| `.gsz` import/export | Not supported: another vendor's proprietary format. |
| Code signing / notarization | Builds are unsigned. |
| Live Claude API call | Tested with a fake client only. The AI builder sets up slope models. |
