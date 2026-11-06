"""GeoLab Mobile bridge (mobile/www/mobile_api.py), run with the normal Python engine."""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mobile" / "www"))
import mobile_api as m  # noqa: E402


def _fast(s):
    a = m.P.analyses[0]
    a.search.n_entry = a.search.n_exit = 4
    a.search.n_radius = 3
    return s


def test_quick_slope_layers_and_solve():
    s = json.loads(m.quick_slope(json.dumps({
        "height": 8, "ratio": 2, "crest": 20, "toe": 20, "base": 5, "water": 3, "surcharge": 10,
        "layers": [{"name": "Clay", "c": 10, "phi": 25, "gamma": 18, "thickness": 4},
                   {"name": "Sand", "c": 0, "phi": 35, "gamma": 20}]})))
    assert [r["pts"] for r in s["regions"]][0] == [[28.0, 9.0], [56.0, 9.0], [56.0, 13.0], [36.0, 13.0]]
    assert s["piezo"] and s["surcharges"] and s["analyses"][0]["pwp"] == "piezometric"
    _fast(s)
    s = json.loads(m.solve_one(1))
    d = s["analyses"][0]["draw"]
    assert 0.5 < d["fos"] < 5 and d["slip"] and d["slices"] and "Bishop Simplified" in d["methods"]
    assert "GeoLab" in json.loads(m.report(1))["text"]


def test_edits_validate_and_clear_results():
    m.quick_slope(json.dumps({"height": 6, "ratio": 1.5, "water": 2}))
    _fast(None)
    m.solve_one(1)
    s = json.loads(m.set_material(1, "cohesion", "12"))
    assert s["materials"][0]["cohesion"] == 12 and not s["analyses"][0]["solved"]
    s = json.loads(m.move_water(0.5))
    assert s["piezo"][-1][1] == 9.5
    s = json.loads(m.set_analysis(1, "method", "bishop"))
    assert s["analyses"][0]["method"] == "bishop"
    for bad in [("set_material", (1, "phi", "95")), ("set_analysis", (1, "method", "magic")),
                ("set_material", (1, "unit_weight", "-1"))]:
        try:
            getattr(m, bad[0])(*bad[1])
        except ValueError:
            continue
        raise AssertionError(f"{bad} should fail")


def test_save_open_and_autosave_round_trip():
    m.open_example("Homogeneous slope (benchmark)")
    saved = json.loads(m.save_file())
    assert saved["name"].endswith(".slab")
    s = json.loads(m.open_file(saved["name"], saved["b64"]))
    assert s["title"] == "Homogeneous slope (benchmark)"
    text = m.to_json()
    s = json.loads(m.from_json(text))
    assert len(s["regions"]) == 1
    assert base64.b64decode(saved["b64"])[:2] == b"PK"


def test_seepage_field_drawing():
    m.open_example("Earth dam: seepage + stability")
    seep = next(a for a in m.P.analyses if a.kind == "seepage")
    s = json.loads(m.solve_one(seep.id))
    d = next(a for a in s["analyses"] if a["kind"] == "seepage")["draw"]
    assert d["tris"] and "head" in d["fields"] and len(d["fields"]["head"]["v"]) == len(d["nodes"])
