<!-- example: River bank: flood, drawdown, toe scour -->
<!-- check: River bank: flood, drawdown, toe scour | 0 | critical.fos | 1.435 | 0.02 -->
<!-- check: River bank: flood, drawdown, toe scour | 1 | critical.fos | 0.736 | 0.03 -->
<!-- check: River bank: flood, drawdown, toe scour | 2 | critical.fos | 1.154 | 0.02 -->
# Tutorial 11 — River bank after a monsoon flood (BNBC 2020)

**Goal:** check an 8 m river bank through a flood, the fall of the flood and an earthquake, and compare
it with BNBC 2020.
**Time:** 10 minutes. **Result:** F = 1.43 at high flood, **0.74 after rapid drawdown**, and 1.15 with an
earthquake.

![Rapid drawdown of the river bank](img/riverbank.png)

## 1. The model

1. **File > New River Bank**. Keep the numbers:
   - bank 8 m high at 2.5H:1V
   - scour hole 2 m deep at the toe
   - flood 7 m and low water 1 m above the river bed
   - 3 m of silty clay over fine sand
2. Leave *Solve straight away* ticked and press OK.

GeoLab draws the bank and the scour hole. It sets up three slope stability analyses:

| Analysis | Water | What it shows |
|---|---|---|
| 1. High flood | bank saturated to the flood level | the river supports the bank |
| 2. Rapid drawdown after the flood | flood falls to the low level (Duncan-Wright-Wong) | the clay cannot drain in time |
| 3. High flood + earthquake | as 1, with kh from the design code | the seismic case |

## 2. Results

| Analysis | F |
|---|---|
| 1. High flood | 1.435 |
| 2. Rapid drawdown | **0.736** |
| 3. Flood + earthquake | 1.154 |

The bank is stable while the river is high, because the water pushes on the slope. It fails when the
flood falls quickly. The clay top is still full of water, but the river no longer supports it. This is
how most bank failures on the big rivers happen in the monsoon recession.

## 3. Check against BNBC 2020

1. **Design > Design Code Check**, design code **BNBC 2020**, location **Dhaka** (zone 2), site class
   **SD**, importance **II**.
2. GeoLab works out the design PGA = 2/3 × 0.20 × 1.0 × 1.35 = 0.18 g, so kh = 0.090.
3. Press **Check the solved analyses**:
   - Analysis 1 fails the long-term minimum of 1.5.
   - Analysis 2 fails the drawdown minimum of 1.3 by a long way.
   - Analysis 3 used kh = 0.044 (the Australian default the model was made with), which is less than
     BNBC asks for.
4. Press **Put this kh in the earthquake analyses** and solve again (Shift+F5). F of analysis 3 drops.

## 4. What would make it safe?

- **Design > What-If Sliders** on analysis 1: move *tan(phi) ×* and *Cohesion ×* to see how much stronger
  the bank would have to be.
- **Design > Design Optimizer** on analysis 1, *Slope steepness*, target 1.5: the flatter slope that is
  needed.
- Protecting the toe against scour (geobags, revetment) removes the scour hole: set the scour to 0 in
  File > New River Bank and compare.
