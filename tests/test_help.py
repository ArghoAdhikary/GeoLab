"""The manual and tutorials: every number a tutorial quotes is what GeoLab computes today."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from geolab import help as docs
from geolab.examples import EXAMPLES, example_file_name, write_example_files
from geolab.quick import quick_slope
from geolab.solver import solve_all

_solved = {}


def _project(src, tut):
    if src not in _solved:
        if src.startswith("@quick"):
            q = dict(tut["quick"])
            for mod in src.split()[1:]:
                k, v = mod.split("=")
                q[k] = None if v == "none" else float(v)
            p = quick_slope(q)
        else:
            p = EXAMPLES[src]()
        errors = [e for e in solve_all(p) if e[1]]
        assert not errors, errors
        _solved[src] = p
    return _solved[src]


CHECKS = [(t["path"].name, src, idx, path, val, tol, t)
          for t in docs.tutorials() for (src, idx, path, val, tol) in t["checks"]]


def test_manual_and_tutorials_are_there():
    ch, tu = docs.chapters(), docs.tutorials()
    assert len(ch) >= 10 and len(tu) >= 10
    for page in ch + tu:
        assert page["text"].startswith(("# ", "<!--")), page["path"]
        assert page["title"] and "#" not in page["title"]
    for t in tu:
        assert t["checks"], f"{t['path'].name} quotes no checked result"
        if t["example"]:
            assert t["example"] in EXAMPLES, t["example"]
        for src, *_ in t["checks"]:
            assert src.startswith("@quick") or src in EXAMPLES, src


def test_markdown_cleaning():
    t = docs.tutorials()[0]["text"]
    assert "<!--" in t
    clean = docs.clean_markdown(t, with_images=False)
    assert "<!--" not in clean and "![" not in clean and clean.startswith("# Tutorial 1")
    assert "![" in docs.clean_markdown(t, with_images=True)


@pytest.mark.parametrize("name,src,idx,path,val,tol,tut", CHECKS, ids=[f"{c[0]}:{c[3]}:{c[1]}" for c in CHECKS])
def test_tutorial_numbers(name, src, idx, path, val, tol, tut):
    p = _project(src, tut)
    got = docs.result_value(p.analyses[idx].results, path)
    assert got == pytest.approx(val, rel=tol), f"{name} says {val} for {src} {path}, GeoLab gives {got}"


def test_example_files(tmp_path):
    from geolab.fileio import load_project
    files = write_example_files(tmp_path, solve=False)
    assert len(files) == len(EXAMPLES) and len({f.name for f in files}) == len(files)
    assert files[0].name == "01 Homogeneous slope (benchmark).slab"
    for name, f in zip(EXAMPLES, files):
        assert f.name == example_file_name(name)
        p = load_project(f)
        assert p.regions and p.analyses
