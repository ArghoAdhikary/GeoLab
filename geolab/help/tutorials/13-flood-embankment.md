<!-- example: Flood embankment on soft clay -->
<!-- check: Flood embankment on soft clay | 1 | critical.fos | 1.715 | 0.02 -->
<!-- check: Flood embankment on soft clay | 2 | critical.fos | 3.017 | 0.03 -->
<!-- check: Flood embankment on soft clay | 3 | critical.fos | 1.470 | 0.02 -->
# Tutorial 13 — Flood embankment: code check and design report

**Goal:** check a 5 m levee on soft clay with Australian Standards and BNBC 2020, add a liquefaction
check, and write the design report.
**Time:** 15 minutes. **Result:** land side F = 1.72, river side 3.02, land side in an earthquake 1.47; a
Word report.

## 1. The model

**File > New Flood Embankment** gives a levee 5 m high on 6 m of soft clay over sand, with the river on
the left. The defaults are:

- crest 4 m wide
- slopes 3H:1V on both sides
- flood 4.2 m above the ground

Four analyses: the seepage at flood, then three slope stability analyses that take their pore pressures
from it.

| Analysis | F |
|---|---|
| Land side at flood | 1.715 |
| River side at flood | 3.017 |
| Land side, earthquake (kh = 0.044) | 1.470 |

The land side is the critical one: water seeps under the levee and lifts the pore pressure at the land
side toe.

## 2. Australian Standards (the default)

1. **Design > Design Code Check**: *Australian Standards*, soil class II, Sydney (Z = 0.08), 1/500, site
   class De.
2. **Check the solved analyses**:
   - Both flood cases pass F ≥ 1.5.
   - The AS 4678 limit state check divides the strength by the soil uncertainty factors
     (c' × 0.70, tan φ' × 0.85) and multiplies the live load by 1.5. F of that factored model must be at
     least 1.0.

## 3. BNBC 2020

Switch the code to **BNBC 2020**, location **Sylhet** (zone 4, Z = 0.36), site class **SD**.

- kh becomes 0.5 × 2/3 × 0.36 × 1.35 = 0.162.
- **Put this kh in the earthquake analyses**, then solve again: the earthquake case now has to pass
  F ≥ 1.1 with the larger kh.

## 4. Liquefaction of the foundation sand

**Design > Liquefaction Check**, SPT, **Example values**, water table 1.5 m. The PGA comes from the
code: 2/3 × 0.36 × 1.35 = 0.324 g for Sylhet.

Run:

- Every sand layer from 3 m to 9 m has FS < 1. The lowest is about 0.5, at 4.5–6 m.
- The dense sand at 12 m is safe.
- LPI is about 25, which is **very high**.

Change the code back to Sydney (PGA 0.088 g): every layer is then safe and LPI = 0.

Press **Put in the design report** to keep the result.

## 5. The report

**Design > Design Report**, save as Word. The document has:

- the project and the materials
- a picture and the results of each analysis
- the code check table with PASS / FAIL for each item
- the liquefaction table
- the detailed reports, in an appendix

It opens in Word, ready to edit and submit.
