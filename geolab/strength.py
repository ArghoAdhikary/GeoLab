"""Shear strength models shared by the limit-equilibrium and finite element solvers.

Every model is reduced, at a given effective normal stress, to an equivalent
(instantaneous) cohesion and friction angle, so the slice equations can treat all
models the same way. Stresses are in the project's pressure unit.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

STRENGTH_MODELS = {
    "mohr_coulomb": "Mohr-Coulomb",
    "undrained": "Undrained (phi = 0)",
    "undrained_depth": "Undrained, strength increasing with depth",
    "shansep": "SHANSEP (S x OCR^m x vertical effective stress)",
    "bilinear": "Bilinear Mohr-Coulomb",
    "shear_normal": "Shear / normal function",
    "hoek_brown": "Generalized Hoek-Brown",
    "anisotropic": "Anisotropic (c, phi vary with base angle)",
    "high_strength": "High strength (slip surface may pass, never fails)",
    "bedrock": "Bedrock (impenetrable)",
}

HIGH_STRENGTH_C = 1e9


def is_nonlinear(mat) -> bool:
    """True when c and phi depend on the stress state (needs iteration)."""
    return mat.model in ("bilinear", "shear_normal", "hoek_brown")


def _table_tangent(table, sn):
    """Instantaneous (c, tan phi) of a piecewise-linear shear-normal envelope at sn."""
    s = np.asarray([p[0] for p in table], dtype=float)
    t = np.asarray([p[1] for p in table], dtype=float)
    if len(s) == 1:
        return float(t[0]), 0.0
    k = int(np.clip(np.searchsorted(s, sn) - 1, 0, len(s) - 2))
    ds = s[k + 1] - s[k]
    tan = (t[k + 1] - t[k]) / ds if ds > 0 else 0.0
    tan = max(tan, 0.0)
    c = t[k] - tan * s[k]
    if c < 0.0:   # keep tau(sn) exact with a secant through the origin
        tau = max(t[k] + tan * (sn - s[k]), 0.0)
        return 0.0, tau / sn if sn > 0 else tan
    return c, tan


@lru_cache(maxsize=64)
def hoek_brown_table(sigci, gsi, mi, D, n=120):
    """Shear-normal envelope of the generalized Hoek-Brown criterion (Hoek et al. 2002, Balmer 1952)."""
    mb = mi * math.exp((gsi - 100.0) / (28.0 - 14.0 * D))
    s = math.exp((gsi - 100.0) / (9.0 - 3.0 * D))
    a = 0.5 + (math.exp(-gsi / 15.0) - math.exp(-20.0 / 3.0)) / 6.0
    s3_min = -s * sigci / mb * 0.999          # uniaxial tensile strength
    s3 = np.concatenate((np.linspace(s3_min, 0.0, 20)[:-1], np.geomspace(1e-4 * sigci, 2.0 * sigci, n)))
    base = np.maximum(mb * s3 / sigci + s, 1e-12)
    s1 = s3 + sigci * base ** a
    d = 1.0 + a * mb * base ** (a - 1.0)     # d sigma1 / d sigma3
    sn = 0.5 * (s1 + s3) - 0.5 * (s1 - s3) * (d - 1.0) / (d + 1.0)
    tau = (s1 - s3) * np.sqrt(d) / (d + 1.0)
    order = np.argsort(sn)
    return tuple((float(a_), float(b_)) for a_, b_ in zip(sn[order], tau[order]))


def strength_at(mat, sn_eff, sv_eff=0.0, y=0.0, alpha=0.0):
    """Equivalent (c, tan phi) for a material at an effective normal stress.

    sv_eff: vertical effective stress (SHANSEP); y: elevation (strength with depth);
    alpha: base / plane inclination in radians (anisotropic).
    """
    m = mat.model
    if m == "mohr_coulomb":
        return mat.cohesion, math.tan(math.radians(mat.phi))
    if m == "undrained":
        return mat.cohesion, 0.0
    if m == "undrained_depth":
        return mat.cohesion + mat.c_rate * max(0.0, mat.datum - y), 0.0
    if m == "shansep":
        su = mat.shansep_s * mat.ocr ** mat.shansep_m * max(sv_eff, 0.0)
        return max(su, mat.cohesion), 0.0
    if m == "bilinear":
        t1, t2 = math.tan(math.radians(mat.phi)), math.tan(math.radians(mat.phi2))
        if sn_eff <= mat.sigma_break:
            return mat.cohesion, t1
        return mat.cohesion + mat.sigma_break * (t1 - t2), t2
    if m == "shear_normal":
        if not mat.sn_table:
            return mat.cohesion, math.tan(math.radians(mat.phi))
        return _table_tangent(sorted(mat.sn_table), sn_eff)
    if m == "hoek_brown":
        return _table_tangent(hoek_brown_table(mat.sigci, mat.gsi, mat.mi, mat.hb_d), sn_eff)
    if m == "anisotropic":
        c2, s2 = math.cos(alpha) ** 2, math.sin(alpha) ** 2
        c = mat.cohesion * c2 + mat.cohesion_v * s2
        phi = mat.phi * c2 + mat.phi_v * s2
        return c, math.tan(math.radians(phi))
    if m == "high_strength":
        return HIGH_STRENGTH_C, 0.0
    return mat.cohesion, math.tan(math.radians(mat.phi))


def shear_strength(mat, sn_eff, **kw) -> float:
    c, t = strength_at(mat, sn_eff, **kw)
    return c + max(sn_eff, 0.0) * t
