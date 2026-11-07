# 2. The GeoLab window

![The GeoLab window with a solved slope](img/window.png)

## 2.1 Start page

When GeoLab starts it shows the start page. The left card starts a new project: choose the units
(metric or imperial) and click the type of the first analysis, or **Quick Slope**. The right card opens a
file, a recent file or one of the built-in examples. Window > Start Page brings it back.

## 2.2 Parts of the window

| Part | Use |
|---|---|
| Menus and Standard toolbar | New, Quick Slope, Open, Save, Print, PDF, Undo / Redo, Verify, Solve, Solve All, Stop, zoom |
| Mode toolbar | Definition view (Ctrl+1), Results view (Ctrl+2), Page Layout (Ctrl+3), the Analyses and Materials dialogs, and the current material used by Draw > Materials |
| Draw toolbar (right) | Regions, Materials, Piezometric Line, Boundary Conditions, loads, reinforcement, structures, slip surface entry / exit and grid, flux sections, text, pan |
| Step guide (above the drawing) | The steps of the selected analysis; see 2.3 |
| Project Explorer (left) | The analyses as a tree (children under their parent). Click one to make it the current analysis. |
| Properties (left) | Settings of the selected analysis or region |
| Solve manager | Progress and messages of the solver |
| Status bar | Mouse coordinates, the hint of the current tool, the value under the mouse in results |

Window > Reset Window Layout puts all docks and toolbars back.

## 2.3 The step guide

![Step guide](img/step_guide.png)

The step guide is a row of numbered buttons above the drawing, for example *1 Draw the ground,
2 Soil properties, 3 Water table (optional), 4 Where it can slide, 5 Solve, 6 See the results* for a slope
analysis. A tick (✓) marks a
finished step, the blue button is the next one, and the line under it says in plain words what to do.
Click a step to open its tool. The steps change with the type of the current analysis.
View > Show Step Guide turns it off.

## 2.4 Mouse and keyboard

| Action | How |
|---|---|
| Zoom | Mouse wheel, Ctrl+= / Ctrl+-, F zooms to fit |
| Pan | Middle mouse button drag, or the Pan tool |
| Finish a line or polygon | Enter, right-click, or click the first point again |
| Cancel the current tool | Esc (returns to Select) |
| Delete a selected region | Del |
| Move a point | Select tool, drag the point |
| Type coordinates | Modify > Edit Region Points, or Edit > Go to Coordinate (Ctrl+G) |
| Undo / Redo | Ctrl+Z / Ctrl+Y |
| Verify / Solve / Solve All | F6 / F5 / Shift+F5 |
| Report | Ctrl+R |
| Quick Guide | F1 |

Drawing snaps to the grid (View > Snap to Grid) and to existing points.

## 2.5 Themes, styles, colours and fonts

The look of GeoLab is set in three layers. The View menu switches the first three settings directly:

| Setting | Choices | Where |
|---|---|---|
| Theme | Light (day), Dark (night), Auto (follows the operating system) | View > Theme |
| Interface style | Classic, Modern (rounded), Compact (more room for the drawing), Flat, Large / touch | View > Interface Style |
| Colour scheme | GeoLab blue, Ocean, Forest, Sunset, Purple, Graphite, Solarized, High contrast | View > Colour Scheme |
| Accent colour and interface font | any colour; any installed or added font and size | Edit > Preferences > Appearance |
| Any single part of the window | a background colour, a text colour and a font | Edit > Preferences > Advanced Colours & Fonts |

**Advanced Colours & Fonts** (View > Customise Colours and Fonts) lists every part of the window. Each
part has a background colour, a text colour and (where it has text) a font:

- the window title bar (Windows 11)
- the menu bar and menus
- the toolbars and tabs
- the panel title bars (Project Explorer, Properties, Solve Manager)
- the status bar and tooltips
- the step guide
- the chat head (the round button) and the chat box: title bar, conversation, your messages, the
  assistant's messages, the Send button
- the drawing area (background and grid; printing and PDF stay on white paper)

Click a colour button to choose a colour; right-click it, or press Reset, to go back to the default.
**Apply** shows the change without closing the window.

- **Add Font...** adds a .ttf or .otf file (for example a Bangla font such as Kalpurush or SolaimanLipi).
  GeoLab copies it to its own fonts folder and loads it at every start, so it can be chosen for any part.
- **Save Theme...** writes all the colours and fonts to a `.geolab-theme` file. **Load Theme...** reads
  one, for example to use the same look on another computer or to share it with a colleague.

Edit > Preferences (Ctrl+,) has four tabs: Appearance, Advanced Colours & Fonts, Files & Backup (section
2.6) and AI Assistant (chapter 9).

## 2.6 Saving, autosave and cloud backup

| Command | What it does |
|---|---|
| File > Save (Ctrl+S) | saves the GeoLab project (.slab) |
| File > Save As (Ctrl+Shift+S) | saves under a new name. The file type can be GeoLab (.slab), GeoStudio (.gsz) or PDF |
| File > Save As GeoStudio (.gsz) (Ctrl+Alt+S) | writes a GeoStudio file. The project stays linked to its .slab file, which keeps everything GeoStudio cannot hold |
| File > Export as PDF (Ctrl+Shift+E) | a PDF of the current analysis, of every analysis (drawing and report of each), or the design report |
| File > Recover Autosaved Project | opens a project autosaved before it had a file |
| File > Back Up to Cloud Drive Now | copies the project to the backup folder at once |

**Autosave is on by default** (Edit > Preferences > Files & Backup turns it off or changes it). Every 2
minutes (1 to 60), a changed project is saved:

- If the project has a file, it is saved into that file. The previous version is kept as `name.slab.bak`.
  You can choose to write only a recovery copy instead.
- If it has no file yet, a recovery copy is written to the GeoLab Autosave folder.

**Cloud backup** (off until you turn it on) puts a dated copy of the project into Google Drive, OneDrive,
Dropbox or iCloud Drive at every save and autosave. GeoLab finds the synced folders on the computer, for
example `G:\My Drive` for Google Drive for desktop. The copies go to
`GeoLab Backups\<project>\<project> 2026-11-08 1530.slab`, and the drive's own app uploads them, so no
sign-in is needed in GeoLab. You choose how many versions to keep for each project (20 by default) and how
often a copy is made (at most one every 10 minutes by default). Install Google Drive for desktop first if
the drive is not in the list.
