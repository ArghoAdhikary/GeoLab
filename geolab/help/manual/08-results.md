# 8. Results, reports and exchange

## 8.1 Results view

Ctrl+2 switches to the Results view. The Results toolbar chooses the contour field and, for transient
analyses, the time step. Click anywhere in the drawing to read every value at that point. View options
draw the mesh, flow vectors, the deformed mesh, yielded zones, slices and trial slip surfaces.

## 8.2 Graphs and reports

* **View > Graph**: load steps, settlement in time, input motion, Newmark displacement, sensitivity, or
  the history of the clicked point in a transient analysis.
* **View > Report** (Ctrl+R): every input and result as text, ready to copy.
* **View > Slice Information**: the forces on each slice of the critical surface.

## 8.3 Printing and export

| Command | Output |
|---|---|
| File > Export > PDF (Ctrl+E) | Drawing with a title block, then the report |
| File > Print (Ctrl+P), View > Page Layout | Print the same pages |
| File > Export > Image (PNG), Edit > Copy Image | The drawing as a picture |
| File > Export > Results (CSV) | Nodal results for a spreadsheet |
| File > Export > Project (JSON) | The model as text |
| File > Export > GeoStudio Project (.gsz) | Slope stability and seepage analyses for GeoStudio |

## 8.4 GeoStudio files

**File > Open** reads GeoStudio .gsz files: geometry, materials, piezometric lines, boundary conditions and
SLOPE/W, SEEP/W and SIGMA/W analyses. The export writes slope stability and seepage (steady and transient)
analyses with their boundaries. Items GeoStudio cannot take from GeoLab (structures, construction stages,
rapid drawdown settings, dynamic, thermal, transport and air analyses, results) are listed when exporting.
GeoStudio creates the mesh again when the file is opened there.
