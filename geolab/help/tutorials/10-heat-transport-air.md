<!-- example: Contaminant plume (transport) -->
<!-- check: Contaminant plume (transport) | 0 | inflow | 5.0e-6 | 0.01 -->
<!-- check: Soil vapour extraction (air flow) | 0 | inflow | 2.758e-4 | 0.03 -->
# Tutorial 10 — Frost, contamination and air flow

Three short tours of the other analysis types. Open each example with File > Open Example and press
Shift+F5.

## A. Frost penetration (thermal)

![Temperature after the winter](img/thermal.png)

*Frost penetration (thermal)*: a 6 m silt column, 6 °C deep in the ground, and a **convective** boundary
at the surface (heat transfer coefficient 15 and an air temperature falling from 2 °C to −12 °C, then
rising to 5 °C after 150 days). The silt has frozen and unfrozen conductivity and heat capacity, and
32 % water whose latent heat slows the frost.

In the results move the time slider and show the *frozen fraction*: the frost front goes down to about
1.8 m by day 125; when the air warms up at the end, the top starts to thaw.

## B. Contaminant plume (transport)

![Plume after 10 years](img/transport.png)

*Contaminant plume (transport)*:

1. **Groundwater flow** (seepage): heads 20 m upstream and 18 m downstream across a 120 m sand aquifer,
   k = 2 × 10⁻⁵ m/s; the flow is 5 × 10⁻⁶ m³/s per metre.
2. **Transport (10 years)**, child of 1: a pond at the surface keeps the concentration at 100; dispersivity
   2 m along and 0.2 m across the flow. Two particles show the path of the water.

Move the time slider to watch the plume spread downstream. The report gives the mass in the aquifer and
the grid Peclet number (below 2 means the mesh is fine enough).

## C. Soil vapour extraction (air flow)

*Soil vapour extraction (air flow)*: a well at the bottom of a 5 m sand layer pulls −5 kPa; the ground
surface is at atmospheric pressure. Results: air pressure contours, flow vectors and the air flow into the
well (≈ 2.8 × 10⁻⁴ m³/s per metre).
