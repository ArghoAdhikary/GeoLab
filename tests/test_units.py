"""Converting a project between metric and imperial units."""
import copy

import pytest

from geolab.examples import EXAMPLES
from geolab.solver import solve
from geolab.units import FT, PSF, convert_project


def test_round_trip_restores_every_value():
    p = EXAMPLES["Layered slope with water table"]()
    before = copy.deepcopy(p.to_dict())
    notes = convert_project(p, "imperial")
    assert p.units == "imperial" and notes
    assert p.regions[0].points[1][0] == pytest.approx(80 * FT)
    assert p.materials[0].cohesion == pytest.approx(8.0 * PSF)
    convert_project(p, "metric")
    after = p.to_dict()

    def close(a, b):
        if isinstance(a, dict):
            return all(close(a[k], b[k]) for k in a)
        if isinstance(a, list):
            return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
        if isinstance(a, (int, float)) and not isinstance(a, bool):
            return b == pytest.approx(a, rel=1e-9, abs=1e-12)
        return a == b
    assert close(before, after)


def test_factor_of_safety_is_the_same_in_both_unit_systems():
    p = EXAMPLES["Homogeneous slope (benchmark)"]()
    a = p.analyses[0]
    a.search.n_entry = a.search.n_exit = 5
    a.search.n_radius = 3
    F_m = solve(p, a)["critical"]["fos"]
    convert_project(p, "imperial")
    F_i = solve(p, p.analyses[0])["critical"]["fos"]
    assert F_i == pytest.approx(F_m, rel=2e-3)
