# Feature status

"Tested" means covered by an automated test in `tests/` or checked by running the built app.

## Implemented

| Area | Feature | Verified by |
|---|---|---|
| App | Start page (new, open, examples, recent, AI builder, units) | built app, `test_ui.py` |
| App | Project explorer with parent/child analyses, properties panel, solve manager | built app screenshot |
| App | Definition / results views, zoom, pan, grid, snap, axes | `test_ui.py`, screenshots |
| App | Undo / redo (60 steps) | `test_draw_region_with_mouse_and_undo` |
| Draw | Regions by mouse (snap to grid and points), drag points, delete | `test_ui.py` |
| Draw | Assign materials, piezometric line, boundary conditions, point loads, surcharges, entry/exit, grid, sketch text | `test_ui.py` (assign, entry/exit), manual |
| Define | Project properties, units (metric/imperial), materials table with validation | `test_materials_dialog_validates` |
| Define | Analysis settings, typed point lists, boundary condition and load editors | manual |
| Slope | Ordinary, Bishop, Janbu (uncorrected), Spencer, Morgenstern-Price (half-sine / constant) | `test_slope.py` |
| Slope | ACADS 1(a) benchmark (reference F ~ 1.00): Bishop 0.985, M-P 0.984 | `test_acads_1a_benchmark` |
| Slope | phi = 0 case checked against direct numerical integration (< 0.5 %) | `test_undrained_methods_agree...` |
| Slope | Entry-and-exit, grid-and-radius, fully specified circles and polylines | `test_slope.py` |
| Slope | Mohr-Coulomb, undrained, bedrock (impenetrable) materials | `test_slope.py` |
| Slope | Pore pressure: piezometric line, Ru, from seepage analysis | `test_slope.py`, `test_seep.py` |
| Slope | Seismic coefficient kh, surcharge and point loads | `test_slope.py` |
| Slope | Monte Carlo probability of failure, reliability index, histogram | `test_probabilistic_*` |
| Slope | Sensitivity of F to one material property | `test_sensitivity_*` |
| Slope | Slice information table, trial surfaces drawn by F | built app |
| Seepage | Automatic triangle mesh | `test_mesh_covers_region_area` |
| Seepage | Steady-state saturated and saturated/unsaturated flow, anisotropy | `test_seep.py` |
| Seepage | Head, pressure head, unit flux, potential seepage face boundaries | `test_seep.py` |
| Seepage | Confined flow exact; rectangular dam within 5 % of Dupuit (measured 1.6 %) | `test_seep.py` |
| Seepage | Head / pressure contours, phreatic line, flow vectors, click to read values | screenshots |
| Files | `.slab` save/open, JSON export, CSV results, CSV point import, PNG, clipboard | `test_io.py` |
| Files | PDF export (drawing + full report) and printing | `test_ui.py`, `test_cli_solve`, PDF inspected |
| Batch | `stratalab solve` command line with `--save`, `--pdf`, `--csv` | `test_cli_solve` |
| AI | AI Slope Builder (Claude, JSON-schema output, validated before use) | `test_ai.py` with a fake client |
| Build | Windows executable (PyInstaller) | built and run on Windows 11 |

## Not implemented

| Feature | Notes |
|---|---|
| Stress-deformation, dynamic (earthquake time history), thermal, contaminant and air-flow analyses | Each is a separate finite element product; out of scope for 1.0. |
| 3D geometry and 3D slope stability | 2D only. |
| Transient (time-dependent) seepage, climate boundaries | Steady state only. |
| Reinforcement (anchors, nails, geosynthetics, piles), tension cracks, ponded water loads, partial factors | Not modelled. Ponded water above the ground is ignored. |
| Strength functions (shear-normal, anisotropic, spatially varying), unsaturated strength (suction) | Constant Mohr-Coulomb / undrained parameters only; negative pore pressure is set to zero. |
| Slip surface optimization, block search, multiple tangent lines | Grid uses a radius range rather than tangent lines. |
| Janbu correction factor f0 | Janbu Simplified is reported uncorrected. |
| Unit conversion when switching unit systems | Switching relabels values; it does not convert them. |
| `.gsz` import/export | Deliberately not supported: that is a proprietary format of another vendor. Use `.slab`, JSON or CSV. |
| macOS build tested on a Mac | The GitHub Actions workflow builds and tests on macOS, but it has not been run yet. |
| Code signing / notarization | Builds are unsigned; Windows SmartScreen and macOS Gatekeeper will warn on first launch. |
| Live Claude API call | Tested with a fake client only; no API key was available during development. |
