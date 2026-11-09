# Changelog

## 2.14.0 - 2026-11-09

### New analyses (as in GeoStudio SLOPE3D, SEEP3D, QUAKE/W and SIGMA/W)

- **3D slope stability:** ellipsoidal slip surfaces on the section extruded over a width, 3D Bishop
  simplified (Hungr 1987), trial slide lengths, a slide centre, and crest loads over part of the width.
  Pore pressure from a piezometric line, or from a 2D or 3D seepage analysis.
- **3D seepage:** the mesh extruded into wedge elements, steady or transient, saturated / unsaturated.
  Boundary conditions can act over part of the width. Wells can have a fixed head or a pumping rate.
- **Axisymmetric seepage:** flow to wells, tanks and shafts. Checked against Thiem's equation.
- **Liquefaction in dynamic analysis:** excess pore pressure from the cyclic stresses (cycle counting,
  Seed et al. 1976 ru curve), liquefied zones, and the shear modulus softening with ru.
- **Stability after an earthquake:** a slope child of a dynamic analysis can add its excess pore
  pressure.
- **Interface elements:** a thin layer with shear and normal stiffness that slips on adhesion and
  friction angle, for walls, piles and weak seams.

### Viewing

- **View > 3D View:** the extruded model, the 3D slip surface, the water table across the width and the
  wells, turned with the mouse.
- **View > 3D Section (z):** show any section of a 3D seepage analysis.
- The design report gives the 3D factor of safety, the well flows and the liquefied area.

## 2.13.0 - 2026-11-08

### Design

- **Earthquake check:** the yield acceleration ky of a solved slope, and the Newmark displacement from
  Jibson (2007) and Ambraseys and Menu (1988), with a hazard class. No dynamic analysis is needed.
- **Parametric study:** vary one or two values (water table, kh, loads, strength, any material property),
  plot F and find where it crosses 1.0 and the target. The table saves to Excel or CSV.
- **Pile design:** driven and bored piles in clay and sand (API alpha, beta method, API limits), pile
  groups (Converse-Labarre, block failure) and settlement.
- **Soil nails, ground anchors and geosynthetics:** nail wall design (apparent pressure, tension,
  pullout, active zone, length), anchor bond and tendon checks, and a library of generic geogrids and
  geotextiles with their reduction factors. Each design can be put into the model's reinforcement.
- **Braced excavations:** Peck apparent pressure for sand and soft or stiff clay, strut loads by the hinge
  method, and basal heave (Bjerrum and Eide).

### Files and reports

- **Export Results to Excel** (.xlsx): project, materials, results, design check and critical slices.
- **My templates:** save a project as a template and start new projects from it.
- **Report branding:** company, engineer, licence, checked by, address, header, footer and logo on
  every design report.
- **Design report in Bangla.** Decimal places can be set.
- **Map:** satellite, topographic and hillshade layers as well as the street map.

### Settings

- **Offline mode:** one switch turns off every internet call.
- **Accessibility:** interface size from 100 to 200 %, and colour-blind-safe and greyscale contour colours.
- **Solver:** Fast / Normal / Fine accuracy for new analyses, and how many CPU cores to use.
- Units of new projects.
- More of the desktop app in Bangla: the new dialogs and the preferences.

## 2.12.0 - 2026-11-08

### From the site

- **Cross-section from a map:** click two points on an OpenStreetMap map. GeoLab gets the ground levels
  (Copernicus 90 m DEM through Open-Meteo) and builds the slope model with your soil layers and water table.
- **Landslide early warning:** past rain and the 7-16 day forecast give F and a green / yellow / orange /
  red alert for each day. It can use your transient seepage model or a quick water table rise, and it can
  check every 6 hours while GeoLab is open.
- **Strength from lab tests:** triaxial (CD, CU with u, UU) and direct shear give c', phi' and R^2, with
  Mohr circles.
- **SWCC and k from the grain size:** Modified Kovacs and Chapuis for sands, and Carsel & Parrish for
  silts and clays.
