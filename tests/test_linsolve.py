"""The sparse direct solver: SuperLU everywhere, Intel MKL PARDISO for large systems where available."""
import numpy as np
import pytest
import scipy.sparse as sp

from geolab import linsolve


def _system(n=40, nonsym=False):
    I = sp.identity(n)
    T = sp.diags([-1.0, 2.0, -1.0], [-1, 0, 1], (n, n))
    A = sp.kron(I, T) + sp.kron(T, I)
    A = sp.kron(A, np.array([[2.0, 0.5], [0.5 if not nonsym else 0.2, 2.0]])).tocsr()
    rng = np.random.default_rng(1)
    return A, rng.random(A.shape[0]), rng.random((A.shape[0], 3))


def test_superlu_solves():
    A, b, B = _system()
    f = linsolve._SuperLU(A)
    assert np.abs(A @ f.solve(b) - b).max() < 1e-10
    assert np.abs(A @ f.solve(B) - B).max() < 1e-10


def test_small_systems_use_superlu():
    A, b, _ = _system(10)
    assert isinstance(linsolve.factorize(A), linsolve._SuperLU)
    assert np.allclose(A @ linsolve.solve(A, b), b)


@pytest.mark.skipif(linsolve._load() is None, reason="MKL PARDISO not available here")
@pytest.mark.parametrize("nonsym", [False, True])
def test_pardiso_matches_superlu(nonsym, monkeypatch):
    A, b, B = _system(nonsym=nonsym)
    p, s = linsolve._Pardiso(A), linsolve._SuperLU(A)
    assert np.allclose(p.solve(b), s.solve(b), rtol=1e-10, atol=1e-12)
    assert np.allclose(p.solve(B), s.solve(B), rtol=1e-10, atol=1e-12)
    x1 = p.solve(b)
    assert np.array_equal(p.solve(b), x1)              # the factors are reused, same answer each time
    monkeypatch.setattr(linsolve, "PARALLEL_FROM", 100)
    assert isinstance(linsolve.factorize(A), linsolve._Pardiso)
    assert "MKL" in linsolve.backend()


def test_switch_off(monkeypatch):
    monkeypatch.setattr(linsolve, "_pardiso", None)
    monkeypatch.setattr(linsolve, "_pardiso_error", "")
    monkeypatch.setenv("GEOLAB_SOLVER", "superlu")
    assert linsolve._load() is None and linsolve.backend() == "SciPy SuperLU"
    monkeypatch.setattr(linsolve, "PARALLEL_FROM", 1)
    A, b, _ = _system(5)
    assert isinstance(linsolve.factorize(A), linsolve._SuperLU)
