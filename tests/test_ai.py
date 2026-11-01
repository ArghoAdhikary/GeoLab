"""AI builder tests use a fake client, so they run offline and cost nothing."""
import json
from types import SimpleNamespace

import pytest

from stratalab.ai import MODEL, AIError, generate_project, project_from_ai
from stratalab.slope import run_slope

GOOD = {
    "title": "Cut slope", "description": "test", "units": "metric",
    "materials": [{"name": "Clay", "model": "mohr_coulomb", "unit_weight": 19, "cohesion": 10, "phi": 25},
                  {"name": "Sand", "model": "mohr_coulomb", "unit_weight": 20, "cohesion": 0, "phi": 35}],
    "regions": [
        {"material_index": 1, "points": [{"x": 0, "y": 0}, {"x": 80, "y": 0}, {"x": 80, "y": 6}, {"x": 0, "y": 6}]},
        {"material_index": 0, "points": [{"x": 0, "y": 6}, {"x": 80, "y": 6}, {"x": 80, "y": 18}, {"x": 48, "y": 18},
                                          {"x": 30, "y": 6}]},
    ],
    "piezometric_line": [{"x": 0, "y": 6}, {"x": 30, "y": 6}, {"x": 48, "y": 15}, {"x": 80, "y": 15}],
    "surcharges": [{"x1": 52, "x2": 60, "q": 20}],
    "method": "morgenstern_price", "pore_pressure": "piezometric", "ru": 0, "seismic_kh": 0,
    "assumptions": "Sand strength assumed.",
}


class FakeClient:
    def __init__(self, payload, stop="end_turn"):
        self.payload, self.stop, self.calls = payload, stop, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


def test_generate_project_builds_solvable_model():
    c = FakeClient(GOOD)
    p, notes = generate_project("a cut slope", client=c)
    kw = c.calls[0]
    assert kw["model"] == MODEL
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert len(p.regions) == 2 and p.analyses[0].pwp == "piezometric"
    assert notes == "Sand strength assumed."
    r = run_slope(p, p.analyses[0])
    assert r["critical"] and 0.5 < r["critical"]["fos"] < 5


def test_bad_material_index_rejected():
    bad = json.loads(json.dumps(GOOD))
    bad["regions"][0]["material_index"] = 7
    with pytest.raises(AIError, match="material"):
        project_from_ai(bad)


def test_crossing_polygon_rejected():
    bad = json.loads(json.dumps(GOOD))
    bad["regions"][0]["points"] = [{"x": 0, "y": 0}, {"x": 10, "y": 10}, {"x": 10, "y": 0}, {"x": 0, "y": 10}]
    with pytest.raises(AIError, match="not valid"):
        project_from_ai(bad)


def test_refusal_and_truncation_reported():
    with pytest.raises(AIError, match="declined"):
        generate_project("x", client=FakeClient(GOOD, stop="refusal"))
    with pytest.raises(AIError, match="cut off"):
        generate_project("x", client=FakeClient(GOOD, stop="max_tokens"))
    with pytest.raises(AIError, match="Describe"):
        generate_project("   ", client=FakeClient(GOOD))