- **AutoCAD DXF** import (closed polylines or lines to regions, layers to materials) and export (R12,
  with the slip surface).

### Design

- **Probabilistic analysis** on the lowest slip surfaces: Pf, reliability index, histogram and a tornado
  sensitivity chart.
- **Foundations and retaining walls:** bearing capacity (Vesic, Hansen, Meyerhof) with the code check,
  settlement, cantilever / gravity walls, cantilever sheet piles.
- **Quantities and cost** (materials, cut and fill, reinforcement) and **Compare Design Options** (F,
  pass or fail, Pf and cost side by side).

### Working faster

- Command palette (Ctrl+K), project tabs (Ctrl+T), a History panel of every change, Version History
  (the file, .bak, autosave and cloud backups, compared and restored).
- Your own keyboard shortcuts and "My Tools" toolbar.
- Pictures of recent projects on the start page.
- Crash recovery and an update check.
- Share Report: one HTML file in the cloud drive folder, ready to share with a link.

### Mobile

- Colour schemes and Bangla in the mobile app.

## 2.11.1 - 2026-11-08

- **Mac fixed:** the Mac app was built only for Apple Silicon and was blocked by Gatekeeper. There are now
  two builds, `GeoLab-macos-apple-silicon.zip` and `GeoLab-macos-intel.zip`. Both are signed for local use
  and opened, solved and checked on a Mac during every build.
- New one-line Mac installer: `curl -fsSL https://raw.githubusercontent.com/ArghoAdhikary/GeoLab/main/install-mac.sh | bash`.
- Drawings, PDF and chat use Helvetica Neue on macOS instead of the missing Segoe UI.

## 2.11.0 - 2026-11-08

### Looks

- **Interface styles:** Classic, Modern (rounded), Compact, Flat and Large / touch.
- **Colour schemes:** GeoLab blue, Ocean, Forest, Sunset, Purple, Graphite, Solarized and High contrast,
  each with a day and a night version, plus your own accent colour.
- Both are in the View menu and in Edit > Preferences > Appearance, with an interface font and size.
- **Advanced Colours & Fonts:** a background colour, a text colour and a font for every part of the
  window: title bar (Windows 11), menu bar, menus, toolbars, panel title bars, tabs, status bar,
  tooltips, step guide, the chat head and every part of the chat box, and the drawing area.
- **Add Font:** add .ttf / .otf fonts (for example Bangla fonts). Themes can be saved to and loaded from
  a .geolab-theme file.

### Files

- **Autosave, on by default:** every 2 minutes, into the project file (the previous version kept as .bak),
  or to a recovery copy for new projects. File > Recover Autosaved Project opens those.
- **Cloud backup:** dated copies to Google Drive, OneDrive, Dropbox or iCloud Drive (the synced folder is
  found automatically), with the number of versions to keep.
- **Save As GeoStudio (.gsz)** in the File menu, and .gsz and PDF as file types in Save As.
- **Export as PDF:** the current analysis, every analysis in one PDF, or the design report.

## 2.10.0 - 2026-11-07

### Design codes

- Design > Design Code Check covers Australian Standards (the default for new projects) and BNBC 2020.
  - Minimum factors of safety for the long-term, temporary, earthquake and rapid drawdown cases.
  - The AS 4678 limit state check: soil uncertainty factors on c' and tan(phi'), live load x 1.5.
  - The seismic coefficient from AS 1170.4 (kp, Z, site class) or BNBC 2020 (zone, site class,
    importance), which can be written into the earthquake analyses.

### New design tools

- **What-if sliders:** move the water table, loads, strength or kh, and the factor of safety and slip
  surface update in under a second.
- **Design optimizer:** finds the smallest change that reaches a target F (slope steepness, berm, drainage,
  reinforcement length or capacity), or the largest crest load that still meets the target.
- **Back-analysis:** the strength that explains an observed failure (F = 1), and the line of (c', phi')
  pairs that do. Tools > Calibrate k from Piezometers does the same for hydraulic conductivity.
