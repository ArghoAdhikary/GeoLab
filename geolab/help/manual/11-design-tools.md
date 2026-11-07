# 11. Design tools

GeoLab 2.10 adds tools that answer design questions directly. They are in the **Design** and **Tools**
menus and work with the model that is open.

## Design codes: Australian Standards and BNBC 2020

**Design > Design Code Check** (Ctrl+Shift+K). New projects use **Australian Standards**. You can switch to
the **Bangladesh National Building Code 2020 (BNBC)**, or to *No code*, for each project.

| | Australian Standards (default) | BNBC 2020 |
|---|---|---|
| Minimum F, long term | 1.5 | 1.5 |
| Temporary / end of construction | 1.3 | 1.3 |
| Earthquake (pseudo-static) | 1.1 | 1.1 |
| Rapid drawdown | 1.3 | 1.3 |
| Limit state check | AS 4678: c' × φuc, tan φ' × φuφ, live load × 1.5, F ≥ 1.0 | — |
| Seismic hazard | AS 1170.4: kp, Z, site class Ae–Ee, kpZ ≥ 0.08 | Zones 1–4 (Z = 0.12–0.36), site class SA–SE, importance I–IV |
| Design PGA | kp Z Ch(0) | 2/3 Z I S |
| Bearing | φg = 0.5 on the ultimate capacity | FS = 3.0 on the ultimate capacity |

GeoLab picks the **design case** of each slope analysis from its settings:

- **Rapid drawdown** when drawdown is switched on.
- **Earthquake** when kh or kv is not zero.
- **Temporary** when the name or description says *temporary*, *construction* or *undrained*.
- **Long term** otherwise.

![Design code check with BNBC 2020](img/code_check.png)

You can also choose the case yourself. The pseudo-static coefficient is kh = 0.5 × PGA by default (the
fraction can be changed). **Put this kh in the earthquake analyses** writes kh into your model. If no
analysis has an earthquake load yet, it adds an earthquake copy of your slope analysis.

These values are what GeoLab uses by default; you can change any of them. The project specification and
the published standard always come first.

## What-if sliders

**Design > What-If Sliders** (Ctrl+Shift+W) opens a window with sliders for:

- the water table level
- the crest loads
- cohesion and tan φ
- the earthquake coefficient kh
- Ru

When you move a slider, the factor of safety and the critical slip surface update in under a second. The
colour shows whether the code minimum is met. Nothing changes in your model until you press **Use in the
model**.

![What-if sliders](img/whatif.png)

How it works: after a solve, GeoLab keeps the 30 most useful slip surfaces of the search (the lowest
ones, plus a spread of others) and re-evaluates only those. Solve again for the final answer.

## Design optimizer

**Design > Design Optimizer** (Ctrl+Shift+O): enter the factor of safety you need and what you may change.

| Change | Finds |
|---|---|
| Slope steepness | the steepest slope (H:1V) that still gives the target (Quick Slope models) |
| Berm width | the narrowest bench at mid-height (Quick Slope models) |
| Lower the water table | the drainage depth needed |
| Reinforcement length / capacity | how much longer or stronger the nails, anchors or geosynthetics must be |
| Largest crest load | the load the crest can carry with the target F |

The answer is checked with a full slip-surface search at the end. **Use this design** puts it in the
model. For the geometry changes, it opens the redesigned Quick Slope model.

## Back-analysis

**Design > Back-Analysis**: a slope that failed had F = 1 when it failed. Choose the material and the
parameter (c', φ' or unit weight). GeoLab finds the value that gives F = 1.0, or any target you enter.

One failure is not enough to find both c' and φ'. Many (c', φ') pairs give F = 1, so GeoLab lists the
line of pairs that do. A laboratory friction angle, or a second failed section, then picks one point on
that line.

**Tools > Calibrate k from Piezometers** does the same for seepage. It changes the hydraulic conductivity
of the materials you tick until the computed heads match the measured ones (least squares).

## Liquefaction

**Design > Liquefaction Check**. It works from SPT N values or cone (CPT) readings:

| Method | Steps |
|---|---|
| SPT: Idriss & Boulanger (2014) | fines correction, CN, MSF, Kσ, rd |
| CPT: Robertson & Wride (1998) | Ic, Qtn,cs, Kc |

The result gives:

