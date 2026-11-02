"""Runs analyses in dependency order (parents before children)."""
from __future__ import annotations

from .seep import run_seepage
from .slope import run_slope


def solve(project, analysis, progress=None, cancel=None) -> dict:
    if analysis.kind == "seepage":
        parent = project.analysis(analysis.parent_id)
        pres = None
        if parent is not None and parent.kind == "seepage":
            if parent.results is None:
                parent.results = run_seepage(project, parent, None, cancel)
            pres = parent.results
        res = run_seepage(project, analysis, progress, cancel, parent_results=pres)
    elif analysis.kind == "slope":
        seep = None
        if analysis.pwp == "seepage":
            parent = project.analysis(analysis.parent_id)
            if parent is None or parent.kind != "seepage":
                raise ValueError(f"'{analysis.name}' takes pore pressures from a seepage analysis, "
                                 "but its parent is not a seepage analysis.")
            if parent.results is None:
                parent.results = run_seepage(project, parent, None, cancel)
            seep = parent.results
        res = run_slope(project, analysis, seep, progress, cancel)
    else:
        raise ValueError(f"Unknown analysis type '{analysis.kind}'.")
    analysis.results = res
    return res


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
    if analysis.kind == "slope":
        st = analysis.search
        if st.mode == "entry_exit" and (st.entry_x1 == st.entry_x2 and st.exit_x1 == st.exit_x2):
            msgs.append("Entry and exit ranges are not set (Draw > Slip Surface Entry and Exit, or Auto).")
        if st.mode == "grid_radius" and (st.grid_x1 == st.grid_x2 or st.grid_y1 == st.grid_y2):
            msgs.append("The slip surface grid has zero size.")
        if st.mode == "fully_specified" and not (st.circles or st.polylines):
            msgs.append("No fully specified slip surfaces are defined.")
        if analysis.pwp == "piezometric" and len(project.piezometric_line) < 2:
            msgs.append("Pore-water pressure uses a piezometric line but none is drawn.")
        if analysis.pwp == "seepage":
            parent = project.analysis(analysis.parent_id)
            if parent is None or parent.kind != "seepage":
                msgs.append("Pore-water pressure comes from a seepage analysis but no seepage parent is set.")
        if analysis.n_slices < 5:
            msgs.append("Use at least 5 slices.")
    else:
        if not any(b.type in ("head", "pressure_head") for b in project.boundary_conditions):
            msgs.append("A seepage analysis needs at least one head or pressure-head boundary condition.")
        for m in project.materials:
            if m.k_sat <= 0:
                msgs.append(f"Material '{m.name}' has a non-positive hydraulic conductivity.")
    return msgs