- **Liquefaction check:** SPT (Idriss & Boulanger 2014) or CPT (Robertson & Wride 1998), giving FS with
  depth and the LPI.

### Data import and AI

- **Boreholes and CPT:** import logs from CSV or Excel, estimate parameters from N or the cone, and build
  the cross-section automatically.
- **Rainfall:** real daily rainfall and evaporation of any place (Open-Meteo archive), a CSV file or a
  design storm, put on the climate boundary.
- **Monitoring data:** import piezometers, settlement plates and inclinometers, and compare them with the
  model (RMS error).
- **Model from a photo or sketch:** Claude reads the picture and builds the model.

### Templates, reports and other additions

- **River bank and flood embankment templates:** File > New River Bank (flood, rapid drawdown, toe scour,
  earthquake) and File > New Flood Embankment (levee on soft clay).
- **Design report:** a Word (.docx) or PDF report with pictures, results, the code check, liquefaction
  and monitoring.
- **Python console:** Tools > Python Console for scripting the open model.
- **Bangla interface:** Edit > Preferences > Language. The menus, buttons and step guide are translated,
  and there is a Bangla getting-started chapter.
- Quick Slope can now add a berm and a scour hole at the toe.
- The manual has two new chapters (design tools, Bangla) and three new tutorials (river bank with BNBC,
  back-analysis and redesign, flood embankment with the code check and the report).

## 2.9.0 - 2026-11-07

- User manual (GeoLab-User-Manual.pdf, 40 pages with screenshots) and ten step-by-step tutorials: first
  slope, Quick Slope, earth dam, reservoir drawdown, strip footing, consolidation, anchored excavation,
  earthquake, rainfall, and frost / contamination / air flow. Every number a tutorial quotes is checked
  against the program by the automated tests.
- Help > User Manual (Shift+F1) and Help > Tutorials open a help window that stays beside the drawing;
  each tutorial has a button that opens its model. Help > User Manual (PDF) opens the PDF.
- Help > Example Files Folder puts every example, already solved, in Documents / GeoLab Examples. The
  examples are also a release download (GeoLab-examples.zip).
- Windows: the Intel oneAPI Math Kernel Library (MKL) PARDISO parallel sparse solver for large systems
  (more than 30 000 unknowns). It factorises 5 to 8 times faster than SuperLU there; a fine-mesh
  consolidation model solves in 13 s instead of 62 s. Smaller systems keep SciPy's SuperLU, which is the
  faster of the two at that size. Help > About shows the solver.
- Start page: links to the tutorials and the manual.

## 2.8.0 - 2026-11-07

- Staged construction for stress-deformation: each stage can leave out regions (excavated or not built
  yet). Dug-out soil releases its stresses, new fill adds its weight (Analysis settings > Construction Stage).
- Structural elements: walls / beams, anchors / struts (with prestress) and geogrids (tension only),
  drawn with Draw > Structures and chosen per stage; axial force and bending moment in the results.
- Hardening Soil model; nonlinear load steps are cut automatically when they do not converge.
- Elastic-plastic coupled consolidation, with stages and structures.
- Seepage: plant transpiration and root depth on climate boundaries (Feddes root water uptake).
- Slope: rapid drawdown by the three-stage Duncan, Wright and Wong method (R envelope per material).
- Switching metric / imperial now converts every value.
- GeoStudio export: SEEP/W analyses and hydraulic boundaries; total head is now written as GeoStudio's
  HydHeadvsTime (the old name was not recognised by GeoStudio).
- Beginners: step guide above the drawing, File > New Quick Slope, Quick Slope on the start page,
  tooltips on all drawing tools, a longer Quick Guide.
- New examples: Anchored excavation (staged), Rapid drawdown (Duncan-Wright-Wong).

## 2.7.0 - 2026-11-06

- The app is now called **GeoLab** (was StrataLab). Project files keep the .slab extension, and old StrataLab settings are copied over on first start.
- Windows installer (GeoLab-Setup.exe) and portable version (GeoLab-windows-portable.zip, settings kept next to the program).
- GeoLab Mobile for Android (.apk) and iOS (.ipa): the same analysis engine running on the phone.

