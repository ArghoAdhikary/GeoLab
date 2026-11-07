"""Design tools of 2.10: quick re-evaluation, back-analysis, optimizer, design codes, liquefaction,
boreholes, rainfall, monitoring, templates, the Word report, Bangla and the photo builder (fake client)."""
import io
import json
import math
import zipfile
from types import SimpleNamespace

import pytest

from geolab import backcalc, borehole, codes, designreport, i18n, liquefaction, monitoring, optimize, rainfall
from geolab.examples import EXAMPLES, earth_dam, homogeneous_slope
from geolab.geometry import validate_geometry
from geolab.quick import quick_slope
from geolab.solver import solve
from geolab.whatif import SurfacePool, apply_changes, bisect_target


@pytest.fixture(scope="module")
def slope():
    p = homogeneous_slope()
    solve(p, p.analyses[0])
    return p


@pytest.fixture(scope="module")
def pool(slope):
    return SurfacePool(slope, slope.analyses[0])


def test_root_finder():
    x, F, _, st = bisect_target(lambda v: 3 - math.sqrt(v), 0, 9, 1.5)
    assert st == "ok" and x == pytest.approx(2.25, rel=1e-3) and F >= 1.5 - 1e-9
    assert bisect_target(lambda v: 0.5 + 0.0 * v, 0, 1, 1.5)[3] == "below"
    assert bisect_target(lambda v: 2 + v, 0, 1, 1.5)[3] == "above"


def test_pool_matches_search_and_changes(slope, pool):
    a = slope.analyses[0]
    assert pool.fos() == pytest.approx(a.results["critical"]["fos"], rel=1e-6)
    assert pool.fos({"c_factor": 2.0}) > pool.fos() > pool.fos({"tanphi_factor": 0.8})
    p2, a2 = apply_changes(slope, a, {"m1.cohesion": 10, "kh": 0.1})
    assert p2.material(1).cohesion == 10 and a2.kh == 0.1 and slope.material(1).cohesion == 3.0


def test_back_analysis_cohesion_and_line(slope, pool):
    r = backcalc.back_strength(slope, slope.analyses[0], 1, "cohesion", 1.0, pool=pool)
    assert r["status"] == "ok" and r["value"] == pytest.approx(3.22, abs=0.03) and r["fos"] == pytest.approx(1.0, abs=2e-3)
    line = backcalc.c_phi_line(slope, slope.analyses[0], 1, 1.0, phis=[15, 25], pool=pool)["rows"]
    assert line[0]["c"] == pytest.approx(7.0, abs=0.2) and line[1]["c"] < 0.5


def test_optimizer_load_and_slope_ratio(slope):
    r = optimize.optimize(slope, slope.analyses[0], "max_surcharge", 0.9, full_check=False)
    assert r["status"] == "ok" and r["value"] == pytest.approx(19.5, rel=0.05)
    assert optimize.available(slope, slope.analyses[0])["slope_ratio"]          # not a Quick Slope
    q = quick_slope({"height": 6, "ratio": 1.5, "layers": [{"name": "Clay", "c": 8, "phi": 25, "gamma": 19}]})
    a = q.analyses[0]
    solve(q, a)
    r = optimize.optimize(q, a, "slope_ratio", a.results["critical"]["fos"] + 0.2, 1.5, 4.0, full_check=False)
    assert r["status"] == "ok" and 1.5 < r["value"] < 4.0 and r["fos"] >= r["target"] - 1e-6


def test_quick_slope_berm_and_scour():
    for q in ({"berm": 3}, {"scour": 2, "toe": 20}):
        p = quick_slope(dict({"height": 8, "ratio": 2}, **q))
        assert not validate_geometry(p) and p.quick


