# 13. From the field to the design

GeoLab 2.12 adds tools that start from the site and end with a costed design, plus features that make
everyday work faster.

## Cross-section from a map

**Tools > Cross-Section from Map** (Ctrl+Alt+M) shows an OpenStreetMap map.

1. Pick a place, or drag the map and zoom with the mouse wheel.
2. Click point **A** at the top of the hill and point **B** at the toe, or type the coordinates.
3. Press **Get Ground Levels**. GeoLab reads the ground level at points along the line from the Copernicus
   90 m digital elevation model, through the free Open-Meteo service. Only the coordinates are sent.
4. Enter the soil layers: thickness below the ground, c', φ' and unit weight. Thickness 0 means down to
   the bottom of the model.
5. Press **Make the Model**.

The model gets:

- regions that follow the ground at your layer depths
- the water table, at the depth you chose
- a slope analysis with the entry and exit ranges set on the steepest part

A 90 m elevation model does not show cuttings, walls or slopes shorter than about 100 m. It is for first
checks and for finding the steepest line of a hill. Use a survey for design.

## Landslide early warning

**Tools > Landslide Early Warning** gets the rain of the last days (14 by default) and the forecast for the
next days (7, up to 16) for a place, from Open-Meteo. It then works out the factor of safety and an
alert level for each day.

| Method | How F is found |
|---|---|
| Model (best) | The rain goes on the climate boundary of your transient seepage analysis, which is solved once. The slip surfaces of the slope analysis are then checked with the pore pressures of each day. Start from File > Open Example > Rainfall and evaporation on a slope, or your own model built the same way. |
| Quick | The water table rises with the antecedent rain (a decaying sum of the daily rain, divided by the drainable porosity). The solved slip surfaces are checked at each rise. This is a screening estimate. |

Each day gets a level:

| Level | When |
|---|---|
| Red | F < 1.0, or both rain thresholds are exceeded |
| Orange | F < 1.2 |
| Yellow | F < 1.3, or one rain threshold is exceeded |
| Green | none of the above |

The default thresholds are 90 mm in one day and 150 mm in three days. They are starting values for
hill slopes, not a national standard, so set them for your site.

Tick **Check again every 6 hours** to keep watching while GeoLab is open. If the level gets worse, GeoLab
shows a notification.

## Probabilistic analysis and sensitivity

**Design > Probabilistic Analysis and Sensitivity** needs a solved slope analysis.

c', φ' and the unit weight of each material vary around their values. The spread is the material's
standard deviation, or the COV you enter when none is set. The water table level can vary too. Each
trial is checked on the lowest slip surfaces of the search, so a different surface can become critical.

The result gives:

- the probability of failure, Pf = P(F < 1)
- the mean and standard deviation of F
- the reliability index β, normal and lognormal, with the US Army Corps of Engineers performance level
- a histogram of F
- a **tornado chart**: how far F moves when each parameter goes to its mean ± one standard deviation.
  The widest bar is the parameter that most needs good testing.

**Put in the Design Report** keeps the result with the analysis.

The analysis settings also have a Monte Carlo option, which runs on the critical surface only.

## Foundations and retaining walls

**Design > Foundations and Retaining Walls** has four tabs:

| Tab | What it does |
|---|---|
| Bearing capacity | General equation with Vesic, Hansen or Meyerhof factors, shape, depth and load inclination factors, and the water table. Undrained (φ = 0) uses Nc = 5.14. Checked with the project's design code: φg = 0.5 (Australian Standards) or FS = 3 (BNBC). |
| Settlement | Immediate (elastic) plus primary consolidation (Cc, Cr, e0, preconsolidation pressure) with the 2:1 stress spread, layer by layer |
| Retaining wall | Cantilever or gravity concrete wall: Rankine or Coulomb thrust, surcharge, water behind the wall and uplift. Checks sliding (1.5), overturning (2.0), bearing on the effective width (3.0) and the middle third. |
| Cantilever sheet pile | Embedment in sand by the simplified free-earth method (+20 %), and the maximum bending moment |

These are hand-calculation checks. For walls in a slope, model them with Define > Structures and a stress
analysis.

## Strength from laboratory tests

**Tools > Strength from Lab Tests** fits the Mohr-Coulomb line to test results. Paste one specimen per
line:

