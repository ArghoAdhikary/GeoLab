"""Runs analyses in dependency order (parents before children).

An analysis takes what it needs from its ancestors:
  seepage   <- seepage (initial heads)
  slope     <- seepage (pore pressure), stress (finite element stress method), dynamic (Newmark)
  stress    <- seepage (pore pressure), stress (initial stresses)
  dynamic   <- stress (in situ, informational)
  thermal   <- thermal (initial temperatures)
  transport <- seepage (flow field, required)
  air       <- seepage (degree of saturation)
"""
from __future__ import annotations

import math

import numpy as np

from .seep import run_seepage


def ancestor(project, analysis, kind):
    """Nearest ancestor of the given kind (parents first)."""
    seen = set()
    a = project.analysis(analysis.parent_id)
    while a is not None and a.id not in seen:
        if a.kind == kind:
            return a
        seen.add(a.id)
        a = project.analysis(a.parent_id)
    return None


def _ensure(project, a, cancel):
    if a is not None and a.results is None:
        solve(project, a, None, cancel)
    return a.results if a is not None else None


def solve(project, analysis, progress=None, cancel=None) -> dict:
    kind = analysis.kind
    parent = project.analysis(analysis.parent_id)
    if parent is not None and parent.results is None:
        solve(project, parent, None, cancel)
    seep = ancestor(project, analysis, "seepage")
    if kind == "seepage":
        pres = parent.results if parent is not None and parent.kind == "seepage" else None
        res = run_seepage(project, analysis, progress, cancel, parent_results=pres)
    elif kind == "slope":
        from .slope import run_slope
        if analysis.pwp == "seepage" and seep is None:
            raise ValueError(f"'{analysis.name}' takes pore pressures from a seepage analysis, "
                             "but it has no seepage parent.")
        stress = ancestor(project, analysis, "stress")
        if analysis.method == "finite_element" and stress is None:
            raise ValueError("The finite element stress method needs a stress-deformation analysis as parent.")
        res = run_slope(project, analysis, _ensure(project, seep, cancel) if analysis.pwp == "seepage" else None,
                        progress, cancel, stress_results=_ensure(project, stress, cancel) if stress else None)
        dyn = ancestor(project, analysis, "dynamic")
        if dyn is not None and res.get("critical"):
            res["newmark"] = newmark_for_slope(project, analysis, res, _ensure(project, dyn, cancel), seep)
    elif kind == "stress":
        from .sigma import run_stress
        if analysis.pwp == "seepage" and seep is None:
            raise ValueError("Pore pressure 'From seepage analysis' needs a seepage parent.")
        sp = parent if parent is not None and parent.kind == "stress" else None
        res = run_stress(project, analysis, progress, cancel, parent=sp,
                         seep_results=_ensure(project, seep, cancel) if analysis.pwp == "seepage" else None)
    elif kind == "dynamic":
        from .quake import run_dynamic
        res = run_dynamic(project, analysis, progress, cancel, parent=parent)
    elif kind == "thermal":
        from .thermal import run_thermal
        pres = parent.results if parent is not None and parent.kind == "thermal" else None
        res = run_thermal(project, analysis, progress, cancel, parent_results=pres)
    elif kind == "transport":
        from .transport import run_transport
        if seep is None:
            raise ValueError("Contaminant transport needs a seepage analysis as its parent.")
        res = run_transport(project, analysis, progress, cancel, seep_results=_ensure(project, seep, cancel))
    elif kind == "air":
        from .air import run_air
        res = run_air(project, analysis, progress, cancel, seep_results=_ensure(project, seep, cancel) if seep else None)
    else:
        raise ValueError(f"Unknown analysis type '{kind}'.")
    analysis.results = res
    return res


def newmark_for_slope(project, analysis, res, dyn_results, seep):
    """Yield acceleration of the critical slip surface and Newmark permanent displacement from the
    average horizontal acceleration of the sliding mass in the parent dynamic analysis."""
    from .geometry import GroundProfile
    from .quake import newmark_block
    from .slope import _surface_fn, build_slices, factor_of_safety, make_pwp_fn, set_strength
    gp = GroundProfile(project.regions)
    pwp_fn = make_pwp_fn(project, analysis, seep.results if seep is not None else None)
    surf = res["critical"]["surface"]
    s, why = build_slices(project, analysis, surf, pwp_fn, gp)
    if s is None:
        return {"error": why}
    method = analysis.method if analysis.method != "finite_element" else "morgenstern_price"

    def F_at(kh):
        s.kh = kh
        set_strength(s, project.materials)
        return factor_of_safety(s, method, analysis.interslice, analysis.interslice_points)[0]
    if not F_at(0.0) > 1.0:
        ky = 0.0
    else:
        lo, hi = 0.0, 0.05
        while F_at(hi) > 1.0 and hi < 2.0:
            lo, hi = hi, hi * 2
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if F_at(mid) > 1.0:
                lo = mid
            else:
                hi = mid
        ky = 0.5 * (lo + hi)
    nodes = np.asarray(dyn_results["nodes"])
    ys, _, _ = _surface_fn(surf)
    inside = (nodes[:, 1] > ys(nodes[:, 0])) & (nodes[:, 1] <= gp.ground(nodes[:, 0]) + 1e-9)
    ax = np.asarray(dyn_results["history_ax"])
    if not inside.any() or ax.size == 0:
        return {"ky": ky, "error": "No dynamic nodes inside the sliding mass."}
    avg = ax[:, inside].mean(axis=1)
    sign = -1.0 if res["critical"]["driving_direction"] == "left" else 1.0
    d, hist = newmark_block(dyn_results["history_times"], sign * avg, ky, dyn_results["g"])
    return {"ky": float(ky), "displacement": float(d), "times": dyn_results["history_times"],
            "avg_acceleration": avg.tolist(), "displacement_history": hist}


