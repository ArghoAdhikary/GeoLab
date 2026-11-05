# StrataLab

2D geotechnical analysis for Windows and macOS:

- **Slope stability** by limit equilibrium: 11 methods (Bishop, Spencer, Morgenstern-Price, Janbu,
  Corps of Engineers, Lowe-Karafiath, Sarma, ...) plus the finite element stress method; 10 strength
  models; reinforcement, tension cracks, ponded water; six slip surface searches and optimization;
  probability, sensitivity and Newmark earthquake displacement.
- **Seepage**: steady and transient, saturated / unsaturated flow with a free phreatic surface, and a
  climate boundary (rainfall, evaporation, ponding and runoff).
- **Stress-deformation**: in situ stresses, load-deformation with Mohr-Coulomb, Modified Cam Clay or
  hyperbolic (Duncan-Chang) soil, strength reduction factor of safety and coupled consolidation.
- **Dynamic**: earthquake response with equivalent linear soil behaviour.
- **Thermal** (with freezing and thawing), **contaminant transport** (with particle tracking) and **air flow**.
- Analyses are linked: seepage feeds slope stability, stress and transport; stresses feed the finite
  element slope method; earthquakes feed Newmark displacement.
- **AI Slope Builder**: describe a slope in plain language and Claude sets up the model.
- Opens GeoStudio `.gsz` files (geometry, materials, slope, stress and seepage analyses, piezometric line, slip surface entry and exit, boundary conditions) and exports them
  (geometry, materials, limit-equilibrium slope analyses with their water table and entry/exit, stress / consolidation analyses and their boundaries).
- PDF reports, PNG/CSV/JSON exports and a command-line batch solver.

See [FEATURES.md](FEATURES.md) for exactly what is and isn't implemented, and how each feature was tested.

## Install

### Ready-made app
Download `StrataLab-windows.zip` or `StrataLab-macos.zip` from the
[Releases](https://github.com/ArghoAdhikary/StrataLab/releases) page
(or the latest **Actions** run), unzip, and run `StrataLab.exe` / `StrataLab.app`.
The builds are not code-signed: on Windows choose *More info > Run anyway*; on macOS right-click the
app and choose *Open* the first time.

### From source (any OS, Python 3.10+)
```bash
git clone https://github.com/ArghoAdhikary/StrataLab.git
```
```bash
cd StrataLab
```
```bash
pip install -r requirements.txt
```
```bash
python -m stratalab
```

### Build the app yourself
```bash
pip install pyinstaller
```
```bash
python build.py
```
The result is `dist/StrataLab/StrataLab.exe` on Windows or `dist/StrataLab.app` on macOS.

## Using it

1. The start page offers a new slope or seepage project, examples, recent files and the AI builder.
2. **Draw > Regions**: click the corners of each soil layer (snaps to the grid and to existing points);
   click the first point or press Enter to close. **Define > Materials** sets strengths and permeability;
   **Draw > Materials** assigns them.
3. Slope stability: **Draw > Slip Surface Entry and Exit** (or *Auto* in **Define > Analyses**),
   then **Analysis > Solve** (F5). The results view shows the critical slip surface and its factor of safety.
4. Seepage: add boundary conditions along region edges (**Draw > Boundary Conditions**), solve, and read
   values by clicking the drawing. Add a child slope analysis to use the seepage pore pressures.
5. **File > Export > PDF** writes the drawing and the full report. **View > Report / Slice Information /
   Graph** show the details.

Help > Quick Guide inside the app has the full list of tools and shortcuts.

### AI Slope Builder
Needs an Anthropic API key: paste it in the dialog (optionally remembered) or set `ANTHROPIC_API_KEY`.
It uses `claude-opus-5-5` with a strict JSON schema; the reply is validated (polygons, materials, ranges)
before it becomes a project, and the model's assumptions are shown to you. Always review the values.

### Command line
```bash
stratalab solve project.slab --save --pdf report.pdf --csv slices.csv
```
(or `python -m stratalab solve ...`). The report is printed to the terminal.

## File format
`.slab` is a zip containing `manifest.json` and `project.json` (all geometry, materials, analyses and
results). **File > Export > Project (JSON)** writes the same data as plain JSON, which also opens directly.

## Development
```bash
pip install -r requirements.txt pytest
```
```bash
python -m pytest
```
On a machine without a display set `QT_QPA_PLATFORM=offscreen`. Code layout:

| Path | Contents |
|---|---|
| `stratalab/model.py` | Project data model and serialization |
| `stratalab/geometry.py` | Polygons, ground profile, validation |
| `stratalab/slope.py` | Method of slices, GLE solver, searches, probability |
| `stratalab/seep.py` | Mesh generator and FE seepage solver |
| `stratalab/solver.py` | Runs analyses in parent/child order, pre-solve checks |
| `stratalab/ai.py` | Claude integration |
| `stratalab/ui/` | Qt main window, canvas, dialogs, rendering, PDF |
| `tests/` | Benchmarks and unit/GUI tests |

GitHub Actions (`.github/workflows/build.yml`) tests and builds on Windows and macOS for every push,
and attaches the zipped apps to a GitHub release when you push a tag such as `v1.0.0`.

## Validation
Every solver is checked by automated tests against closed-form solutions or published benchmarks:
- ACADS 1(a) homogeneous slope (referee F ~ 1.00): Bishop 0.985, Morgenstern-Price 0.984; all 11 methods within 1.5 %.
- Griffiths & Lane slope: Bishop 1.386 (published 1.38), strength reduction 1.36 (published ~1.4).
- Prandtl bearing capacity: 5.10 su (exact 5.14 su).
- Terzaghi consolidation and transient seepage: within 2 % of the series solution.
- Seepage: exact confined flow, Dupuit dam within 1.6 %, unsaturated infiltration mass balance < 2 %.
- Heat: erfc conduction, Stefan frost front within 1.4 %, energy balance < 0.01 %.
- Transport: Ogata-Banks, retardation, particle travel time.
- Dynamic: layer frequency Vs/4H within 2 %, amplification within 3 %, Newmark sliding block within 0.5 %.

See [FEATURES.md](FEATURES.md) for the full list.

Results are only as good as the model. Check inputs and results independently before relying on them.

## License
MIT
