# 15. 3D, axisymmetric, liquefaction and interfaces

GeoLab 2.14 adds analyses that GeoStudio offers in SLOPE3D, SEEP3D, QUAKE/W and SIGMA/W:

- 3D slope stability
- 3D seepage with wells
- axisymmetric seepage
- excess pore pressure and liquefaction during an earthquake, and stability after it
- interface elements that slip between a structure and the soil

## 3D models: an extruded section

In 3D the cross-section you draw is extruded over a **width** in z, from z = 0 at the front to z = width
at the back. The ground, layers and water are the same in every section across the width. The slip
surface, loads, boundary conditions and wells can vary along z.

**View > 3D View** shows the model turned in 3D. Drag the picture, or use the slider, to turn it.

## 3D slope stability

Turn it on in **Analysis Settings > 3D** of a slope analysis:

| Setting | Meaning |
|---|---|
| 3D | Use ellipsoidal slip surfaces on the extruded section |
| Width of the model in z | Width of the extrusion |
| Trial slide lengths | The lengths to try. Leave the table empty to try 1/4, 1/2, 3/4, 1 and 1.5 times the width |
| Slide centre z | Where the slide is centred. A negative value means the middle of the load band or of the width |
| Surcharges and point loads from z / to z | Limits the crest loads to part of the width, for example a building or a stockpile of finite length. Both 0 means the whole width |

The slip surface is an ellipsoid about an axis along the slope. Every section through it is a circle with
the same centre. Its radius is largest in the middle and shrinks to zero at the ends.

GeoLab first runs the usual 2D search on the section (Bishop simplified). It then tries ellipsoids of each
length about the best circles, and refines the most critical one.

The factor of safety is **3D Bishop simplified (Hungr 1987)**. The sliding mass is cut into columns, and
each column is in vertical equilibrium. The whole mass is in moment equilibrium about the axis.

The results show:

- F (3D) and the slide length
- the 2D F of the section
- F for each trial length
- the volume of the sliding mass

**Checks:**

- A very long ellipsoid gives exactly the 2D Bishop factor of safety of the section.
- Shorter slides give higher F, because the curved ends add resistance.

Pore pressure can come from a piezometric line, a 2D seepage analysis or a **3D seepage** analysis. Set
the seepage analysis as the parent.

## 3D seepage

Turn it on in **Analysis Settings > 3D / Axisymmetric** of a seepage analysis:

| Setting | Meaning |
|---|---|
| 3D | Extrude the mesh over the width into layers of wedge elements |
| Width of the model in z | Width of the extrusion |
| Element layers across the width | Number of layers in z (more layers: more accurate, slower) |
| Section shown in the results | Which section z the contours show. A negative value means the middle |
| 3D wells | One row per well: x, z, top y, bottom y, type (0 = fixed head, 1 = pumping rate), head or rate |

**Boundary conditions:** a boundary condition acts over the whole width unless you give it a range. Set
**3D: from z** and **to z** when you draw it (Draw > Boundary Condition). For example, a drain or a
river reach can cover only part of the width.

In 3D you can use these boundary conditions:

- head
- pressure head
- unit flux and total flux
- seepage face
- infiltration

**Wells:**

- A well is a vertical line at (x, z) from its top to its bottom y.
- With a fixed head, GeoLab gives the flow into the well.
- With a pumping rate (outflow +), the head around the well drops.

**Results:**

- The contours show one section at a time. Use **View > 3D Section (z)** to choose another section.
- The panel lists the flow of each well and the total inflow and outflow of the whole 3D model.

**Check:** a 3D model of a section that does not change along z gives the same heads as the 2D analysis,
and the width times the 2D flow.

## Axisymmetric seepage

Tick **Axisymmetric** in the same tab. The section then turns about the vertical axis at x = 0, so x is
the radius. Draw the model at x ≥ 0. A well is the boundary at the smallest radius.

Use it for:

- flow to a single well or a pumping test
- a circular tank or pond
- a shaft

Flows are given for the full circle.

**Check:** confined flow to a well matches Thiem's equation, Q = 2π k b Δh / ln(r2/r1), within 1.5 %.

## Pore pressure and liquefaction in an earthquake

For every material that can build up pore pressure:

1. Give the material a **cyclic resistance ratio CRR** (Materials > Dynamic). This is the ratio for 15
   uniform cycles, for example CRR7.5 from the Liquefaction (SPT / CPT) tool.
2. Give the **slope b** of the CRR vs cycles curve (about 0.34 for sands).
3. Give the shape **α** of the pore pressure curve (0.7).

Then tick **Generate excess pore pressure and check liquefaction** in the dynamic analysis settings.

During the shaking, GeoLab counts the half cycles of horizontal shear stress in every element. Each half
cycle adds damage 0.5 / N_L. N_L is the number of uniform cycles that liquefies the soil at that stress
ratio, from CRR(N) = CRR15 (N / 15)^-b. The excess pore pressure ratio follows Seed, Martin and Lysmer
(1976):

ru = (2/π) arcsin(D^(1/(2α)))

The soil liquefies (ru = 1) when the damage D reaches 1. As ru rises, the shear modulus falls with
√(1 − ru) in the next iteration.

The results show:

- the fields ru, excess pore pressure and liquefied (1 = yes)
- the largest ru
- the liquefied area

The vertical effective stress before the earthquake comes from the soil weight and the piezometric line.

## Stability after the earthquake

Make a slope analysis a child of the dynamic analysis. Then tick **After an earthquake: add the excess
pore pressure of the parent dynamic analysis** (Analysis Settings > Rapid Drawdown tab). The slope
analysis then uses the static pore pressure plus the excess pore pressure left by the shaking. This works
in 2D and in 3D.

## Interface elements

An interface is a thin layer of elements that can slip along its own direction. It sits, for example,
between a wall or a pile and the soil, or along a weak seam.

1. Draw the layer as a thin region, for example 0.05 to 0.2 m thick, along the wall.
2. Give it a material with the stress model **Interface**. Its properties are:
   - **ks**: the shear stiffness, in pressure per length of slip.
   - **kn**: the normal stiffness.
   - **adhesion c_a**.
   - **friction angle δ**: often 2/3 of φ' of the soil.

GeoLab takes the direction and thickness of the layer from its shape. Before it slips, the layer moves
τ / ks in shear. It slips when the shear stress on it reaches c_a + σ'n tan δ. There is no dilation, so
the normal stress does not change. The strength reduction method reduces the interface strength with the
soil's.

**Checks:**

- A shear box with an interface moves τ / ks.
- When the shear passes c_a + σ'n tan δ, the box keeps sliding and the analysis does not converge.

## Limits

- The 3D models are extrusions of one section. They do not use a 3D terrain or layers that change along z.
- 3D slope stability uses Bishop simplified and ellipsoids only.
- 3D seepage does not take climate boundaries.
- Pore pressure generation uses an equivalent number of cycles, not an effective-stress constitutive model.
