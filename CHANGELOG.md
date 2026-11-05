# Changelog

## 2.3.0 - 2026-11-05

- `.gsz` import now reads materials (stress model, stiffness, unit weight, void ratio, conductivity,
  anisotropy, compressibility), region assignments, analyses (kind, method, parent, duration, time
  steps), boundary conditions with the analyses that use them, and interior lines such as drains.
- `.gsz` export now writes materials, in situ and consolidation stress analyses, and fixed, load and
  drainage boundaries; the export lists anything it could not write. A real project survives a full
  round trip through GeoStudio's GeoCmd unchanged.
- The mesh follows interior lines (drains, internal boundaries).

## 2.2.0 - 2026-11-05

- Open GeoStudio `.gsz` files (File > Open) and export them (File > Export > GeoStudio Project). The
  geometry (points, lines, regions) is exchanged; material names, region assignments and common
  properties are read when the file has them. Exported files are accepted by GeoStudio's GeoCmd.

## 2.1.0 - 2026-11-05

- Climate boundary for seepage: rainfall and potential evaporation that vary with time; actual
  evaporation falls as the surface dries (Kelvin's law, Wilson-Fredlund-Barbour); rain that cannot
  infiltrate ponds and runs off. Results report rainfall, evaporation and runoff totals.
- Advanced soil models for load-deformation analyses: Modified Cam Clay (critical state) and
  Duncan-Chang hyperbolic, solved with Newton iterations and sub-stepped stress integration.
- Two new examples: rainfall and evaporation on a slope; soft clay under a fill (Cam Clay).

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
