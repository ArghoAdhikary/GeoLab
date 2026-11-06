"""Every built-in example solves, and independent methods agree with each other."""
import pytest

from geolab.examples import EXAMPLES, slope_fe_stress
from geolab.solver import solve_all, verify


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_example_solves(name):
    p = EXAMPLES[name]()
    for a in p.analyses:
        assert verify(p, a) == [], (a.name, verify(p, a))
    out = solve_all(p)
    assert all(err is None for _, err in out), out
    for a in p.analyses:
        assert a.results is not None
        assert a.results.get("converged", True), a.name
        if a.kind == "slope":
            assert a.results["critical"] is not None


def test_limit_equilibrium_finite_element_and_strength_reduction_agree():
    p = slope_fe_stress()
    solve_all(p)
    le, _ins, fe, srm = p.analyses
    F_le = le.results["critical"]["fos"]
    assert fe.results["critical"]["fos"] == pytest.approx(F_le, rel=0.05)
    assert srm.results["srm_fos"] == pytest.approx(F_le, rel=0.05)
