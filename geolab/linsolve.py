"""Sparse direct solver used by every finite element analysis.

On Windows builds the Intel oneAPI Math Kernel Library (MKL) PARDISO solver is used through
pypardiso: a multi-threaded supernodal LU that is much faster than SuperLU on large meshes.
Where MKL is not available (macOS on Apple silicon, the phone app) SciPy's SuperLU is used.
Both give the same answer to round-off. Set GEOLAB_SOLVER=superlu to force SuperLU.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from scipy.sparse import csr_matrix, issparse
from scipy.sparse.linalg import splu

_pardiso = None          # the pypardiso module, once it loads
_pardiso_error = ""
_mkl = None              # the mkl_rt library (thread control)
# Below this many unknowns MKL runs on one thread: starting threads costs more than it saves, and idle
# MKL threads that keep spinning slow down NumPy's own work on the element matrices.
PARALLEL_FROM = 30000


def _bundled_mkl_rt():
    """In the packaged app the MKL DLLs sit next to the program (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    for name in ("mkl_rt.3.dll", "mkl_rt.2.dll", "mkl_rt.dll", "libmkl_rt.so.2", "libmkl_rt.dylib"):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


def _load():
    global _pardiso, _pardiso_error, _mkl
    if _pardiso is not None or _pardiso_error:
        return _pardiso
    if os.environ.get("GEOLAB_SOLVER", "").lower() == "superlu":
        _pardiso_error = "disabled by GEOLAB_SOLVER"
        return None
    try:
        p = _bundled_mkl_rt()
        if p and "PYPARDISO_MKL_RT" not in os.environ:
            os.environ["PYPARDISO_MKL_RT"] = p
        # idle OpenMP threads go to sleep at once instead of spinning for 200 ms
        os.environ.setdefault("KMP_BLOCKTIME", "0")
        import pypardiso
        # a tiny solve proves the library really loads and works on this CPU
        t = pypardiso.PyPardisoSolver()
        # pypardiso searches the whole Python folder for mkl_rt on every new solver (~0.15 s);
        # remember the library it found so later solvers load it directly
        found = getattr(getattr(t, "libmkl", None), "_name", None)
        if found and os.path.exists(found):
            os.environ["PYPARDISO_MKL_RT"] = found
        _mkl = getattr(t, "libmkl", None)
        a = csr_matrix(np.array([[4.0, 1.0], [1.0, 3.0]]))
        x = t.solve(a, np.array([1.0, 2.0]))
        t.free_memory(everything=True)
        if not np.allclose(a @ x, [1.0, 2.0]):
            raise RuntimeError("PARDISO self-test failed")
        _pardiso = pypardiso
    except Exception as e:                        # noqa: BLE001 - any failure falls back to SuperLU
        _pardiso_error = f"{type(e).__name__}: {e}"
    return _pardiso


def backend() -> str:
    """Name of the solver in use, for the About box and reports."""
    return "Intel MKL PARDISO" if _load() else "SciPy SuperLU"


def backend_note() -> str:
    return "" if _load() else _pardiso_error


class _threads:
    """Run MKL on one thread for small systems, on all cores for large ones."""

    def __init__(self, n):
        self.n = 1 if n < PARALLEL_FROM else 0
        self.prev = None

    def __enter__(self):
        try:
            self.prev = _mkl.MKL_Set_Num_Threads_Local(self.n)
        except Exception:                          # noqa: BLE001
            self.prev = None

    def __exit__(self, *exc):
        if self.prev is not None:
            try:
                _mkl.MKL_Set_Num_Threads_Local(self.prev)
            except Exception:                      # noqa: BLE001
                pass


class _Pardiso:
    """A factorised matrix kept by MKL PARDISO; .solve(b) like SuperLU's object."""

    def __init__(self, A):
        self.A = csr_matrix(A, dtype=float)
        self.A.sort_indices()
        self.s = _pardiso.PyPardisoSolver()
        self.s.set_iparm(1, 1)    # use user iparm values
        self.s.set_iparm(2, 3 if A.shape[0] >= PARALLEL_FROM else 2)   # nested dissection (parallel if large)
        self.s.set_iparm(8, 2)    # up to two iterative refinement steps
        self.s.set_iparm(10, 13)  # pivot perturbation 1e-13
        self.s.set_iparm(11, 1)   # scaling
        self.s.set_iparm(13, 1)   # weighted matching (robust for indefinite / coupled systems)
        with _threads(A.shape[0]):
            self.s.factorize(self.A)
        self.ia = (self.A.indptr.astype(np.int32) + 1)
        self.ja = (self.A.indices.astype(np.int32) + 1)

    def solve(self, b):
        """Back-substitution only (PARDISO phase 33) with the stored factors. This skips pypardiso's
        per-call matrix hash and index copies, which cost more than the solve on small meshes."""
        import ctypes
        b = np.asarray(b, dtype=float)
        shape = b.shape
        bf = np.asfortranarray(b.reshape(shape[0], -1))
        x = np.zeros_like(bf)
        err = ctypes.c_int32(0)
        i32 = ctypes.POINTER(ctypes.c_int32)
        f64 = ctypes.POINTER(ctypes.c_double)
        s = self.s
        with _threads(self.A.shape[0]):
            s._mkl_pardiso(s.pt.ctypes.data_as(ctypes.POINTER(s._pt_type[0])), ctypes.byref(ctypes.c_int32(1)),
                           ctypes.byref(ctypes.c_int32(1)), ctypes.byref(ctypes.c_int32(s.mtype)),
                           ctypes.byref(ctypes.c_int32(33)), ctypes.byref(ctypes.c_int32(self.A.shape[0])),
                           self.A.data.ctypes.data_as(f64), self.ia.ctypes.data_as(i32), self.ja.ctypes.data_as(i32),
                           s.perm.ctypes.data_as(i32), ctypes.byref(ctypes.c_int32(bf.shape[1])),
                           s.iparm.ctypes.data_as(i32), ctypes.byref(ctypes.c_int32(0)),
                           bf.ctypes.data_as(f64), x.ctypes.data_as(f64), ctypes.byref(err))
        if err.value != 0:
            raise RuntimeError(f"PARDISO error {err.value}")
        return np.ascontiguousarray(x).reshape(shape)

    def __del__(self):
        try:
            self.s.free_memory(everything=True)
        except Exception:                          # noqa: BLE001
            pass


class _SuperLU:
    def __init__(self, A):
        self.lu = splu(A.tocsc() if issparse(A) else csr_matrix(A).tocsc())

    def solve(self, b):
        return self.lu.solve(np.asarray(b, dtype=float))


def factorize(A):
    """Factorise a square sparse matrix once; the result's .solve(b) can be called many times."""
    if A.shape[0] == 0:
        return _SuperLU(A)
    if A.shape[0] >= PARALLEL_FROM and _load() is not None:   # small systems: SuperLU is faster
        try:
            return _Pardiso(A)
        except Exception:                          # noqa: BLE001 - singular etc.: let SuperLU report it
            pass
    return _SuperLU(A)


def solve(A, b):
    """Solve A x = b once."""
    return factorize(A).solve(b)