def test_codes_seismic_and_checks(slope):
    a = codes.seismic("AS", {"Z": 0.08, "probability": "1/500", "site": "De", "kh_fraction": 0.5})
    assert a["pga"] == pytest.approx(0.088) and a["kh"] == pytest.approx(0.044)
    assert codes.seismic("AS", {"Z": 0.03, "probability": "1/500", "site": "Be"})["pga"] == pytest.approx(0.08)
    b = codes.seismic("BNBC", {"zone": 4, "site": "SD", "importance": "II", "kh_fraction": 0.5})
    assert b["pga"] == pytest.approx(2 / 3 * 0.36 * 1.35) and b["kh"] == pytest.approx(0.162)
    assert slope.design_code == "AS" and codes.code_of(slope) == "AS"
    c = codes.check_slope(slope, slope.analyses[0])
    assert c["case"] == "long_term" and c["required"] == 1.5 and not c["pass_all"]
    assert c["factored_fos"] < c["fos"]
    assert "BNBC" in codes.CODES and "FAIL" in codes.summary_text(slope)


def test_liquefaction_spt_hand_check():
    r = liquefaction.spt([{"depth": 4.5, "N": 9, "fc": 25}], 1.0, 0.2, 7.5)
    row = r["rows"][0]
    assert row["N160cs"] == pytest.approx(17.0, abs=0.2)
    assert row["CRR75"] == pytest.approx(0.174, abs=0.003)
    assert row["CSR"] == pytest.approx(0.212, abs=0.003)
    assert row["FS"] == pytest.approx(0.89, abs=0.02) and row["status"] == "liquefies"
    clay = liquefaction.spt([{"depth": 4, "N": 3, "fc": 90, "pi": 20}], 1.0, 0.3)["rows"][0]
    assert clay["FS"] is None and "clay" in clay["note"]
    c = liquefaction.cpt([{"depth": 3, "qc": 3000, "fs": 20}, {"depth": 6, "qc": 1200, "fs": 40}], 1.5, 0.25)
    assert c["rows"][0]["status"] == "liquefies" and c["rows"][1]["FS"] is None and c["LPI"] > 0


