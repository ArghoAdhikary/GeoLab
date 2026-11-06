<!-- example: Anchored excavation (staged) -->
<!-- check: Anchored excavation (staged) | 3 | structures.0.max_M | 29.4 | 0.05 -->
<!-- check: Anchored excavation (staged) | 3 | structures.1.max_N | 68.1 | 0.05 -->
# Tutorial 7 — Anchored excavation in stages

**Goal:** dig a 6 m excavation in two lifts next to a sheet-pile wall with one prestressed anchor, and read
the wall moment and anchor force.
**Time:** 30 minutes. **Result:** wall moment ≈ 29 kN·m/m, anchor force ≈ 68 kN/m after the second lift.

![Wall and anchor](img/excavation.png)

## 1. Geometry — draw each lift as its own region

Half model, the excavation on the left (x = 0 to 10), ground surface at y = 20:

| Region | Points |
|---|---|
| Lift 1 (top 3 m to dig) | (0, 17), (10, 17), (10, 20), (0, 20) |
| Lift 2 (next 3 m) | (0, 14), (10, 14), (10, 17), (0, 17) |
| The rest | (0, 0), (40, 0), (40, 20), (10, 20), (10, 17), (10, 14), (0, 14) |

All three use one material *Sand*: Elastic-plastic, c' = 2 kPa, φ' = 32°, ψ = 2°, E = 30 000 kPa, ν = 0.3,
γ = 19. Supports: fixed x on the sides, fixed x and y on the base.

## 2. Four stages

| Stage | Type, parent | Construction Stage tab | Load steps |
|---|---|---|---|
| 1. In situ | In Situ | all regions ticked | — |
| 2. Wall + dig to 3 m | Load-Deformation, child of 1 | untick Lift 1 | 4 |
| 3. Anchor (150 kN) | Load-Deformation, child of 2 | untick Lift 1 | 2 |
| 4. Dig to 6 m | Load-Deformation, child of 3 | untick Lift 1 and Lift 2 | 6 |

Use Define > Add Child Analysis on the previous stage each time, then open its **Construction Stage**
tab and untick the dug-out regions. They are drawn hatched in that stage.

## 3. Structures

Draw > Structures:

1. **Sheet-pile wall**: click (10, 20) and (10, 10), Enter. Type Beam / wall, EA = 4 × 10⁶ kN/m,
   EI = 4 × 10⁴ kN·m²/m, present in stages 2, 3 and 4.
2. **Ground anchor**: click (10, 18) and (20, 14), Enter. Type Anchor / strut, EA = 2 × 10⁵ kN,
   spacing 2 m, prestress 150 kN, present in stages 3 and 4.

## 4. Solve and read the results

Shift+F5. Select stage 4:

* The wall and anchor are labelled with their largest force: wall moment **≈ 29 kN·m/m**, anchor force
  **≈ 68 kN/m** (136 kN per anchor at 2 m spacing).
* View > Show Deformed Mesh: the excavation floor heaves and the ground behind the wall settles.
* View > Report lists N, V and M along every structure element.

**Try:** make the soil Hardening Soil (E50 = 30 000, Eur = 90 000 kPa, m = 0.5) and compare the floor heave
and the wall moment with the Mohr-Coulomb result.