- the factor of safety against liquefaction at each depth (below 1.0 liquefies, 1.0–1.25 is marginal)
- the Iwasaki liquefaction potential index (LPI)

Layers that are not checked:

- above the water table
- clay-like: PI ≥ 7 for SPT, Ic > 2.6 for CPT

The PGA comes from the design code. Press **Put in the design report** to keep the result for the report.

## Boreholes and CPT

**Tools > Import Boreholes / CPT** reads CSV or Excel (.xlsx) logs:

- **Borehole log**, one row per layer: `hole, x, ground, top, bottom, soil, N, fc, pi, gamma`.
- **CPT**, one row per reading: `hole, x, ground, depth, qc, fs, u2`. qc can be in kPa or MPa.

The soil can be a name or a USCS symbol (AS 1726), such as *CH* or *SM*. GeoLab:

- joins the units between the holes along the section
- estimates the soil parameters (see the table below)
- builds the regions, the water table and a slope analysis with the slip search set

| Soil | From SPT N | From CPT |
|---|---|---|
| Sand | φ' = √(15.4 (N1)60) + 20 (Hatanaka & Uchida) | φ' = 17.6 + 11 log Qtn (Kulhawy & Mayne) |
| Clay | Su = 5 N (Stroud) | Su = (qt − σv) / 14 |
| All | unit weight and k from N and fines | unit weight and k from Robertson |

Check these correlations against laboratory tests.

## Rainfall from weather data

**Tools > Rainfall from Weather Data** gets the real daily rainfall and the FAO reference evaporation
(ET0) of any place and period from the free **Open-Meteo** archive. Only the coordinates and the dates are
sent.

Other ways to give the rainfall:

- a CSV file of `date, rain, et0` in mm/day
- a design storm, for example 500 mm in 5 days

**Use in the model** puts the series on the climate boundary of the transient seepage analysis. Solve, and
the slope stability analysis below it gives F at the end of the season. Graph the factor of safety
against time to see when the slope is at its weakest: this is the basis of landslide early warning for
hill slopes in the monsoon.

## Monitoring data

**Tools > Monitoring Data** imports instrument readings from a CSV file:
`instrument, kind, x, y, time, value`.

- `kind` is one of `head`, `pore_pressure`, `settlement`, `displacement_x`, `displacement_y`.
- `time` is written like `30 d`.

GeoLab compares each reading with the analysis at the same place and time and gives the RMS error. The
readings are saved in the project. From there, **Calibrate k** fits the model to the piezometers.

## Model from a photo or sketch

**Tools > Model from Photo or Sketch (AI)**: choose a photo of a slope or river bank, or a picture of a
hand sketch or a drawing. Claude reads the picture and builds the model. Dimensions written on the
picture help. Without them, the AI estimates the scale and lists every assumption.

This needs your Anthropic API key (Edit > Preferences > AI Assistant), and the picture is sent to
Anthropic.

## Design report (Word / PDF)

**Design > Design Report** (Ctrl+Alt+R) writes one document of the whole project. It has:

- the project data and the materials
- a picture and the key results of every solved analysis
- the design code check, with pass or fail for each item
- the liquefaction and monitoring results, if you made them
- the detailed analysis reports, in an appendix

Save it as Word (.docx, which Word, LibreOffice and Google Docs can edit) or as PDF.

## River banks and flood embankments

- **File > New River Bank**: a bank with a clay top over fine sand and a scour hole at the toe. It has
  three analyses: high flood, rapid drawdown after the flood (the usual cause of bank failures as monsoon
  floods fall) and the flood with an earthquake.
- **File > New Flood Embankment**: a levee on soft clay, with seepage at the flood level, the stability of
  both sides, and the land side in an earthquake.

## Python console

**Tools > Python Console** (Ctrl+Shift+P) runs Python on the open model, for batch runs, parameter
studies or your own formulas. These names are ready to use:

- `project` and `analysis`
- `solve(a)` and `solve_all()`
- `refresh()`
- `np` and `geolab`

The console starts with an example that changes the cohesion and prints F. Ctrl+Enter runs the script
(or only the selected lines).

## Bangla

Edit > Preferences > Language > **বাংলা**, then restart GeoLab. The menus, buttons and step guide are then
in Bangla. Help > Bangla Getting Started is a Bangla guide to the first model.