| Test | Each line |
|---|---|
| Triaxial CD / CU (effective stresses) | σ3, σ1 at failure, pore pressure u |
| Triaxial (total stresses) | σ3, σ1 at failure |
| Triaxial UU | σ3, σ1 at failure; gives Su |
| Direct shear | σn, τ at failure |

The result gives c', φ' and R², with a plot of the Mohr circles and the failure line. **Use for Material**
puts the values in a material. Tick **Force c' = 0** for sands and normally consolidated clays.

## SWCC and k from the grain size

**Tools > Estimate SWCC and k from Grain Size** estimates the hydraulic properties of a material:

- **Sands and gravels:** the Modified Kovács model from D10, D60 and the void ratio, fitted with van
  Genuchten. k comes from Chapuis (2004).
- **Silts and clays:** the average van Genuchten curve and k of the soil type (Carsel & Parrish 1988),
  from the USCS symbol or the liquid limit.

**Use for Material** sets the hydraulic model to van Genuchten with these values. Test results are
always better.

## Quantities, cost and comparing options

**Design > Quantities and Cost** works per metre run of the section, or for the length you enter. It
gives:

- the area and volume of each material
- the reinforcement length
- the length of walls and piles
- cut and fill against an existing-ground project file, if you give one

Enter your own unit rates in any currency. The defaults are only placeholders.

**Design > Compare Design Options** puts the open project and any saved project files side by side. Each
slope analysis gets one row with:

- F and the code minimum
- pass or fail
- Pf, if you ran it
- the cost

Options that are not solved yet are solved first.

## AutoCAD DXF

- **File > Import AutoCAD DXF** reads ASCII DXF files:
  - Closed polylines, or lines that meet end to end, become regions, one material per layer.
  - A polyline on a layer named *water*, *piezo* or *GWL* becomes the water table.
  - Give the drawing unit: 1 for metres, 0.001 for millimetres.
  - Explode arcs and splines in CAD first.
- **File > Export > Export AutoCAD DXF** writes R12 DXF, which every CAD program opens. It contains:
  - the regions, one layer per material
  - the water table
  - the reinforcement and structures
  - the critical slip surface with its factor of safety

## Working faster

| Feature | Where | What it does |
|---|---|---|
| Command palette | Ctrl+K | Type part of any command's name and press Enter |
| Project tabs | File > New Tab (Ctrl+T), Open in New Tab (Ctrl+Alt+O), Close Tab (Ctrl+W) | Several projects in one window; each keeps its own undo history |
| History panel | Window > History | Every change in order; click one to go back to it |
| Version history | File > Version History (Ctrl+Shift+H) | The file, the previous save (.bak), the autosave and every cloud backup. Compare one with the open project, open it in a tab, or restore it |
| Own shortcuts and toolbar | Tools > Keyboard Shortcuts and My Toolbar | Change any shortcut (clashes are refused) and choose the buttons of the My Tools toolbar |
| Start page pictures | Start page | Recent projects show a small picture |
| Crash recovery | automatic | After an unexpected error the project is saved to the autosave folder. If GeoLab did not close normally, it offers the autosaved copies at the next start |
| Update check | Help > Check for Updates; once a day by itself | Tells you when a new version is out and opens the download for your computer |
| Share a report | File > Share Report | Writes the design report as one HTML file, with the pictures inside, to the cloud drive folder. Share it from Google Drive or OneDrive with a link; Google Drive lets readers add comments |

## Mobile

- **Colours and language:** the mobile app's menu has the colour schemes and English / বাংলা.
- **Moving projects between computer and phone:**
  1. On the computer, turn on the cloud backup (Edit > Preferences > Files & Backup), or save into the
     Google Drive folder.
  2. On the phone, use Open file and pick the project from Google Drive.
  3. Save / share sends it back.

## Mac

The Mac app comes in two builds, one for Apple Silicon (M1–M4) and one for Intel Macs. The easiest way to
install or update it is one command in Terminal:

```
curl -fsSL https://raw.githubusercontent.com/ArghoAdhikary/GeoLab/main/install-mac.sh | bash
```

This command:

- picks the right build for the Mac
- puts GeoLab in Applications
- lets macOS open it, since GeoLab is not signed with a paid Apple certificate
