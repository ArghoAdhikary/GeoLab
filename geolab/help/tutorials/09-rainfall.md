<!-- example: Rainfall and evaporation on a slope -->
<!-- check: Rainfall and evaporation on a slope | 1 | critical.fos | 1.609 | 0.03 -->
# Tutorial 9 — Rain, evaporation and plants on a slope

**Goal:** wet a silty slope for 20 days of rain, dry it for 20 days, and check its stability with the
suction that remains.
**Time:** 15 minutes. **Result:** F ≈ 1.61 at the end of the season.

Open File > Open Example > *Rainfall and evaporation on a slope*.

## 1. Unsaturated soil

Material *Silty soil*: van Genuchten-Mualem with k_sat = 2 × 10⁻⁶ m/s, θs = 0.42, θr = 0.08, α = 1,
n = 1.7. Strength c' = 4 kPa, φ' = 30° and **φb = 15°**: suction (negative pore pressure) adds strength.

## 2. The climate boundary

Along the ground surface, type **Climate**:

* Rainfall in time: 25 mm/day (2.9 × 10⁻⁷ m/s) for 20 days, then none until day 40.
* Potential evaporation 4 mm/day, air humidity 0.6.
* Optional: **potential transpiration** of plants and the **root depth**. Water is taken from the root zone;
  less when the soil is very dry or saturated.

Rain that cannot enter the soil runs off. Head boundaries on the sides keep the groundwater.

## 3. Analyses

1. *Wet season and dry spell*: transient seepage, 40 days in 40 steps, initial conditions from the water
   table.
2. *Stability after the season*: slope stability, child of 1.

## 4. Results

Move the time slider in the seepage result: the wetting front goes down during the rain and the surface
dries afterwards. The report lists the rain, evaporation, runoff and (if set) transpiration totals, and
the water balance error. The stability gives **F ≈ 1.61**.

**Try:** set φb = 0 (no strength from suction) and solve the stability again.