## 2.6.0 - 2026-11-06

- AI Assistant chat. A round chat head sits in the bottom-right corner; clicking it opens a small chat
  box, which expands into a side panel on the right and minimises back to the chat head. The assistant
  builds slope models (several at once, extra ones in new windows), edits the open model (materials,
  water table, method, surcharges, seismic load, title), solves it and reports the factor of safety.
  Every change is validated and undoable in one step.
- The assistant works with any AI: Claude (Anthropic API key), ChatGPT (OpenAI API key), any
  OpenAI-compatible service (Google Gemini, OpenRouter, DeepSeek, Groq, Mistral, Ollama, LM Studio)
  or a Claude / ChatGPT account through the Claude Code or Codex command line app, with no API key.
- Edit > Preferences: turn the chat on or off, choose the AI service, model, key or server address,
  and test the connection.
- Light (day), Dark (night) and Auto themes (View > Theme or Preferences). Auto follows the operating
  system and switches live. The drawing, start page, icons and chat follow the theme; printing and PDF
  stay on white paper.

## 2.5.1 - 2026-11-06

- Entry and exit slip surface search now matches GeoStudio SLOPE/W: each trial circle slides only
  along its arc between the entry and exit points (a large circle that dips below the ground again
  beyond the toe no longer drags that extra length into the sliding mass), and radius increments
  are spaced by evenly increasing arc depth below the entry-exit chord. The example Slope project now
  gives F = 1.224 against GeoStudio's 1.225, with the same critical circle.
- Tension crack: the crack now forms where the slip surface is at least the crack depth deep (it was
  checked one slice too far towards the crest).

## 2.5.0 - 2026-11-06

- GeoStudio slope stability (SLOPE/W) projects open and solve: limit equilibrium method, piezometric
  line and which materials use it, pore pressure source, entry and exit ranges with their increments,
  direction of movement and seismic coefficients. Slope analyses, Mohr-Coulomb strength and these
  settings are also written on export; GeoStudio's GeoCmd reads the exported file with nothing dropped.
- Window layout reorganised: File, Edit, View, Define, Draw, Sketch, Modify, Window and Help menus;
  Definition / Results / Page Layout buttons; drawing tools in a toolbar down the right side; status
  bar with the cursor coordinate (type x, y to go there), grid and snap toggles, zoom and the drawing
  scale. Solve Manager, Verify and Solve are under Window and on the toolbar.
- Page Layout: print preview of the drawing and results pages.
- Slope analysis settings in tabs: Settings (method, side function, pore pressures, seismic, unit
  weight of water), Slip Surface (search and tension crack), Optimization, Distribution
  (probabilistic and sensitivity) and Convergence (slices, minimum depth). Analysis Type chooses
  Limit Equilibrium or Finite Element Stress-based.
- Slip Surface Entry and Exit Range window (Draw menu, and after drawing the ranges): left and right
  ranges with X, Y read from the ground, increments and radius increments; the higher range is the
  entry.

## 2.4.0 - 2026-11-06

- New home page inside the main window: **New** (choose units template, geometry dimension and the
  analysis type to start with), **Open** (recent projects and examples) and getting-started links.
  Docks and toolbars appear once a project is open.
- New **Define Analyses** window (Define > Analyses, or double-click an analysis): the analysis tree
  on the left with Add and Delete, and the selected analysis on the right with Name, Parent,
  Analysis Type and Description above its settings tabs. Time settings have their own tab and are
  greyed out for steady-state and in situ analyses. Edits apply together on OK and can be undone.
- In situ stress analyses can use the **K0 procedure** as well as gravity activation:
  sigma'v from the weight of the soil above, sigma'h = K0 sigma'v.
- Stress analyses label pore pressures as "Final PWP conditions from": none, parent analysis or
  piezometric surface.
- Painted icons for each analysis type.

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
