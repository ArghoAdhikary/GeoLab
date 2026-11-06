# 7. Earthquake, heat, contaminant and air flow

## 7.1 Dynamic (earthquake)

A dynamic analysis applies a base acceleration record (time in seconds, acceleration in g) to the model.
Settings: the time step, **Linear Elastic** or **Equivalent Linear** (stiffness and damping follow the
strain level through the reference strain and maximum damping of each material) and the number of
equivalent linear iterations.

Boundaries: fix the base in x and y and the sides in y. Results: peak acceleration and displacement,
maximum shear strain, stiffness ratio and damping, the natural frequency, and the acceleration history at
any point. A slope stability child computes the Newmark displacement (4.6).

![Peak acceleration in a slope](img/dynamic.png)

## 7.2 Thermal (heat transfer and freezing)

Conduction with latent heat: when the soil temperature passes through 0 °C its water freezes or thaws
(within the freezing range), which slows the frost front. Boundaries: temperature, heat flux, or
convective (heat transfer coefficient h and air temperature in time). Results: temperature, frozen
fraction, heat flux, the energy balance.

![Frost penetration after a winter](img/thermal.png)

## 7.3 Contaminant transport

Advection-dispersion with adsorption (Kd and dry density) and first-order decay (half-life), in the flow
field of a parent seepage analysis. Boundaries: concentration (a source), mass flux, free exit. Particle
tracking start points follow the groundwater flow. Results: concentration in time, mass in the model, the
grid Peclet number (keep it below about 2 by refining the mesh).

![Contaminant plume after 10 years](img/transport.png)

## 7.4 Air flow

Air pressure and flow in the soil pores, for soil vapour extraction or air sparging. Air conductivity
falls as the soil becomes wetter when a seepage parent gives the saturation. Boundaries: air pressure
(gauge) and air flux.
