# GeoLab

2D geotechnical analysis for Windows, macOS, Android and iOS (formerly StrataLab):

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
- **AI Assistant chat**: a round chat button in the bottom-right corner opens a small chat box or a
  full side panel. Ask it to build slopes, change the open model, solve it or explain the result. It
  works with Claude or ChatGPT (API key), any OpenAI-compatible service (Gemini, OpenRouter, DeepSeek,
  Ollama, LM Studio...), or your Claude / ChatGPT account through the Claude Code or Codex app.
- **AI Slope Builder**: describe a slope in plain language and Claude sets up the model.
- **Light, Dark and Auto themes** (View > Theme): day and night colours, Auto follows the system.
- Opens GeoStudio `.gsz` files (geometry, materials, slope, stress and seepage analyses, piezometric line, slip surface entry and exit, boundary conditions) and exports them
  (geometry, materials, limit-equilibrium slope analyses with their water table and entry/exit, stress / consolidation analyses and their boundaries).
- PDF reports, PNG/CSV/JSON exports and a command-line batch solver.

See [FEATURES.md](FEATURES.md) for exactly what is and isn't implemented, and how each feature was tested.

## Install

### Ready-made app
From the [Releases](https://github.com/ArghoAdhikary/GeoLab/releases) page:

| File | For |
|---|---|
| `GeoLab-Setup.exe` | Windows installer: Start menu and desktop shortcuts, opens `.slab` files, uninstall from Settings > Apps |
| `GeoLab-windows-portable.zip` | Windows, nothing installed: unzip anywhere (also a USB stick) and run `GeoLab.exe`. Settings stay in `GeoLab.ini` beside it |
| `GeoLab-macos.zip` | macOS: unzip and open `GeoLab.app` |
| `GeoLab-android.apk` | Android phones and tablets (GeoLab Mobile) |
| `GeoLab-ios-unsigned.ipa` | iPhone and iPad (GeoLab Mobile), unsigned: see below |

The desktop builds are not code-signed: on Windows choose *More info > Run anyway*; on macOS right-click
the app and choose *Open* the first time.

### GeoLab Mobile (Android and iOS)
The phone app runs the same Python analysis engine as the desktop app (through Pyodide, fully offline):
build a slope from a few numbers (height, slope, layers, water table, crest load) or open an example
or a `.slab` / `.gsz` file, edit materials, method, water table and seismic coefficient, solve, and see the
critical slip surface, the factor of safety by every method, seepage and other finite element results
as colour maps, and the full text report. Projects save and share as `.slab` files that open on the desktop.

- **Android**: download `GeoLab-android.apk` on the phone, open it and allow *Install unknown apps* for
  your browser or file manager when asked. Updates install over the old version.
- **iOS**: Apple only allows apps from the App Store or signed with a developer account, so the `.ipa`
  is unsigned. Install it with [AltStore](https://altstore.io) or [Sideloadly](https://sideloadly.io) using
  your Apple ID (free accounts re-sign every 7 days), or sign it with your own Apple Developer account.
- **Browser**: run `python mobile/build_web.py`, then `python -m http.server -d mobile/www` and open
  http://localhost:8000 (Pyodide then loads from the internet).

### From source (any OS, Python 3.10+)
```bash
git clone https://github.com/ArghoAdhikary/GeoLab.git
```
```bash
cd GeoLab
```
```bash
pip install -r requirements.txt
```
```bash
python -m geolab
```

### Build the app yourself
```bash
pip install pyinstaller
```
```bash
python build.py
```
The result is `dist/GeoLab/GeoLab.exe` on Windows or `dist/GeoLab.app` on macOS.

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

### AI Assistant chat
Turn it on or off and choose the AI in Edit > Preferences > AI Assistant:

| Service | What you need |
|---|---|
| Claude (Anthropic API) | an API key from console.anthropic.com |
| ChatGPT (OpenAI API) | an API key from platform.openai.com |
| Other AI (OpenAI-compatible) | the server address and model (presets for Gemini, OpenRouter, DeepSeek, Groq, Mistral, Ollama, LM Studio) and a key if the service needs one |
| Claude account | Claude Code installed and signed in once (`claude`); no key |
| ChatGPT account | Codex installed and signed in once (`codex`); no key |

The chat has three sizes: the round chat head (minimised), a small chat box that opens from it, and a
side panel on the right (expand button). The assistant sees a summary of the open model (materials,
coordinates, water table, results). Its changes are checked like your own input, come as one undo
step, and it never invents a factor of safety: it asks GeoLab to solve and reports the result.

### AI Slope Builder
Needs an Anthropic API key: paste it in the dialog (optionally remembered) or set `ANTHROPIC_API_KEY`.
It uses `claude-opus-5-5` with a strict JSON schema; the reply is validated (polygons, materials, ranges)
before it becomes a project, and the model's assumptions are shown to you. Always review the values.

### Command line
```bash
geolab solve project.slab --save --pdf report.pdf --csv slices.csv
```
(or `python -m geolab solve ...`). The report is printed to the terminal.

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
| `geolab/model.py` | Project data model and serialization |
| `geolab/geometry.py` | Polygons, ground profile, validation |
| `geolab/slope.py` | Method of slices, GLE solver, searches, probability |
| `geolab/seep.py` | Mesh generator and FE seepage solver |
| `geolab/solver.py` | Runs analyses in parent/child order, pre-solve checks |
| `geolab/ai.py` | Claude integration |
| `geolab/ui/` | Qt main window, canvas, dialogs, rendering, PDF |
| `tests/` | Benchmarks and unit/GUI tests |

GitHub Actions (`.github/workflows/build.yml`) tests and builds on Windows and macOS for every push.
For a tag such as `v1.0.0` it also builds the Windows installer (Inno Setup, `installer/geolab.iss`),
the portable zip, the Android APK and the iOS IPA (Capacitor project in `mobile/`), and attaches them
all to the GitHub release.

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
