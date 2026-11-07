"""Write Excel workbooks (.xlsx) without extra libraries, and the workbook of a whole project's results."""
from __future__ import annotations

import math
import re
import zipfile
from xml.sax.saxutils import escape


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, v, bold=False):
    st = ' s="1"' if bold else ""
    if isinstance(v, bool):
        v = "yes" if v else "no"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not math.isfinite(v):
            v = "inf" if v > 0 else ("-inf" if v < 0 else "")
        else:
            return f'<c r="{ref}"{st}><v>{v!r}</v></c>'
    t = escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", "" if v is None else str(v)))
    return f'<c r="{ref}"{st} t="inlineStr"><is><t xml:space="preserve">{t}</t></is></c>'


def _sheet(rows):
    out = []
    widths = {}
    for r, row in enumerate(rows):
        cells = "".join(_cell(f"{_col(c)}{r + 1}", v, bold=(r == 0)) for c, v in enumerate(row))
        out.append(f'<row r="{r + 1}">{cells}</row>')
        for c, v in enumerate(row):
            widths[c] = max(widths.get(c, 8), min(60, len(str(v)) + 2))
    cols = "".join(f'<col min="{c + 1}" max="{c + 1}" width="{w}" customWidth="1"/>' for c, w in sorted(widths.items()))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews>'
            + (f"<cols>{cols}</cols>" if cols else "") + f'<sheetData>{"".join(out)}</sheetData></worksheet>')


def _safe_name(name, used):
    n = re.sub(r"[\[\]:*?/\\]", "", name)[:31] or "Sheet"
    base, k = n, 2
    while n.lower() in used:
        n = f"{base[:28]} {k}"
        k += 1
    used.add(n.lower())
    return n


def write(path, sheets: list[tuple[str, list[list]]]):
    """sheets: [(name, rows)]; the first row of each sheet is bold and frozen."""
    if not sheets:
        sheets = [("Sheet1", [[""]])]
    used = set()
    names = [_safe_name(n, used) for n, _ in sheets]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(len(sheets))) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(names))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                             for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   "</Relationships>")
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                   '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                   "</styleSheet>")
        for i, (_, rows) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet(rows))


def read(path) -> dict:
    """{sheet name: rows of text} (for tests and quick checks)."""
    from .borehole import read_xlsx
    with zipfile.ZipFile(path) as z:
        wb = z.read("xl/workbook.xml").decode()
    names = re.findall(r'<sheet name="([^"]+)"', wb)
    return {names[0]: read_xlsx(path)} if names else {}


def project_sheets(project) -> list[tuple[str, list[list]]]:
    """Summary, materials, results of every analysis, the design check and the critical slices."""
    from . import __version__, codes
    from .designreport import key_results
    from .model import ANALYSIS_KINDS
    u = project.unit
    sheets = [("Project", [["Item", "Value"], ["Title", project.title], ["Author", project.author],
                           ["Units", project.units], ["Design code", codes.CODES[codes.code_of(project)]],
                           ["Program", f"GeoLab {__version__}"], ["Notes", project.description]])]
    rows = [["#", "Material", "Model", f"Unit weight ({u('unit_weight')})", f"c ({u('pressure')})", "phi (deg)",
             f"k ({u('k')})"]]
    for m in project.materials:
        rows.append([m.id, m.name, m.model, m.unit_weight, m.cohesion, m.phi, m.k_sat])
    sheets.append(("Materials", rows))
    rows = [["Analysis", "Kind", "Result", "Value"]]
    for a in project.analyses:
        if not a.results:
            rows.append([a.name, ANALYSIS_KINDS.get(a.kind, a.kind), "Not solved", ""])
            continue
        for k, v in key_results(project, a):
            rows.append([a.name, ANALYSIS_KINDS.get(a.kind, a.kind), k, v])
    sheets.append(("Results", rows))
    checks = []
    try:
        checks = codes.check_project(project)
    except Exception:                                 # noqa: BLE001
        checks = []
    if checks:
        rows = [["Analysis", "Design case", "Check", "Value", "Required", "Pass"]]
        for c in checks:
            for j, r in enumerate(c.get("rows", [])):
                rows.append([c["analysis"], c.get("case_label", ""), r["check"], r["value"], r["limit"],
                             {True: "PASS", False: "FAIL", None: "n/a"}[r["pass"]]])
        sheets.append(("Design check", rows))
    for a in project.analyses:
        crit = (a.results or {}).get("critical") if a.kind == "slope" else None
        sl = crit.get("slices") if crit else None
        if isinstance(sl, list) and sl and isinstance(sl[0], dict):
            keys = list(sl[0].keys())
            sheets.append((f"Slices {a.name}", [keys] + [[s.get(k) for k in keys] for s in sl]))
        elif isinstance(sl, dict) and sl:
            keys = [k for k, v in sl.items() if isinstance(v, (list, tuple))]
            if keys:
                n = len(sl[keys[0]])
                sheets.append((f"Slices {a.name}", [keys] + [[sl[k][i] if i < len(sl[k]) else "" for k in keys]
                                                              for i in range(n)]))
    return sheets


def export_project(project, path):
    write(path, project_sheets(project))
