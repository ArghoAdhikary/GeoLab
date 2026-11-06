# 1. Introduction

GeoLab is a 2D geotechnical analysis program. One project holds one cross-section (geometry, materials,
boundary conditions) and any number of analyses that share it:

| Analysis | What it computes |
|---|---|
| Slope stability | Factor of safety of slip surfaces by limit equilibrium (Ordinary, Bishop, Janbu, Spencer, Morgenstern-Price, Corps of Engineers, Lowe-Karafiath, Sarma) or from finite element stresses; probability of failure; rapid drawdown; Newmark earthquake displacement |
| Seepage | Steady and transient groundwater flow, saturated and unsaturated, seepage faces, rainfall, evaporation and plant transpiration |
| Stress-deformation | In situ stresses, load-deformation, staged excavation and fill, walls, anchors and geogrids, strength reduction factor of safety, coupled consolidation |
| Dynamic | Earthquake response, linear or equivalent linear |
| Thermal | Heat transfer with freezing and thawing |
| Contaminant transport | Advection, dispersion, adsorption and decay, particle tracking |
| Air flow | Air pressure and flow in dry or partly saturated soil |

Analyses are linked by **parents**: a slope stability analysis can take its pore water pressures from a
seepage analysis, a load stage starts from the stresses of the in situ stage, and so on.

## 1.1 Downloads

Every release on GitHub (https://github.com/ArghoAdhikary/GeoLab/releases) has:

| File | Use |
|---|---|
| GeoLab-Setup.exe | Windows installer. Start menu entry, desktop icon, opens .slab files, uninstaller. |
| GeoLab-windows-portable.zip | Windows without installing: unzip anywhere (also a USB stick) and run GeoLab.exe. Settings are kept in GeoLab.ini next to the program. |
| GeoLab-macos.zip | macOS app. The app is not notarized: right-click it and choose Open the first time. |
| GeoLab-android.apk | Android phone or tablet. Allow installing apps from this source when Android asks. |
| GeoLab-ios-unsigned.ipa | iPhone / iPad, unsigned. It must be signed with your own Apple account (for example with AltStore or Xcode) before it can be installed. |
| GeoLab-User-Manual.pdf | This manual. |
| GeoLab-examples.zip | All example projects, already solved. |

The Windows programs also contain this manual (Help > User Manual), the tutorials (Help > Tutorials) and
the example files (Help > Example Files).

## 1.2 Files

| Extension | Content |
|---|---|
| .slab | A GeoLab project: geometry, materials, analyses and (optionally) their results. It is a zip file holding project.json. |
| .gsz | A GeoStudio project. GeoLab opens SLOPE/W, SEEP/W and SIGMA/W models and can export slope and seepage models to GeoStudio (File > Export). |
| .json | The project as plain text, for scripts and version control. |

## 1.3 The solver and the maths libraries

All finite element analyses (seepage, stress, consolidation, dynamic, thermal, transport, air flow) build a
sparse system of equations and solve it with a direct sparse solver. GeoLab picks the faster one for the
size of the system:

* **Up to 30 000 unknowns** (most 2D models): SciPy's **SuperLU**. On systems this size it factorises
  about as fast as anything and its repeated solves are the quickest.
* **Above 30 000 unknowns** (fine meshes), on Windows: the **Intel oneAPI Math Kernel Library (MKL)
  PARDISO** solver, a parallel direct solver that uses all processor cores. It factorises 5 to 8 times faster
  than SuperLU at 50 000 to 200 000 unknowns; a fine-mesh consolidation model (7 100 nodes, 30 time steps)
  solves in 13 s instead of 62 s. MKL is part of the Windows program, which is why that download is larger.

macOS and the phone app always use SuperLU (MKL does not run on Apple silicon or in the phone's Python
engine). Both solvers give the same answer to round-off. Help > About shows whether MKL is available. To
switch MKL off, set the environment variable `GEOLAB_SOLVER=superlu` before starting GeoLab.

NumPy (with OpenBLAS) does the element calculations; limit equilibrium slope stability is vectorised with
NumPy and does not need a sparse solver.

## 1.4 How accurate is it?

Every method is checked against closed-form solutions and published benchmarks in the automated tests
(the list is in FEATURES.md in the source code). Examples: the ACADS 1(a) slope gives F = 0.99 (reference
about 1.0), a strip footing on clay fails near 5.14 su, consolidation follows Terzaghi's 1D theory, a
cantilever wall bends as P L³ / 3 EI. Still, as with any program, **check every input and judge whether the
result is reasonable** before relying on it.
