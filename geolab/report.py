"""Plain-text analysis report (shown in the Report window and in PDF exports)."""
from __future__ import annotations

import datetime

from . import __version__
from .model import (ANALYSIS_KINDS, BC_TYPES, KIND_BCS, PWP_MODES, SEARCH_MODES, SLOPE_METHODS,
                    STRENGTH_MODELS, STRESS_MODELS)


def _f(v, nd=3):
    return "-" if v is None else f"{v:.{nd}f}"


def build_report(project, analysis) -> str:
    u = project.unit
    L = []
    L.append(f"GeoLab {__version__} report  -  {datetime.datetime.now():%Y-%m-%d %H:%M}")
    L.append("=" * 72)
    L.append(f"Project:  {project.title}")
    if project.author:
        L.append(f"Author:   {project.author}")
    if project.description:
        L.append(f"Notes:    {project.description}")
    L.append(f"Units:    {project.units} (length {u('length')}, pressure {u('pressure')}, unit weight {u('unit_weight')})")
    L.append("")
    L.append(f"Analysis: {analysis.name}  [{ANALYSIS_KINDS.get(analysis.kind, analysis.kind)}]")
    if analysis.description:
        L.append(f"          {analysis.description}")
    parent = project.analysis(analysis.parent_id)
    if parent:
        L.append(f"Parent:   {parent.name}")
    L.append("")
    L.append("Materials")
    L.append("-" * 72)
    k = analysis.kind
    if k == "slope":
        L.append(f"{'#':>3}  {'Name':<20}{'Model':<22}{'Unit wt':>9}{'c':>9}{'phi':>7}")
        for m in project.materials:
            L.append(f"{m.id:>3}  {m.name[:19]:<20}{STRENGTH_MODELS.get(m.model, m.model)[:21]:<22}"
                     f"{m.unit_weight:>9.2f}{m.cohesion:>9.2f}{m.phi:>7.1f}")
    elif k in ("seepage", "transport", "air"):
        L.append(f"{'#':>3}  {'Name':<20}{'Model':<14}{'k_sat':>11}{'ky/kx':>7}{'th_s':>6}{'aL':>7}{'k_air':>10}")
        for m in project.materials:
            L.append(f"{m.id:>3}  {m.name[:19]:<20}{m.hyd_model[:13]:<14}{m.k_sat:>11.3e}{m.k_ratio:>7.2f}"
                     f"{m.theta_s:>6.2f}{m.disp_l:>7.2f}{m.k_air:>10.2e}")
    elif k in ("stress", "dynamic"):
        L.append(f"{'#':>3}  {'Name':<20}{'Model':<18}{'E':>11}{'nu':>6}{'c':>8}{'phi':>6}{'gamma':>7}{'damp':>6}")
        for m in project.materials:
            L.append(f"{m.id:>3}  {m.name[:19]:<20}{STRESS_MODELS.get(m.stress_model, '')[:17]:<18}{m.E:>11.4g}"
                     f"{m.nu:>6.2f}{m.cohesion:>8.2f}{m.phi:>6.1f}{m.unit_weight:>7.2f}{m.damping:>6.2f}")
    else:
        L.append(f"{'#':>3}  {'Name':<20}{'k unfr':>9}{'k froz':>9}{'C unfr':>11}{'C froz':>11}{'water':>7}")
        for m in project.materials:
            L.append(f"{m.id:>3}  {m.name[:19]:<20}{m.th_k:>9.3g}{m.th_k_frozen:>9.3g}{m.th_c:>11.4g}"
                     f"{m.th_c_frozen:>11.4g}{m.th_water:>7.2f}")
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
        if analysis.kv:
            L.append(f"Seismic kv:        {analysis.kv}")
        if analysis.tension_crack_depth or analysis.tension_crack_angle:
            L.append(f"Tension crack:     depth {analysis.tension_crack_depth}, angle {analysis.tension_crack_angle}, "
                     f"water {analysis.crack_water:.0%}")
        if analysis.optimize:
            L.append("Optimization:      on")
        for rf in project.reinforcements:
            L.append(f"Reinforcement:     {rf.type} ({rf.x1:g}, {rf.y1:g}) to ({rf.x2:g}, {rf.y2:g}), capacity "
                     f"{rf.capacity:g}, bond {rf.bond:g}, spacing {rf.spacing:g}"
                     + (", F-dependent" if rf.f_dependent else ""))
    else:
        L.append("Settings")
        L.append("-" * 72)
        if k != "transport":
            L.append(f"Mesh size:         {analysis.mesh_size} {u('length')}")
        if k == "seepage":
            L.append(f"Unsaturated flow:  {'yes' if analysis.unsaturated else 'no (saturated only)'}")
        if k == "stress":
            L.append(f"Type:              {analysis.stress_type}{' + strength reduction' if analysis.srm else ''}")
            L.append(f"Pore pressure:     {PWP_MODES.get(analysis.pwp, analysis.pwp)}")
        if k == "dynamic":
            L.append(f"Time step:         {analysis.dt} s, "
                     f"{'equivalent linear' if analysis.equivalent_linear else 'linear'}")
            peak = max((abs(acc) for _, acc in analysis.motion), default=0)
            L.append(f"Input motion:      {len(analysis.motion)} points, peak {peak:.3f} g")
        timed = (k in ("seepage", "thermal", "air") and analysis.transient) or k == "transport" \
            or (k == "stress" and analysis.stress_type == "consolidation")
        if timed:
            L.append(f"Duration:          {analysis.duration:g} s in {analysis.n_steps} steps "
                     f"(growth {analysis.step_growth:g})")
        group = KIND_BCS.get(k)
        if group:
            L.append("Boundary conditions:")
            for bc in project.bcs(group, analysis):
                fn = f"  (varies with time, {len(bc.fn)} points)" if bc.fn else ""
                L.append(f"  {bc.name:<22}{BC_TYPES.get(bc.type, bc.type):<34}{bc.value:g}{fn}")
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
        L.append(f"Critical factor of safety ({SLOPE_METHODS.get(r['method'], r['method'])}):  {c['fos']:.3f}")
        s = c["surface"]
        if s["type"] == "circle":
            L.append(f"Critical circle:   centre ({s['xc']:.2f}, {s['yc']:.2f}), radius {s['R']:.2f}")
        L.append(f"Sliding towards:   {'+x (right)' if c['driving_direction'] == 'right' else '-x (left)'}")
        if c.get("lambda") is not None:
            L.append(f"Lambda:            {c['lambda']:.4f}")
        if r.get("drawdown"):
            dd = r["drawdown"]
            L.append("")
            L.append(f"Rapid drawdown (Duncan, Wright and Wong) to elevation {dd['level']:g} {u('length')}:")
            L.append(f"  stage 1, before drawdown (drained):            F = {_f(dd['stage1'])}")
            L.append(f"  stage 2, after drawdown (undrained strength):  F = {_f(dd['stage2'])}")
            L.append(f"  stage 3, lower of drained and undrained:      F = {_f(dd['stage3'])}")
            L.append(f"  undrained strength used on {dd['undrained_slices']} of {dd['slices']} slices")
        L.append("")
        L.append("All methods on the critical surface:")
        for m, v in c["all_methods"].items():
            lam = f"   lambda {v['lambda']:.3f}" if v.get("lambda") is not None else ""
            L.append(f"  {SLOPE_METHODS.get(m, m):<34}{_f(v['fos'])}{lam}")
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
        if r.get("newmark") and "displacement" in r["newmark"]:
            nm = r["newmark"]
            L.append("")
            L.append(f"Newmark: yield acceleration ky = {nm['ky']:.3f} g, permanent displacement "
                     f"{nm['displacement']:.4f} {u('length')}")
    else:
        t = r["type"]
        L.append(f"Converged:         {'yes' if r.get('converged', True) else 'NO'}")
        L.append(f"Mesh:              {len(r['nodes'])} nodes, {len(r['tris'])} elements")
        if t in ("seepage", "air"):
            L.append(f"Total inflow:      {r['inflow']:.4e} {u('flux')} per unit width")
            L.append(f"Total outflow:     {r['outflow']:.4e} {u('flux')} per unit width")
            for name, q in (r.get("flux_sections") or {}).items():
                L.append(f"Flux section {name}: {q:.4e} {u('flux')}")
        if t == "seepage":
            L.append(f"Head range:        {min(r['head']):.3f} to {max(r['head']):.3f} {u('length')}")
            L.append(f"Seepage face:      {len(r['seepage_face_nodes'])} nodes")
        if "balance_error" in r:
            L.append(f"Balance error:     {100 * r['balance_error']:.4f} % (storage change vs boundary flow)")
        if r.get("climate"):
            cl = r["climate"]
            L.append(f"Climate:           rainfall {cl['rainfall']:.4g}, actual evaporation {cl['evaporation']:.4g}, "
                     f"runoff {cl['runoff']:.4g} {u('length')}3 per unit width")
            if cl.get("potential_transpiration"):
                L.append(f"Transpiration:     actual {cl['transpiration']:.4g} of potential "
                         f"{cl['potential_transpiration']:.4g} {u('length')}3 per unit width")
        if t == "stress":
            if r.get("srm_fos"):
                L.append(f"Strength reduction factor of safety: {r['srm_fos']:.3f}")
            L.append(f"Max displacement:  {max(abs(v) for v in r['dx'] + r['dy']):.5g} {u('length')}")
            L.append(f"Vertical stress:   {min(r['sy']):.2f} to {max(r['sy']):.2f} {u('pressure')} (compression +)")
            L.append(f"Yielded elements:  {sum(r.get('yielded', []))} of {len(r['tris'])}")
            for name, (rx, ry) in (r.get("reactions") or {}).items():
                L.append(f"Reaction {name:<14} x {rx:>12.4g}   y {ry:>12.4g} {u('force')}")
            if r.get("settlement_history"):
                L.append(f"Settlement:        immediate {r['settlement_history'][0]:.5g}, final "
                         f"{r['settlement_history'][-1]:.5g} {u('length')}")
            if r.get("inactive") and any(r["inactive"]):
                L.append(f"Construction stage: {sum(r['inactive'])} elements not built or excavated")
            for st in r.get("structures") or []:
                L.append("")
                L.append(f"Structure '{st['name']}' ({st['type']}): max axial force {st['max_N']:.4g} "
                         f"{u('force')}/{u('length')} (tension +)"
                         + (f", max bending moment {st['max_M']:.4g} {u('force')}.{u('length')}/{u('length')}"
                            if st["type"] == "beam" else ""))
                L.append(f"  {'x1':>8}{'y1':>8}{'x2':>8}{'y2':>8}{'N':>11}{'V':>11}{'M1':>11}{'M2':>11}")
                for e in st["elements"]:
                    L.append(f"  {e['x1']:>8.2f}{e['y1']:>8.2f}{e['x2']:>8.2f}{e['y2']:>8.2f}{e['N']:>11.3f}"
                             f"{e['V']:>11.3f}{e['M1']:>11.3f}{e['M2']:>11.3f}")
        if t == "dynamic":
            L.append(f"Peak acceleration: {max(r['max_acceleration']):.3f} g")
            if r.get("natural_frequency"):
                L.append(f"Natural frequency: {r['natural_frequency']:.3f} Hz")
            if r.get("eq_iterations"):
                L.append(f"Equivalent linear: {len(r['eq_iterations'])} iterations, last change "
                         f"{100 * r['eq_iterations'][-1]:.1f} %")
        if t == "thermal":
            L.append(f"Temperature:       {min(r['temperature']):.2f} to {max(r['temperature']):.2f} "
                     f"{u('temperature')}")
            L.append(f"Frozen fraction:   max {max(r['frozen_fraction']):.2f}")
        if t == "transport":
            L.append(f"Concentration:     max {max(r['concentration']):.4g} {u('concentration')}")
            L.append(f"Grid Peclet:       max {r['max_grid_peclet']:.2f}")
            for prt in r.get("particles", []):
                end = prt["path"][-1]
                L.append(f"Particle {prt['start']}: ends at ({end[0]:.2f}, {end[1]:.2f}) after {prt['time']:.4g} s")
    return "\n".join(L)
