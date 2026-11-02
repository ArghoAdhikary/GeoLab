# Changelog

## 2.0.0 - 2026-11-02

- New analysis types: stress-deformation (in situ, load-deformation, Mohr-Coulomb plasticity,
  strength reduction, coupled consolidation), dynamic earthquake (Newmark integration, equivalent
  linear), thermal with freezing and thawing, contaminant transport with particle tracking, air flow.
- Seepage: transient flow, van Genuchten functions, infiltration, free drainage, nodal flux,
  time-varying boundaries, flux sections, automatic time-step cutting.
- Slope stability: Janbu corrected and generalized, Corps of Engineers 1 and 2, Lowe-Karafiath, Sarma,
  finite element stress method; SHANSEP, bilinear, shear/normal, Hoek-Brown, anisotropic, undrained
  with depth and unsaturated strength; reinforcement; tension cracks; ponded water; kv; tangent-line,
  block and auto searches; optimization; lognormal and uniform distributions; Newmark displacement.
- Slice boundaries now fall on every slip-surface vertex and ground corner.
- Boundary conditions can be limited to one analysis and can vary with time.
- Interface: new-project type picker, materials dialog with tabs per physics, settings per analysis
  type, results toolbar (field, time, deformed mesh), point read-out, graphs against time,
  reinforcement and flux section tools, eight new examples.

## 1.0.0 - 2026-11-02

First release.

- Desktop app (Windows, macOS) built with Qt for Python: start page, project explorer, properties
  panel, solve manager, definition and results views, menus, toolbars, undo/redo.
- Drawing tools: regions (with snapping and point dragging), material assignment, piezometric line,
  boundary conditions, point and surcharge loads, slip surface entry/exit and grid, sketch text.
- Slope stability: Ordinary, Bishop Simplified, Janbu Simplified, Spencer and Morgenstern-Price
  (GLE). Entry-and-exit, grid-and-radius and fully specified (circular and polyline) slip surfaces.
  Pore pressure from a piezometric line, Ru or a seepage analysis. Seismic coefficient. Monte Carlo
  probabilistic analysis and one-parameter sensitivity.
- Seepage: steady-state saturated/unsaturated finite element solver with automatic triangle mesh,
  head, pressure head, flux and seepage-face boundary conditions, anisotropy, flow vectors and
  phreatic line.
- Files: `.slab` project format (zip + JSON), JSON export, CSV results export, CSV point import,
  PNG export, clipboard copy, PDF export and printing.
- AI Slope Builder: creates a model from a plain-language description using Claude.
- Command line: `stratalab solve file.slab [--save] [--pdf out.pdf] [--csv out.csv]`.
- 38 automated tests, including published benchmark comparisons.
