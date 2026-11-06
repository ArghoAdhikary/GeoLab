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
| In situ by the K0 procedure (sigma'v from the soil column above, sigma'h = K0 sigma'v) | exact hand calculation |
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
| GeoStudio `.gsz` open: geometry incl. interior lines (drains), materials (stress, hydraulic, compressibility) and region assignments, analyses (kind, method, parent, duration, steps), boundary conditions with the analyses that use them | two real GeoStudio 2025 files imported; imported consolidation solves; `test_gsz.py` |
| GeoStudio `.gsz` export: geometry, materials, in situ and consolidation stress analyses, fixed / load / drainage boundaries; anything else is listed as not written | real project exported, passed through GeoStudio's GeoCmd and read back identical (regions, materials, analyses, boundaries) |
| AI Slope Builder (Claude) | fake client only |
| AI Assistant chat (Claude, OpenAI, OpenAI-compatible, Claude Code / Codex accounts) | fake API clients and fake command line programs; chat head, popup and side panel modes |
| Light / Dark / Auto theme | palette, canvas, start page and icon colours checked in tests |
| Windows and macOS builds | GitHub Actions |

### Added in 2.8.0 (staged construction, structures, more SEEP / SLOPE / SIGMA features)

| Feature | Verified by |
|---|---|
| Staged construction: each stress stage lists the regions not present (excavated or not built yet); removed soil releases its stresses, new fill adds its weight, stresses carry on from the parent stage | a stage with no change does not move (exact); 2 m fill on an 8 m layer settles as 1D theory (6 %); excavation floor heaves (`test_staged.py`) |
| Structural elements in stress analysis: walls / beams (Euler-Bernoulli frame, EA and EI), anchors / struts (bars, spacing, prestress), geogrids (tension only); forces carry over between stages | cantilever tip deflection P L^3 / 3 EI and fixed-end moment P L (exact); bar stiffness EA / (L spacing) (exact); slack geogrid carries no compression; anchored excavation example: anchor stays in tension, wall moment continuous |
| Hardening Soil (shear hardening: stress-dependent E50 and Eur with exponent m, hyperbolic curve with Rf, Mohr-Coulomb limit; no cap) | modulus at p_ref = 2 E50 / (2 - Rf), (4 p_ref / p_ref)^0.5 = 2 times stiffer, unloading uses Eur (exact); layer load converges, softer with lower E50 |
| Load steps cut in half automatically when a nonlinear step does not converge (Cam Clay, hyperbolic, Hardening Soil) | a hyperbolic footing that used to diverge now finishes |
| Consolidation with plasticity (Mohr-Coulomb, viscoplastic iterations each time step), with stages and structures | plastic consolidation settles more than elastic (`test_staged.py`) |
| Seepage: plant transpiration on climate boundaries (root zone with triangular root density, Feddes reduction: none when saturated, full between -0.25 and -4 m, zero at -150 m) | Feddes values exact; moist soil transpires at the potential rate (2 %), water balance < 2 % (`test_climate.py`) |
| Slope: rapid drawdown by the three-stage Duncan, Wright and Wong (1990) method with R envelopes (c_R, phi_R) per material | stage 3 <= stage 2 < stage 1; a free-draining fill gives exactly the drained result with the after-drawdown water table (`test_slope_advanced.py`) |
| Unit conversion of the whole project (m / ft, kPa / psf, kN/m3 / pcf, forces, conductivities, structures, search settings) | metric -> imperial -> metric restores every value; factor of safety the same in both systems (0.2 %) (`test_units.py`) |
| GeoStudio export of SEEP/W analyses (steady and transient) and hydraulic boundaries (head as HydHeadvsTime, pressure head, unit / total flux, seepage face, infiltration) | exported file opened by GeoStudio 2025.2 GeoCmd: no warnings, recognised as SEEP/W, regions and points verified (solving needs the GUI to mesh it, and a SEEP/W licence) |
| Beginner help: step guide above the drawing (ticks done steps, highlights the next, one-click tools), Quick Slope dialog (slope from height, steepness, layers, water, load), tooltips on every drawing tool | `test_ui_beginner.py` |

### Added in 2.9.0 (documentation, examples, MKL solver)

| Feature | Verified by |
|---|---|
| User manual (10 chapters) and 10 tutorials, in the app (Help > User Manual, Tutorials) and as a PDF with screenshots | every number quoted in a tutorial is recomputed and compared (`test_help.py`); help window opens tutorial models (`test_ui_beginner.py`) |
| Example files: every example solved and saved as .slab (Help > Example Files Folder, GeoLab-examples.zip) | files written and read back (`test_help.py`) |
| Intel MKL PARDISO sparse direct solver on Windows for systems above 30 000 unknowns; SciPy SuperLU below that, on macOS and on phones | same solution to round-off (residual ~1e-15); full test suite passes with MKL loaded; factorisation 5-8 times faster at 50 000-200 000 unknowns |

## Not implemented

| Feature | Notes |
|---|---|
| 3D geometry and 3D analyses | 2D only. |
| Snow, density-dependent flow, freezing-induced water migration | Climate covers rainfall, evaporation, plant transpiration, ponding and runoff. |
| Hardening Soil cap (volumetric hardening), hysteretic cyclic models, liquefaction / pore pressure generation in dynamic analysis | Static models: linear, Mohr-Coulomb, Modified Cam Clay, hyperbolic, Hardening Soil (shear hardening). |
| Interface elements between structures and soil; structural yield | Structures are tied to the soil nodes and stay elastic. |
| Cam Clay / hyperbolic / Hardening Soil in the in situ and consolidation stages | Those stages use E and nu (Mohr-Coulomb plasticity is included); the nonlinear models apply in load-deformation stages. |
| Thermal, transport and air-flow values in unit conversion | Listed after converting so they can be checked. |
| `.gsz`: dynamic, thermal, transport and air analyses on export; structures, construction stages and rapid drawdown settings; results | Written as a list of skipped items when exporting. Results are not read. |
| Code signing / notarization | Builds are unsigned. |
| Live Claude API call | Tested with a fake client only. The AI builder sets up slope models. |

## GeoLab Mobile (Android / iOS)

| Feature | Verified by |
|---|---|
| Same engine on the phone (Pyodide 0.27.7, numpy, scipy, offline) | `test_mobile.py` (bridge, native Python); quick slope and earth-dam seepage + stability run in a phone-size browser |
| Quick slope from height, ratio, widths, layers, water table, crest load; examples; open .slab/.gsz; save and share .slab | `test_mobile.py` |
| Edit materials, method, pore water, kh, water table, crest load; solve one or all; FS by all methods; FE colour maps; report | `test_mobile.py`, browser check |
| Android APK and iOS IPA built by GitHub Actions (Capacitor) | Actions run; not yet run on a real phone |