def test_boreholes_to_section_and_xlsx(tmp_path):
    holes = borehole.parse_logs(borehole.SAMPLE_BOREHOLES)
    assert [h["hole"] for h in holes] == ["BH1", "BH2", "BH3"]
    p, params = borehole.build_section(holes, 2.0)
    assert not validate_geometry(p) and len(p.materials) == 3 and p.piezometric_line
    assert params["Silty clay (CL)"]["kind"] == "clay" and 30 < params["Dense sand (SP)"]["phi"] < 45
    # the same table as an Excel file (inline strings)
    rows = [r.split(",") for r in borehole.SAMPLE_BOREHOLES.strip().splitlines()]

    def cell(c, j, i):
        ref = f"{chr(65 + j)}{i + 1}"
        try:
            float(c)
            return f'<c r="{ref}"><v>{c}</v></c>'
        except ValueError:
            return f'<c r="{ref}" t="inlineStr"><is><t>{c}</t></is></c>'
    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             + "".join(f'<row r="{i + 1}">' + "".join(cell(c, j, i) for j, c in enumerate(r) if c) + "</row>"
                       for i, r in enumerate(rows)) + "</sheetData></worksheet>")
    x = tmp_path / "logs.xlsx"
    with zipfile.ZipFile(x, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    assert len(borehole.parse_logs(x)) == 3
    cpt = borehole.parse_logs("hole,x,ground,depth,qc,fs\nC1,0,5,1,2.5,0.02\nC1,0,5,2,3.0,0.03\nC1,0,5,3,0.8,0.04\n")
    assert cpt[0]["kind"] == "cpt" and cpt[0]["readings"][0]["qc"] == 2500


def test_rainfall_sources_and_apply():
    payload = {"daily": {"time": ["2024-06-01", "2024-06-02", "2024-06-03"], "precipitation_sum": [10, 250, None],
                         "et0_fao_evapotranspiration": [3, 2, 4]}}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    seen = {}

    def opener(req, timeout):
        seen["url"] = req.full_url
        return Resp(json.dumps(payload).encode())
    s = rainfall.fetch_open_meteo(22.36, 91.78, "2024-06-01", "2024-06-03", opener=opener)
    assert "latitude=22.3600" in seen["url"] and s["rain"] == [10.0, 250.0, 0.0]
    st = rainfall.stats(s)
    assert st["total"] == 260 and st["max_day"] == 250
    p = EXAMPLES["Rainfall and evaporation on a slope"]()
    msg = rainfall.apply_to_project(p, s)
    bc = next(b for b in p.boundary_conditions if b.type == "climate")
    assert bc.at(86400 * 1.5) == pytest.approx(250 / 1000 / 86400) and p.analyses[0].duration == 3 * 86400
    assert "260 mm" in msg
    assert rainfall.design_storm(500, 5, 5)["rain"][:5] == [100.0] * 5
    assert rainfall.from_csv("date,rain,et0\n1,5,2\n2,0,3\n")["rain"] == [5.0, 0.0]
    with pytest.raises(ValueError):
        rainfall.fetch_open_meteo(95, 0, "2024-01-01", "2024-01-02")


def test_monitoring_and_k_calibration():
    p = earth_dam()
    seep = p.analyses[0]
    solve(p, seep)
    pts = [(20.0, 4.0), (40.0, 3.0), (55.0, 2.0)]
    true_heads = backcalc.head_at(seep.results, pts)
    text = "instrument,kind,x,y,time,value\n" + "\n".join(
        f"P{i},head,{x},{y},,{h:.4f}" for i, ((x, y), h) in enumerate(zip(pts, true_heads)))
    p.observations = monitoring.parse(text)
    res = monitoring.compare(p, seep)
    assert res["n_used"] == 3 and res["rms"]["head"] < 1e-3
    assert "RMS error" in monitoring.text_report(p, res)
    assert monitoring.parse_time("2 d") == 172800
    # put k of the fill off by 10 and let the calibration find it again
    true_k = p.material(1).k_sat
    p.material(1).k_sat = true_k * 10
    obs = [{"x": x, "y": y, "head": h} for (x, y), h in zip(pts, true_heads)]
    r = backcalc.calibrate_k(p, seep, obs, [1], max_evals=40)
    assert r["rms_after"] < 0.25 * r["rms_before"]
    assert abs(math.log10(r["materials"][0]["k_after"] / true_k)) < 0.35


def test_templates_valid():
    from geolab.templates import flood_embankment, riverbank
    rb, fe = riverbank(), flood_embankment()
    assert not validate_geometry(rb) and not validate_geometry(fe)
    assert rb.analyses[1].rapid_drawdown and rb.analyses[2].kh > 0
    assert [a.kind for a in fe.analyses] == ["seepage", "slope", "slope", "slope"]
    with pytest.raises(ValueError):
        riverbank({"flood": 1, "low": 2})


def test_word_report(slope, tmp_path):
    from geolab.docx import Document
    blocks = designreport.build(slope, {slope.analyses[0].id: _png()})
    kinds = [b[0] for b in blocks]
    assert "img" in kinds and "table" in kinds
    text = json.dumps([b for b in blocks if b[0] != "img"])
    assert "Design check" in text and "FAIL" in text and "0.987" in text
    path = tmp_path / "r.docx"
    designreport.to_docx(blocks, path, title="T")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        doc = z.read("word/document.xml").decode()
    assert "word/media/image1.png" in names and "Homogeneous slope" in doc
    assert "<img" in designreport.to_html(blocks)
    d = Document()
    d.paragraph("বাংলা")
    d.save(tmp_path / "bn.docx")


def _png():
    import struct
    import zlib
    raw = b"\x00\xff\x00\x00"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_bangla_translation():
    try:
        i18n.set_language("bn")
        assert i18n.tr("&File") == "ফাইল"
        assert i18n.tr("&Materials...") == "মাটির বৈশিষ্ট্য..."
        assert i18n.tr("Something new") == "Something new"
    finally:
        i18n.set_language("en")
    assert i18n.tr("&File") == "&File"


def test_photo_builder_with_fake_client():
    from geolab.ai import AIError, generate_from_image
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_ai import GOOD, FakeClient
    c = FakeClient(GOOD)
    p, notes = generate_from_image(_png(), "image/png", "6 m bank", client=c)
    content = c.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert p.regions and notes
    with pytest.raises(AIError):
        generate_from_image(b"x", "image/bmp", client=c)


def test_console_runs_code():
    from geolab.ui.console import run_code
    ns = {"x": 2}
    assert run_code("x * 21", ns).strip() == "42"
    assert "ZeroDivisionError" in run_code("1/0", ns)
    run_code("y = x + 1\nprint(y)", ns)
    assert ns["y"] == 3
