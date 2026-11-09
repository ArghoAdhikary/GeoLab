"""Interface elements for stress-deformation: a thin layer of elements (for example between a
wall or pile and the soil) that slips along its own direction.

The layer is drawn as a thin region with the interface material. Its direction and thickness t
come from the shape of the region (its longest principal axis; t = area / length). In the local
axes (t along the layer, n across it) the layer has

    normal stiffness  E_n = k_n t      shear stiffness  G_s = k_s t

with k_n and k_s per unit length of closure / slip, as for a zero-thickness interface. It slips
when the shear stress on the layer reaches the Mohr-Coulomb limit

    |tau_tn| = c_a + sigma_n' tan(delta)       (sigma_n' compression +)

with no dilation, so the normal stress does not change during slip. Inside GeoLab stresses are
tension positive: f = |tau_tn| + sigma_n tan(delta) - c_a.
"""
from __future__ import annotations

import math

import numpy as np

from .geometry import point_in_polygon


def region_axis(points):
    """Angle of the long axis (radians), thickness (area / length) and length of a thin region."""
    P = np.asarray(points, float)
    c = P.mean(axis=0)
    w, v = np.linalg.eigh(np.cov((P - c).T))
    d = v[:, int(np.argmax(w))]
    theta = math.atan2(d[1], d[0])
    proj = (P - c) @ d
    length = float(proj.max() - proj.min())
    x, y = P[:, 0], P[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    return theta, area / max(length, 1e-12), length


def strain_rotation(theta):
    """Strain transformation [ex, ey, gxy, ez] -> [et, en, gtn, ez] for local axes at angle theta."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c * c, s * s, s * c, 0], [s * s, c * c, -s * c, 0],
                     [-2 * s * c, 2 * s * c, c * c - s * s, 0], [0, 0, 0, 1.0]])


def local_D(En, Gs, nu):
    nu = min(max(nu, 0.0), 0.45)
    f = En / ((1 + nu) * (1 - 2 * nu))
    D = f * np.array([[1 - nu, nu, 0, nu], [nu, 1 - nu, 0, nu], [0, 0, 0, 0], [nu, nu, 0, 1 - nu]])
    D[2, 2] = Gs
    return D


def global_D(theta, En, Gs, nu):
    T = strain_rotation(theta)
    return T.T @ local_D(En, Gs, nu) @ T


def shear_normal(sig, cs, sn):
    """Shear stress tau_tn and normal stress sigma_n (tension +) on the layer, from global stresses
    [sx, sy, txy, sz] (any leading shape) and cos / sin of the layer angle."""
    sx, sy, txy = sig[..., 0], sig[..., 1], sig[..., 2]
    tau = (sy - sx) * sn * cs + txy * (cs * cs - sn * sn)
    sig_n = sx * sn * sn + sy * cs * cs - 2 * txy * sn * cs
    return tau, sig_n


def yield_value(sig, cs, sn, c, tand):
    tau, sig_n = shear_normal(sig, cs, sn)
    return np.abs(tau) + sig_n * tand - c, tau


def flow_vector(tau, cs, sn):
    """Gradient of |tau_tn| with respect to the global stresses (plastic strain direction)."""
    g = np.zeros(np.shape(tau) + (4,))
    sgn = np.sign(tau)
    g[..., 0] = -sgn * sn * cs
    g[..., 1] = sgn * sn * cs
    g[..., 2] = sgn * (cs * cs - sn * sn)
    return g


def return_map(sig, cs, sn, c, tand):
    """Stresses brought back to the slip limit (non-dilatant: only tau_tn changes)."""
    tau, sig_n = shear_normal(sig, cs, sn)
    lim = np.maximum(c - sig_n * tand, 0.0)
    over = np.abs(tau) > lim
    if not np.any(over):
        return sig
    d = np.where(over, np.sign(tau) * lim - tau, 0.0)
    out = np.array(sig, float, copy=True)
    # a change d of tau_tn alone: dsx = -2 s c d, dsy = 2 s c d, dtxy = (c^2 - s^2) d
    out[..., 0] += -2 * sn * cs * d
    out[..., 1] += 2 * sn * cs * d
    out[..., 2] += (cs * cs - sn * sn) * d
    return out


class InterfaceSet:
    """Orientation and properties of the interface elements of a mesh."""

    def __init__(self, project, mesh, srf=1.0):
        mats = {m.id: m for m in project.materials}
        ml = [mats[i] for i in mesh.mats]
        self.mask = np.array([m.stress_model == "interface" for m in ml], bool)
        ne = mesh.ne
        self.theta = np.zeros(ne)
        self.thick = np.ones(ne)
        self.c = np.zeros(ne)
        self.tand = np.zeros(ne)
        self.Gs = np.ones(ne)
        self.En = np.ones(ne)
        self.cs, self.sn = np.ones(ne), np.zeros(ne)
        if not self.mask.any():
            return
        regions = [r for r in project.regions if mats.get(r.material_id) is not None
                   and mats[r.material_id].stress_model == "interface"]
        info = {r.id: region_axis(r.points) for r in regions}
        xc, yc = mesh.gx.mean(axis=1), mesh.gy.mean(axis=1)
        for e in np.nonzero(self.mask)[0]:
            for r in regions:
                if r.material_id == mesh.mats[e] and point_in_polygon(xc[e], yc[e], r.points):
                    self.theta[e], self.thick[e], _ = info[r.id]
                    break
            m = ml[e]
            self.c[e] = m.iface_c / srf
            self.tand[e] = math.tan(math.radians(m.iface_delta)) / srf
            self.Gs[e] = max(m.iface_ks, 1e-9) * self.thick[e]
            self.En[e] = max(m.iface_kn, 1e-9) * self.thick[e]
        self.cs, self.sn = np.cos(self.theta), np.sin(self.theta)

    def D(self, nu):
        return {int(e): global_D(self.theta[e], self.En[e], self.Gs[e], nu[e]) for e in np.nonzero(self.mask)[0]}
