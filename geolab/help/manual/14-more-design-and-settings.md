# 14. More design tools and settings

GeoLab 2.13 adds more design checks: earthquake displacement, parametric studies, piles, soil nails and
anchors, geosynthetics and braced excavations. It also adds Excel export, your own templates, and
settings for reports, offline work, accessibility and the solver.

## Earthquake check: ky and Newmark displacement

**Design > Earthquake Check (ky and Newmark)** needs a solved slope analysis. It does not need an
acceleration record or a dynamic analysis.

1. GeoLab finds the **yield acceleration ky**: the horizontal seismic coefficient that brings F down to 1.
   It searches the slip surfaces of the solved analysis, so a different surface can become critical as
   the shaking grows.
2. Enter the peak ground acceleration **amax** and the magnitude **M**. amax comes from the design code
   (BNBC 2020 or AS 1170.4) when one is set in Design > Design Code Settings.
3. The permanent displacement comes from three published regressions:

| Method | Uses |
|---|---|
| Jibson (2007), eq. 6 | ky / amax |
| Jibson (2007), eq. 7 | ky / amax and M |
| Ambraseys and Menu (1988) | ky / amax |

The largest of the three sets the hazard class (Jibson and Michael 2009):

| Displacement | Hazard |
|---|---|
| Less than 1 cm | Low |
| 1 to 5 cm | Moderate |
| 5 to 15 cm | High |
| More than 15 cm | Very high |

**Put in the Design Report** keeps ky and the displacement with the analysis. The regressions scatter by
about a factor of 3. For design, run a dynamic analysis with a record for the site.

## Parametric study

**Design > Parametric Study** varies one value over a range, and optionally a second one too. It plots
F at every step and gives the value where F crosses 1.0 and your target.

You can vary:

- the water table level
- Ru
- kh and kv
- the crest loads
- every cohesion or tan φ'
- the reinforcement length and capacity
- c', φ' or the unit weight of any one material

It uses the slip surfaces of the solved analysis, so a hundred points take seconds. Tick **Full search at
every point** to run a full search at each point instead (slower). **Save Table** writes the numbers to
Excel or CSV.

## Pile design

**Design > Pile Design** works out the axial capacity of one driven or bored pile, layer by layer.

| Soil | Shaft | Base |
|---|---|---|
| Clay, driven | α Su, with API RP 2GEO α | 9 Su |
| Clay, bored | 0.45 Su (Skempton), not more than 100 kPa | 9 Su |
| Sand | K tan δ σ'v (β method, Kulhawy 1984), limited as in API | Nq σ'v, limited as in API; bored piles take half |

**Allowable capacity** = (Qs + Qb − pile weight) / FS. The uplift capacity is shown too.

For a **group**, give the rows, the columns and the spacing:

- The group efficiency is Converse-Labarre (driven piles in sand count 1.0).
- In clay, block failure is checked as well, and the lower of the two governs.
- Settlement: s = D/100 + QL/(AE) for one pile, and s × √(Bg/D) for the group.

## Soil nails, ground anchors and geosynthetics

**Design > Soil Nails, Anchors and Geosynthetics** has three tabs.

- **Soil nail wall:**
  - The nail force comes from the apparent pressure 0.65 Ka (γH + q).
  - The bar is checked in tension with FS 1.8.
  - Pullout is π D q_s, with FS 2.0.
  - Each row needs its active length (out to the Rankine plane through the toe) plus its pullout length.
  - The typical bond list fills in q_s for common soils.
  - **Use for the Model's Nails** puts the capacity and bond into the nails of the model. Then check the
    overall stability with the slope analysis.
- **Ground anchor:**
  - The bond length is T FS / (π D q_s), and at least 4.5 m.
  - The free length is at least 4.5 m.
  - The tendon is checked at 0.6 fpu.
- **Geosynthetics:**
  - Pick a generic geogrid or geotextile. Its long-term design strength is
    T_al = T_ult / (RF_ID RF_CR RF_D).
  - You can change the reduction factors. Use the manufacturer's certified values for design.
  - **Use for the Model's Geosynthetics** sets this strength on the model's geosynthetic layers.

## Braced excavation

**Design > Braced Excavation** works out the apparent earth pressure (Peck 1969) for sand, soft to
medium clay, or stiff clay. From it, it gives:

- **strut loads** for the strut depths you enter, by the hinge method, per metre of wall and per strut
- the largest wall moment
- in clay, **basal heave** by Bjerrum and Eide (FS ≥ 1.5)

## Excel, templates and the map

- **File > Export > Export Results to Excel** writes one .xlsx workbook. It has a sheet each for:
  - the project
  - the materials
  - every result
  - the design check
  - the slices of every critical slip surface
- **File > Save as My Template** saves the open project without its results as your own template. That
  keeps your usual materials, design code, units and analyses. **File > New from My Template** starts a
  new project from a template.
- **Cross-Section from Map** now has four map types: street map, satellite, topographic (contours) and
  hillshade (terrain relief).

## New settings (Edit > Preferences)

| Tab | Setting | What it does |
|---|---|---|
| Reports & Units | Company, engineer, licence, checked by, address, header, footer, logo | Printed on every design report, PDF and Word file |
| Reports & Units | Design report language | English or বাংলা: the headings and labels of the report are in Bangla |
| Reports & Units | Decimal places | Of the numbers in reports |
| Reports & Units | Units of new projects | Metric or imperial |
| Advanced | Offline mode | Turns off every internet call: map, ground levels, rain and forecasts, landslide watch, update check, online AI. A local Ollama model still works |
| Advanced | Interface size | 100 % to 200 %, after a restart |
| Advanced | Contour colours | Classic, Viridis, Cividis, blue-orange (all three safe for colour blindness) or greyscale for printing |
| Advanced | Accuracy of new analyses | Fast, Normal or Fine: slices, slip-surface search and mesh size of the analyses you add |
| Advanced | CPU cores | How many cores the solver may use on large models |

When the language is set to Bangla, the new dialogs and the preferences tabs are in Bangla as well as
the menus.
