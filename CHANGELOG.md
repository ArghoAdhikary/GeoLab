# Changelog

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
