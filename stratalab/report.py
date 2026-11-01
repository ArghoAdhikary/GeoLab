"""Plain-text analysis report (shown in the Report window and in PDF exports)."""
from __future__ import annotations

import datetime

from . import __version__
from .model import BC_TYPES, PWP_MODES, SEARCH_MODES, SLOPE_METHODS, STRENGTH_MODELS


def _f(v, nd=3):
    return "-" if v is None else f"{v:.{nd}f}"


def build_report(project, analysis) -> str:
    u = project.unit
    L = []
    L.append(f"StrataLab {__version__} report  -  {datetime.datetime.now():%Y-%m-%d %H:%M}")
    L.append("=" * 72)
    L.append(f"Project:  {project.title}")
    if project.author:
        L.append(f"Author:   {project.author}")
    if project.description:
        L.append(f"Notes:    {project.description}")
    L.append(f"Units:    {project.units} (length {u('length')}, pressure {u('pressure')}, unit weight {u('unit_weight')})")
    L.append("")
    L.append(f"Analysis: {analysis.name}  [{'Slope stability' if analysis.kind == 'slope' else 'Seepage'}]")
    if analysis.description:
        L.append(f"          {analysis.description}")
    parent = project.analysis(analysis.parent_id)
    if parent:
        L.append(f"Parent:   {parent.name}")
    L.append("")
    L.append("Materials")
    L.append("-" * 72)
    if analysis.kind == "slope":
        L.append(f"{'#':>3}  {'Name':<20}{'Model':<22}{'Unit wt':>9}{'c':>9}{'phi':>7}")
        for m in project.materials:
            L.append(f"{m.id:>3}  {m.name[:19]:<20}{STRENGTH_MODELS.get(m.model, m.model)[:21]:<22}"
                     f"{m.unit_weight:>9.2f}{m.cohesion:>9.2f}{m.phi:>7.1f}")
    else:
        L.append(f"{'#':>3}  {'Name':<20}{'k_sat':>12}{'ky/kx':>8}{'alpha':>8}")
        for m in project.materials:
            L.append(f"{m.id:>3}  {m.name[:19]:<20}{m.k_sat:>12.3e}{m.k_ratio:>8.2f}{m.unsat_alpha:>8.2f}")
    L.append("")
    if analysis.kind == "slope":
        st = analysis.search
        L.append("Settings")
        L.append("-" * 72)
        L.append(f"Method:            {SLOPE_METHODS.get(analysis.method, analysis.method)}")
        if analysis.method == "morgenstern_price":
            L.append(f"Interslice f(x):   {'half-sine' if analysis.interslice == 'half_sine' else 'constant'}")
        L.append(f"Slices:            {analysis.n_slices}")
        L.append(f"Pore pressure:     {PWP_MODES.get(analysis.pwp, analysis.pwp)}"
                 + (f" (Ru = {analysis.ru})" if analysis.pwp == "ru" else ""))
        L.append(f"Seismic kh:        {analysis.kh}")
        L.append(f"Slip search:       {SEARCH_MODES.get(st.mode, st.mode)}")
    else:
        L.append("Settings")
        L.append("-" * 72)
        L.append(f"Mesh size:         {analysis.mesh_size} {u('length')}")
        L.append(f"Unsaturated flow:  {'yes' if analysis.unsaturated else 'no (saturated only)'}")
        L.append("Boundary conditions:")
        for b in project.boundary_conditions:
            L.append(f"  {b.name:<20}{BC_TYPES.get(b.type, b.type):<26}{b.value:g}")
    L.append("")
    r = analysis.results
    L.append("Results")
    L.append("-" * 72)
    if not r:
        L.append("Not solved.")
        return "\n".join(L)
    if r["type"] == "slope":
        L.append(f"Trial surfaces:    {r['n_total']} ({r['n_valid']} valid)")
        for why, n in r.get("invalid_reasons", {}).items():
            L.append(f"  invalid: {n} x {why}")
        c = r.get("critical")
        if not c:
            L.append(r.get("message", "No valid slip surface."))
            return "\n".join(L)
        L.append(f"Critical factor of safety ({SLOPE_METHODS[r['method']]}):  {c['fos']:.3f}")
        s = c["surface"]
        if s["type"] == "circle":
            L.append(f"Critical circle:   centre ({s['xc']:.2f}, {s['yc']:.2f}), radius {s['R']:.2f}")
        L.append(f"Sliding towards:   {'+x (right)' if c['driving_direction'] == 'right' else '-x (left)'}")
        if c.get("lambda") is not None:
            L.append(f"Lambda:            {c['lambda']:.4f}")
        L.append("")
        L.append("All methods on the critical surface:")
        for m, v in c["all_methods"].items():
            lam = f"   lambda {v['lambda']:.3f}" if v.get("lambda") is not None else ""
            L.append(f"  {SLOPE_METHODS[m]:<24}{_f(v['fos'])}{lam}")
        if r.get("probability") and r["probability"].get("n"):
            p = r["probability"]
            L.append("")
            L.append("Probabilistic (Monte Carlo):")
            L.append(f"  samples {p['n']}, mean F {p['mean']:.3f}, std dev {p['sd']:.3f}, "
                     f"min {p['min']:.3f}, max {p['max']:.3f}")
            L.append(f"  probability of failure {100 * p['pf']:.2f} %, reliability index {_f(p['reliability_index'])}")
        if r.get("sensitivity") and "values" in r["sensitivity"]:
            sv = r["sensitivity"]
            L.append("")
            L.append(f"Sensitivity of F to {sv['param']}:")
            for v, f in zip(sv["values"], sv["fos"]):
                L.append(f"  {v:>12.3f}   F = {_f(f)}")
        L.append("")
        L.append("Slices")
        L.append(f"{'#':>3}{'x':>9}{'width':>8}{'alpha':>8}{'weight':>11}{'u':>9}{'N':>11}{'S mob':>10}")
        for row in c["slices"]:
            L.append(f"{row['slice']:>3}{row['x']:>9.2f}{row['width']:>8.2f}{row['alpha_deg']:>8.1f}"
                     f"{row['weight']:>11.2f}{row['pore_pressure']:>9.2f}{row['normal']:>11.2f}"
                     f"{row['shear_mobilized']:>10.2f}")
    else:
        L.append(f"Converged:         {'yes' if r['converged'] else 'NO'} in {r['iterations']} iterations")
        L.append(f"Mesh:              {len(r['nodes'])} nodes, {len(r['tris'])} elements")
        L.append(f"Total inflow:      {r['inflow']:.4e} {u('flux')} per unit width")
        L.append(f"Total outflow:     {r['outflow']:.4e} {u('flux')} per unit width")
        if r["inflow"] > 0:
            L.append(f"Balance error:     {100 * abs(r['inflow'] - r['outflow']) / r['inflow']:.3f} %")
        L.append(f"Head range:        {min(r['head']):.3f} to {max(r['head']):.3f} {u('length')}")
        L.append(f"Seepage face:      {len(r['seepage_face_nodes'])} nodes")
    return "\n".join(L)
