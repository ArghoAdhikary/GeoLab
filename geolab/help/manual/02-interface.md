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

## 2.5 Themes and preferences

View > Theme chooses Light, Dark or Auto (follows the operating system). Edit > Preferences (Ctrl+,) has
two tabs: Appearance (the theme) and AI Assistant (see chapter 9).
