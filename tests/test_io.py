import csv
import subprocess
import sys

import pytest

from stratalab.examples import EXAMPLES, layered_slope_with_water
from stratalab.fileio import export_results_csv, import_points_csv, load_project, save_project
from stratalab.model import Project
from stratalab.report import build_report
from stratalab.solver import solve_all


def test_roundtrip_with_results(tmp_path):
    p = layered_slope_with_water()
    p.analyses[0].n_samples = 30
    solve_all(p)
    f = tmp_path / "x.slab"
    save_project(p, f)
    q = load_project(f)
    assert q.to_dict() == p.to_dict()
    assert q.analyses[0].results["critical"]["fos"] == p.analyses[0].results["critical"]["fos"]


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_examples_roundtrip_without_results(tmp_path, name):
    p = EXAMPLES[name]()
    f = tmp_path / "e.slab"
    save_project(p, f, include_results=False)
    assert load_project(f).to_dict() == p.to_dict()


def test_bad_files(tmp_path):
    bad = tmp_path / "bad.slab"
    bad.write_text("not a zip")
    with pytest.raises(ValueError, match="not a valid"):
        load_project(bad)
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "missing.slab")
    with pytest.raises(ValueError, match="unit"):
        Project.from_dict({"units": "furlongs"})


def test_csv_export_and_points_import(tmp_path):
    p = layered_slope_with_water()
    p.analyses[0].probabilistic = False
    solve_all(p)
    out = tmp_path / "r.csv"
    export_results_csv(p, p.analyses[0], out)
    rows = list(csv.reader(out.open()))
    assert rows[1][0] == "slice" and len(rows) == 2 + p.analyses[0].n_slices
    pts = tmp_path / "p.csv"
    pts.write_text("x,y\n0,0\n10,0\n10,5\n")
    assert import_points_csv(pts) == [[0, 0], [10, 0], [10, 5]]


def test_report_mentions_key_results():
    p = layered_slope_with_water()
    p.analyses[0].n_samples = 30
    solve_all(p)
    txt = build_report(p, p.analyses[0])
    assert "Critical factor of safety" in txt and "probability of failure" in txt


def test_cli_solve(tmp_path):
    from stratalab.examples import homogeneous_slope
    f = tmp_path / "h.slab"
    save_project(homogeneous_slope(), f)
    pdf = tmp_path / "h.pdf"
    r = subprocess.run([sys.executable, "-m", "stratalab", "solve", str(f), "--save", "--pdf", str(pdf)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert "Critical factor of safety" in r.stdout
    assert load_project(f).analyses[0].results is not None
    assert pdf.stat().st_size > 10000
