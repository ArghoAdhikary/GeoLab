# 10. Troubleshooting

| Problem | What to do |
|---|---|
| Verify reports overlapping regions or gaps | Select the region, Modify > Edit Region Points, make neighbouring regions share the same corner coordinates. Snap to Grid helps when drawing. |
| "No valid slip surfaces" | The entry and exit ranges must lie on the ground surface, entry above exit (or the other way for a slope facing left). Try Auto locate. Increase the radius increments. |
| Factor of safety much lower than expected | Look at the critical surface: a very shallow surface in loose material at the face (c' = 0) gives F ≈ tan φ / tan β. Set a minimum slip surface depth (Convergence tab). |
| Seepage does not converge | Use a smaller mesh near seepage faces, more iterations, a steady parent as the initial condition, or saturated-only materials to start with. |
| Stress analysis does not converge | More load steps; check the supports (the model must not be able to float or slide); realistic E (not zero); for an excavation, check the wall reaches below the dig level. |
| Results look patchy | Refine the mesh (smaller element size). Halve it and solve again: if the result changes by more than a few percent, keep the smaller size. |
| Slow solving | Larger elements far from the area of interest; fewer time steps with a growth ratio > 1. On Windows the MKL solver uses every processor core. |
| Imperial values look wrong | Define > Project Properties converts every value when switching units; check the list of values that were not converted. |
| The window layout is lost | Window > Reset Window Layout |

## 10.1 Getting help

* F1 — the Quick Guide
* Help > Tutorials — step-by-step tutorials (also in this manual)
* Help > User Manual — this document
* Help > Example Files — every example, solved, as a .slab file
* Report a problem: https://github.com/ArghoAdhikary/GeoLab/issues
