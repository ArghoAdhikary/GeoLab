"""Climate (rainfall and evaporation) boundary of transient seepage."""
import math

import numpy as np
import pytest

from geolab.model import new_project
from geolab.seep import KELVIN, evaporation_ratio, run_seepage

DAY = 86400.0


def column(H=3.0, wt=2.9):
    p = new_project(kind="seepage")
    m = p.materials[0]
    m.hyd_model, m.k_sat, m.theta_s, m.theta_r, m.vg_alpha, m.vg_n, m.mv = \
        "van_genuchten", 1e-6, 0.40, 0.05, 1.5, 1.8, 1e-6
    p.add_region([(0, 0), (1, 0), (1, H), (0, H)], m.id)
    p.piezometric_line = [[0, wt], [1, wt]]
    a = p.analyses[0]
    a.transient, a.initial, a.mesh_size, a.max_iter = True, "water_table", 0.1, 80
    p.add_bc("Water table", "head", wt, [(0, 0), (1, 0)])
    return p, m, a


def test_evaporation_ratio_follows_kelvin():
    assert evaporation_ratio(0.0) == pytest.approx(1.0)
    assert evaporation_ratio(5.0) == pytest.approx(1.0)
    # suction where the surface humidity equals the air humidity: no evaporation
    hp_dry = math.log(0.5) / KELVIN
    assert evaporation_ratio(hp_dry, 0.5) == pytest.approx(0.0, abs=1e-9)
    hp = 0.5 * hp_dry
    assert evaporation_ratio(hp, 0.5) == pytest.approx((math.exp(KELVIN * hp) - 0.5) / 0.5)


def test_wet_soil_evaporates_at_potential_rate():
    p, m, a = column(wt=2.95)
    pe = 2e-8                                    # about 1.7 mm/day
    a.duration, a.n_steps = 5 * DAY, 20
    p.add_bc("Weather", "climate", 0.0, [(0, 3), (1, 3)], value2=pe)
    r = run_seepage(p, a)
    cl = r["climate"]
    assert cl["evaporation"] == pytest.approx(pe * 1.0 * a.duration, rel=0.01)
    assert r["balance_error"] < 0.02


def test_heavy_rain_ponds_and_runs_off():
    p, m, a = column(wt=1.0)
    rain = 5 * m.k_sat
    a.duration, a.n_steps = 2 * DAY, 30
    p.add_bc("Storm", "climate", rain, [(0, 3), (1, 3)], value2=0.0)
    r = run_seepage(p, a)
    cl = r["climate"]
    assert cl["rainfall"] == pytest.approx(rain * a.duration, rel=1e-6)
    assert cl["runoff"] > 0.3 * cl["rainfall"]                    # most rain cannot enter
    assert r["storage_change"] > 0
    assert r["balance_error"] < 0.02
    hp_top = np.array(r["pressure_head"])[np.array(r["nodes"])[:, 1] > 2.99]
    assert hp_top.max() == pytest.approx(0.0, abs=1e-6)            # ponded surface held at zero pressure


def test_dry_surface_limits_evaporation():
    p, m, a = column(wt=0.0)
    m.vg_alpha, m.vg_n = 0.5, 1.3
    pe = 1e-7
    a.duration, a.n_steps = 10 * DAY, 30
    p.add_bc("Weather", "climate", 0.0, [(0, 3), (1, 3)], value2=pe, humidity=0.9)
    r = run_seepage(p, a)
    assert r["climate"]["evaporation"] < 0.9 * pe * a.duration     # dry surface cannot evaporate at the potential rate
    assert r["balance_error"] < 0.03