def solve_all(project, progress=None, cancel=None) -> list[tuple[str, str | None]]:
    """Solve every analysis, parents first. Returns (name, error or None) per analysis."""
    done, out = set(), []

    def visit(a):
        if a.id in done:
            return
        parent = project.analysis(a.parent_id)
        if parent is not None:
            visit(parent)
        try:
            solve(project, a, progress, cancel)
            out.append((a.name, None))
        except Exception as e:  # report per-analysis failures, keep going
            a.results = None
            out.append((a.name, str(e)))
        done.add(a.id)

    for a in project.analyses:
        visit(a)
    return out


def verify(project, analysis) -> list[str]:
    """Pre-solve checks, reported to the user without running the solver."""
    from .geometry import validate_geometry
    msgs = validate_geometry(project)
    k = analysis.kind
    if k == "slope":
        st = analysis.search
        if st.mode == "entry_exit" and (st.entry_x1 == st.entry_x2 and st.exit_x1 == st.exit_x2):
            msgs.append("Entry and exit ranges are not set (Draw > Slip Surface Entry and Exit, or Auto).")
        if st.mode in ("grid_radius", "grid_tangent") and (st.grid_x1 == st.grid_x2 or st.grid_y1 == st.grid_y2):
            msgs.append("The slip surface grid has zero size.")
        if st.mode == "grid_tangent" and st.tangent_y1 == st.tangent_y2 and st.n_tangent > 1:
            msgs.append("The tangent line range has zero size.")
        if st.mode == "block" and (st.block_left[0] == st.block_left[2] and st.block_right[0] == st.block_right[2]):
            msgs.append("The block search grids are not set.")
        if st.mode == "fully_specified" and not (st.circles or st.polylines):
            msgs.append("No fully specified slip surfaces are defined.")
        if analysis.pwp == "piezometric" and len(project.piezometric_line) < 2:
            msgs.append("Pore-water pressure uses a piezometric line but none is drawn.")
        if analysis.pwp == "seepage" and ancestor(project, analysis, "seepage") is None:
            msgs.append("Pore-water pressure comes from a seepage analysis but no seepage parent is set.")
        if analysis.method == "finite_element" and ancestor(project, analysis, "stress") is None:
            msgs.append("The finite element stress method needs a stress-deformation parent analysis.")
        if analysis.n_slices < 5:
            msgs.append("Use at least 5 slices.")
        return msgs
    from .model import KIND_BCS
    group = KIND_BCS.get(k)
    if group and not project.bcs(group, analysis) and k != "dynamic":
        msgs.append(f"No {group} boundary conditions are defined.")
    if analysis.mesh_size <= 0:
        msgs.append("Mesh size must be positive.")
    if k == "seepage":
        if not any(b.type in ("head", "pressure_head", "seepage_face") for b in project.bcs("hydraulic", analysis)):
            msgs.append("A seepage analysis needs at least one head or pressure-head boundary condition.")
        for m in project.materials:
            if m.k_sat <= 0:
                msgs.append(f"Material '{m.name}' has a non-positive hydraulic conductivity.")
        if analysis.transient and analysis.initial == "parent" and ancestor(project, analysis, "seepage") is None:
            msgs.append("Transient seepage needs initial conditions (a seepage parent, water table or value).")
    if k in ("stress", "dynamic"):
        if not any(b.type in ("fixed_x", "fixed_y", "fixed_xy") for b in project.bcs("stress", analysis)):
            msgs.append("Add fixed boundary conditions (sides fixed in x, base fixed in x and y).")
        for m in project.materials:
            if m.stress_model != "none" and (m.E <= 0 or not (-1 < m.nu < 0.5)):
                msgs.append(f"Material '{m.name}' needs E > 0 and Poisson's ratio below 0.5.")
    if k == "dynamic" and len(analysis.motion) < 2:
        msgs.append("Enter the input acceleration time history (Define > Analysis Settings).")
    if k == "transport" and ancestor(project, analysis, "seepage") is None:
        msgs.append("Contaminant transport needs a seepage parent analysis.")
    if k in ("thermal", "transport") and analysis.duration <= 0 and (analysis.transient or k == "transport"):
        msgs.append("Duration must be positive.")
    return msgs
