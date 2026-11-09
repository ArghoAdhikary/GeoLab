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

### Added in 2.14 (3D, axisymmetric, liquefaction, interfaces)

| Feature | Verified by |
|---|---|
| 3D slope stability: ellipsoids on an extruded section, 3D Bishop simplified (Hungr 1987), trial lengths, loads over part of the width | a very long ellipsoid equals 2D Bishop (1e-6); F falls towards the 2D value as the slide gets longer; a partly loaded slide lies between unloaded and fully loaded (`test_v214.py`) |
| 3D seepage (wedge elements, steady / transient, unsaturated), boundaries over part of the width, wells (head or rate) | extruded earth dam equals the 2D heads (1e-6) and width x 2D flow; pumped flow balances exactly; drawdown largest at the well |
| Axisymmetric seepage | Thiem's equation for confined flow to a well (1.5 %) and its head at r = 5 m |
| Pore pressure generation and liquefaction in dynamic analysis (cycle counting, Seed et al. 1976) | 15 uniform cycles at CSR = CRR15 give D = 1 (4 %); a lower CRR liquefies more; post-earthquake F lower than static |
| Interface elements (shear / normal stiffness, adhesion, friction, no dilation) | shear box slip = tau / ks (3 %); slides beyond c + sigma tan delta; exact return to the slip limit |
| 3D View and 3D sections | drawn and switched in the app (`test_v214.py`) |

### Added in 2.13 (more design and settings)

| Feature | Verified by |
|---|---|
| Yield acceleration ky and Newmark displacement (Jibson 2007, Ambraseys and Menu 1988) | F = 1.00 at ky on the layered example; regression values by hand (`test_v213.py`) |
| Parametric study (one or two values) | a higher water table lowers F; crossing interpolation; Excel and CSV tables |
| Pile capacity, groups, settlement | bored pile in clay equals 0.45 Su and 9 Su by hand; group efficiency and block failure |
| Soil nail wall, ground anchor, geosynthetics | apparent pressure, bond length and T_al by hand; values put into the model |
| Braced excavation | strut loads add up to the pressure diagram; Peck envelopes; basal heave |
| Excel export | workbook opened as a zip; sheet names cleaned and unique |
| Offline mode, templates, solver presets, CPU cores, palettes, report branding and Bangla | driven through the preferences dialog and the menus (`test_v213.py`) |

### Added in 2.12 (field to design)

| Feature | Verified by |
|---|---|
| Cross-section from a map (Open-Meteo / Copernicus DEM) to a layered slope model | haversine distance; model built and solved from a test profile (`test_v212.py`) |
| Landslide early warning (forecast, quick and model methods, alert levels, 6-hour watch) | F falls with the rain on the rainfall example; thresholds; dialog with a fake forecast |
| Probabilistic analysis on a surface pool, reliability index, tornado | Pf and mean F of the benchmark; phi' is the most sensitive parameter |
| AutoCAD DXF import / export | round trip of a layered model; LINE loops in millimetres |
| Bearing capacity, settlement, retaining wall, cantilever sheet pile | Vesic factors for phi' = 30 deg (30.14, 18.40, 22.40); Ka, Kp; water lowers the capacity |
| Mohr-Coulomb fit of triaxial and direct shear tests | exact c' = 10, phi' = 30 recovered |
| SWCC and k estimates | sand and clay values in the expected ranges |
| Quantities, cut and fill, cost, option comparison | cut 7.5 / fill 2.5 m2 of a test section |
| Command palette, tabs, history, version history, shortcuts, my toolbar, thumbnails, crash recovery, update check, share report | driven through the widgets (`test_v212.py`) |

### Added in 2.11 (looks and files)

| Feature | Verified by |
|---|---|
| Interface styles (5) and colour schemes (8, day and night), accent colour, interface font | every style sheet parses; palette and style sheet checked (`test_appearance.py`) |
| Colour and font for each part of the window (20 parts, including the Windows 11 title bar and the chat) | settings round trip; the colours reach the style sheet, the chat and the canvas |
| Added fonts (.ttf / .otf) and theme files | font loaded and removed; theme file round trip |
| Autosave (on by default, .bak copy, recovery folder) | autosave writes the file or the recovery copy |
| Cloud drive backup (Google Drive, OneDrive, Dropbox, iCloud) with versions | dated copies, pruning, drive detection |
| Save As .gsz and Export as PDF (all analyses) | files written and opened as a zip / PDF |

### Added in 2.10 (design tools)

| Feature | Verified by |
|---|---|
| Quick re-evaluation of the slip surfaces of the last search (what-if sliders, optimizer, back-analysis, AS 4678 check) | pool minimum equals the full search; changes act in the right direction (`test_design_tools.py`) |
| Design codes: Australian Standards (default) and BNBC 2020: minimum F by case, AS 4678 factored check, AS 1170.4 / BNBC seismic kh | PGA and kh against hand calculation; code check on the benchmark slope; tutorials 11 and 13 |
| Back-analysis of strength (one parameter, c'-phi' line) and of k from piezometers | c' = 3.22 kPa at F = 1 for the benchmark; k of a dam fill recovered from its own heads |
| Design optimizer: slope ratio, berm, drain depth, reinforcement, largest crest load | target reached and confirmed by a full search |
| Liquefaction: SPT (Idriss & Boulanger 2014), CPT (Robertson & Wride 1998), LPI | (N1)60cs, CRR, CSR and FS against a hand calculation |
| Boreholes / CPT from CSV or Excel to a cross-section with correlated parameters | sample logs give a valid section; .xlsx read without extra libraries |
| Rainfall from Open-Meteo, CSV or a design storm on the climate boundary | parsed and applied (network call replaced in the tests) |
| Monitoring data compared with seepage / stress results | computed heads match their own readings |
| River bank and flood embankment templates | valid geometry; results quoted in tutorials 11 and 13 are checked |
| Word (.docx) and PDF design report | report written and opened as a zip / PDF; pictures included |
| Model from a photo or sketch (Claude) | request with the picture checked with a fake client |
| Python console; Bangla interface | console runs code; menus translated (`test_ui_design.py`) |

The design code values (minimum factors, AS 4678 soil factors, hazard factors) are GeoLab's defaults and
can be edited. The project specification and the standards themselves govern.

## Not implemented

| Feature | Notes |
|---|---|
| 3D terrain and layers that change along z; 3D stress-deformation | 3D slope and seepage use one section extruded over a width. |
| Snow, density-dependent flow, freezing-induced water migration | Climate covers rainfall, evaporation, plant transpiration, ponding and runoff. |
| Hardening Soil cap (volumetric hardening), hysteretic cyclic models, effective-stress cyclic constitutive models | Dynamic pore pressure comes from cycle counting (Seed et al. 1976), not a constitutive model. |
| Zero-thickness interfaces; structural yield | Interfaces are thin layers of elements; structures stay elastic. |
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
