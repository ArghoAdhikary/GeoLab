"""Design report: the whole project in one document, ready to submit - inputs, a picture of every solved
analysis, the results, the design code check, liquefaction and monitoring when present, and the detailed
analysis reports as an appendix. Written as Word (.docx) or turned into PDF by the program (HTML)."""
from __future__ import annotations

import base64
import datetime
import html

import numpy as np

from . import __version__, codes
from .model import ANALYSIS_KINDS, SLOPE_METHODS, STRENGTH_MODELS
from .report import build_report


def _f(v, nd=3):
    if v is None:
        return "-"
    if isinstance(v, (int, float)) and (abs(v) >= 1e4 or (0 < abs(v) < 1e-3)):
        return f"{v:.3e}"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def key_results(project, a) -> list[list[str]]:
    r = a.results or {}
    u = project.unit
    rows = []
    if a.kind == "slope":
        c = r.get("critical")
        if c:
            rows.append(["Factor of safety", f"{c['fos']:.3f} ({SLOPE_METHODS.get(a.method, a.method)})"])
            for m, v in c.get("all_methods", {}).items():
                if v.get("fos") is not None and m != a.method:
                    rows.append([f"  {SLOPE_METHODS.get(m, m)}", f"{v['fos']:.3f}"])
            rows.append(["Trial slip surfaces", f"{r.get('n_valid', 0)} valid of {r.get('n_total', 0)}"])
            if r.get("drawdown"):
                d = r["drawdown"]
                rows.append(["Rapid drawdown stages", ", ".join(f"{k}: {v:.3f}" for k, v in d.items()
                                                                if isinstance(v, float) and k != "level")])
            if r.get("probability", {}).get("n"):
                pr = r["probability"]
                rows.append(["Probability of failure", f"{100 * pr['pf']:.2f} % (mean F {pr['mean']:.3f}, "
                                                       f"reliability index {_f(pr.get('reliability_index'), 2)})"])
            if r.get("newmark", {}).get("displacement") is not None:
                rows.append(["Newmark displacement", f"{r['newmark']['displacement']:.3f} {u('length')} "
                                                     f"(ky = {r['newmark']['ky']:.3f})"])
        else:
            rows.append(["Result", r.get("message", "no valid slip surface")])
    elif a.kind == "seepage":
        rows.append(["Inflow", f"{_f(r.get('inflow'))} {u('flux')} per unit width"])
        rows.append(["Outflow", f"{_f(r.get('outflow'))} {u('flux')}"])
        for k, v in (r.get("flux_sections") or {}).items():
            rows.append([f"Flux section '{k}'", f"{_f(v if not isinstance(v, dict) else v.get('total'))}"])
    elif a.kind == "stress":
        if r.get("dx") is not None:
            d = np.hypot(np.asarray(r["dx"]), np.asarray(r["dy"]))
            rows.append(["Largest displacement", f"{d.max():.4f} {u('length')}"])
        if r.get("settlement_history"):
            rows.append(["Settlement (end)", f"{r['settlement_history'][-1]:.4f} {u('length')}"])
        if r.get("srf"):
            rows.append(["Strength reduction factor", f"{r['srf']:.3f}"])
        for s in r.get("structures", []) or []:
            if isinstance(s, dict) and s.get("max_M") is not None:
                rows.append([f"{s.get('name', 'Structure')}", f"M {s['max_M']:.1f}, N {s.get('max_N', 0):.1f}"])
    else:
        for k in ("max_acceleration_peak", "frost_depth", "max_concentration", "inflow"):
            if r.get(k) is not None:
                rows.append([k.replace("_", " ").capitalize(), _f(r[k])])
    return rows


