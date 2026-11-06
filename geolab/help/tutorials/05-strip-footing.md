<!-- example: Strip footing (stress-deformation) -->
<!-- check: Strip footing (stress-deformation) | 1 | footing_pressure | 215.1 | 0.03 -->
# Tutorial 5 — Bearing capacity of a strip footing

**Goal:** push a rigid footing into clay until it fails and compare the collapse load with theory.
**Time:** 15 minutes. **Result:** about 215 kPa; Prandtl's solution is 5.14 su = 206 kPa (4 % difference).

![Displacement under the footing](img/footing.png)

## 1. Model (half of the footing, symmetry on the left)

1. Start page: Metric, **Stress-deformation**.
2. Draw > Regions: (0, 0), (10, 0), (10, 6), (0, 6).
3. Material *Soft clay*: strength model Undrained (φ = 0), c = su = 40 kPa; stress-strain model
   Elastic-plastic (Mohr-Coulomb), E = 12 000 kPa, ν = 0.45, unit weight 17.

## 2. Supports

Draw > Boundary Conditions:

| Name | Edge | Type |
|---|---|---|
| Left side | (0, 6) → (0, 0) | Fixed x (this is also the line of symmetry) |
| Right side | (10, 0) → (10, 6) | Fixed x |
| Base | (0, 0) → (10, 0) | Fixed x and y |

## 3. Two stages

1. The first analysis: In Situ, mesh size 0.25 m.
2. Define > Add Child Analysis > Stress-deformation: Load-Deformation, 15 load steps, mesh 0.25 m.
3. Draw > Boundary Conditions along (0, 6) → (1, 6): *Displacement y* = −0.15 m, **Applies to** only the
   load stage. This is half of a 2 m wide rigid footing pushed down 150 mm.

## 4. Solve and read the load

Shift+F5. In the load stage:

* View > Show Deformed Mesh and View > Show Yielded Zones show the failure mechanism under the footing.
* View > Report: the reaction of the footing boundary is about 215 kN per metre on the 1 m half width,
  i.e. a pressure of **≈ 215 kPa**.
* View > Graph shows the load-settlement curve flattening as the clay fails.

Theory (Prandtl): q = (π + 2) su = 5.14 × 40 = 206 kPa. A finer mesh comes closer.
