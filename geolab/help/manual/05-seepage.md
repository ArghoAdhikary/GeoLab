# 5. Seepage

![Steady seepage through an earth dam](img/seepage.png)

## 5.1 Steady-state and transient

The analysis type is **Steady-State** (the flow does not change with time) or **Transient** (heads change
over a duration, in time steps). A transient analysis needs initial conditions: from a parent analysis,
from the piezometric line, or a uniform head.

Time steps: give the duration in seconds, the number of steps and a growth ratio (steps grow by this ratio,
so short steps come first, where things change fastest). 1 day = 86 400 s, 1 year ≈ 3.15 × 10⁷ s.

## 5.2 Hydraulic materials

| Model | When |
|---|---|
| Saturated only | Confined flow below the water table; storage from mv |
| Gardner | Simple unsaturated model with one parameter α |
| van Genuchten-Mualem | Unsaturated soils from the water retention curve (θs, θr, α, n) |

Include unsaturated flow (Seepage tab) lets the phreatic surface find its own position.
The ratio ky / kx gives anisotropy.

## 5.3 Boundary conditions

| Boundary | Example |
|---|---|
| Total head | Reservoir: head = water level elevation |
| Pressure head | Pressure relative to the point |
| Unit flux / total nodal flux | Recharge, pumping well (negative = out) |
| Potential seepage face | Downstream face of a dam: no water enters, water may leave where it reaches the face |
| Infiltration with ponding | Rain that cannot all enter the soil: the surplus ponds or runs off |
| Free drainage | Bottom of a deep column (unit gradient) |
| Climate | Rainfall, evaporation from humidity, plant transpiration with a root depth |

Reservoir heads can vary with time (value vs time table) for filling or drawdown.

## 5.4 Climate and plant transpiration

The climate boundary takes the rainfall rate in time, the potential evaporation and the air humidity, and
optionally the **potential transpiration** of plants and their **root depth**. Water is taken out of the
root zone (more near the surface, less at the root tip) and reduced when the soil is too dry or too wet
(Feddes). The result lists the total rain, evaporation, runoff and actual transpiration.

## 5.5 Flux sections

Draw > Flux Sections draws a line across the flow; the result gives the flow rate through it (for example
the seepage under a dam per metre of length).

## 5.6 Results

Contours of total head, pressure head, pore pressure and water content, flow vectors (View > Show Flow
Vectors), the phreatic surface, total inflow and outflow, and for transient analyses the water balance and
the history at any point (click the point, then View > Graph).