def build(project, images: dict | None = None, include_appendix: bool = True) -> list[tuple]:
    """The report as a list of blocks: ('h', level, text), ('p', text), ('table', rows), ('img', png),
    ('mono', text), ('break',)."""
    images = images or {}
    B: list[tuple] = []
    code = codes.code_of(project)
    B.append(("h", 1, project.title or "Geotechnical design report"))
    meta = [["Project", project.title], ["Prepared by", project.author or "-"],
            ["Date", f"{datetime.date.today():%d %B %Y}"], ["Design code", codes.CODES[code]],
            ["Units", f"{project.units} ({project.unit('length')}, {project.unit('pressure')})"],
            ["Program", f"GeoLab {__version__}"]]
    B.append(("table", [["Item", "Value"]] + meta))
    if project.description:
        B.append(("p", project.description))

    B.append(("h", 2, "1. Materials"))
    rows = [["#", "Material", "Model", f"Unit weight ({project.unit('unit_weight')})",
             f"c ({project.unit('pressure')})", "phi (°)", f"k ({project.unit('k')})"]]
    for m in project.materials:
        rows.append([str(m.id), m.name, STRENGTH_MODELS.get(m.model, m.model), f"{m.unit_weight:g}",
                     f"{m.cohesion:g}", f"{m.phi:g}", f"{m.k_sat:.2e}"])
    B.append(("table", rows))

    B.append(("h", 2, "2. Analyses and results"))
    solved = [a for a in project.analyses if a.results]
    if not solved:
        B.append(("p", "No analysis is solved yet. Solve the analyses (Shift+F5) before making the report."))
    for i, a in enumerate(project.analyses, 1):
        B.append(("h", 3, f"2.{i} {a.name}"))
        parent = project.analysis(a.parent_id)
        B.append(("p", f"{ANALYSIS_KINDS.get(a.kind, a.kind)}" + (f", from '{parent.name}'" if parent else "")
                  + (f". {a.description}" if a.description else "")))
        if a.id in images:
            B.append(("img", images[a.id]))
        if a.results:
            B.append(("table", [["Result", "Value"]] + key_results(project, a)))
        else:
            B.append(("p", "Not solved."))

    slope_solved = [a for a in project.analyses if a.kind == "slope" and a.results and a.results.get("critical")]
    if slope_solved and code != "none":
        B.append(("h", 2, f"3. Design check - {codes.CODES[code]}"))
        rows = [["Analysis", "Design case", "Check", "Value", "Required", "Result"]]
        for c in codes.check_project(project):
            if "error" in c:
                rows.append([c["analysis"], "-", "-", "-", "-", c["error"]])
                continue
            for j, row in enumerate(c["rows"]):
                rows.append([c["analysis"] if j == 0 else "", c["case_label"] if j == 0 else "", row["check"],
                             _f(row["value"]), row["limit"],
                             {True: "PASS", False: "FAIL", None: "n/a"}[row["pass"]]])
        B.append(("table", rows))
        sz = codes.seismic(code, codes.settings_of(project))
        B.append(("p", "Seismic hazard: " + sz["text"]))
        B.append(("p", f"Minimum factors of safety: {codes.MIN_FOS_SOURCE[code]}. The project specification and "
                       "the standard itself govern."))

    liq = (project.code_settings or {}).get("_liquefaction")
    if liq:
        B.append(("h", 2, "4. Liquefaction"))
        B.append(("mono", liq))
    if project.observations:
        from .monitoring import compare, text_report
        for a in solved:
            if a.kind in ("seepage", "stress"):
                try:
                    res = compare(project, a)
                except ValueError:
                    continue
                if res["n_used"]:
                    B.append(("h", 2, f"5. Monitoring - {a.name}"))
                    B.append(("mono", text_report(project, res)))
    if include_appendix and solved:
        B.append(("break",))
        B.append(("h", 2, "Appendix - analysis details"))
        for a in solved:
            B.append(("h", 3, a.name))
            B.append(("mono", build_report(project, a)))
    B.append(("p", "This report was produced by GeoLab. The engineer responsible checks the model, the parameters "
                   "and the results before relying on them."))
    return B


def to_docx(blocks, path, title="Design report", author=""):
    from .docx import Document
    d = Document()
    for b in blocks:
        k = b[0]
        if k == "h":
            d.heading(b[2], b[1])
        elif k == "p":
            d.paragraph(b[1])
        elif k == "table":
            d.table(b[1])
        elif k == "img":
            d.picture(b[1])
        elif k == "mono":
            d.mono(b[1])
        elif k == "break":
            d.page_break()
    d.save(path, title=title, author=author or "GeoLab")


def to_html(blocks, src=None) -> str:
    """HTML of the report. src(i, png) gives the address of picture i (default: an embedded data URI)."""
    out = []
    n_img = 0
    for b in blocks:
        k = b[0]
        if k == "h":
            out.append(f"<h{b[1]}>{html.escape(b[2])}</h{b[1]}>")
        elif k == "p":
            out.append(f"<p>{html.escape(b[1])}</p>")
        elif k == "table":
            rows = b[1]
            tr = [f"<tr>{''.join(f'<th>{html.escape(str(c))}</th>' for c in rows[0])}</tr>"]
            tr += [f"<tr>{''.join(f'<td>{html.escape(str(c))}</td>' for c in r)}</tr>" for r in rows[1:]]
            out.append(f'<table cellspacing="0" cellpadding="3" border="1">{"".join(tr)}</table>')
        elif k == "img":
            n_img += 1
            url = src(n_img, b[1]) if src else f"data:image/png;base64,{base64.b64encode(b[1]).decode()}"
            out.append(f'<p><img width="640" src="{url}"/></p>')
        elif k == "mono":
            out.append(f"<pre>{html.escape(b[1])}</pre>")
        elif k == "break":
            out.append('<div style="page-break-before:always"></div>')
    return "<html><body>" + "\n".join(out) + "</body></html>"
