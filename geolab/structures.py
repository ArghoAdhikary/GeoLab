"""Staged construction and structural elements for stress-deformation analyses.

Staged construction
    Each stress analysis lists the regions that are *not* present in it (``inactive_regions``): regions
    not built yet, or already dug out. All stages share one mesh of every region; inactive elements are
    given a nearly zero stiffness and no weight. When a child stage removes elements (excavation), the
    forces they carried are released onto the remaining soil; when it adds elements (fill), their weight
    is applied. With R the removed and A the added elements, the load for the stage is

        dF = F_weight(A) - F_weight(R) + integral_R B^T sigma0 dV + F_boundary

    which keeps the parent stage in equilibrium and gives zero movement when nothing changes.

Structural elements
    Beams / walls are 2-node Euler-Bernoulli frame elements (axial EA, bending EI, one rotation per node);
    anchors / struts are 2-node bars (EA / spacing, optional prestress when installed); geogrids are bars
    that carry tension only. They connect the mesh nodes lying along the structure line (the mesher puts
    nodes on it). Forces carry over from stage to stage.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix

from .geometry import dist_point_polyline, point_in_polygon


def element_regions(project, mesh) -> np.ndarray:
    """Region id of every element (by its centroid); -1 when outside all regions."""
    cen = mesh.nodes3[mesh.tris3].mean(axis=1)
    out = np.full(len(cen), -1, int)
    for r in project.regions:
        if len(r.points) < 3:
            continue
        pts = r.points
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        box = (cen[:, 0] >= min(xs)) & (cen[:, 0] <= max(xs)) & (cen[:, 1] >= min(ys)) & (cen[:, 1] <= max(ys))
        for e in np.nonzero(box & (out < 0))[0]:
            if point_in_polygon(cen[e, 0], cen[e, 1], pts):
                out[e] = r.id
    return out


def inactive_elements(project, mesh, analysis) -> np.ndarray:
    """Boolean mask of the elements that are not present in an analysis stage."""
    ids = set(getattr(analysis, "inactive_regions", None) or []) if analysis is not None else set()
    if not ids:
        return np.zeros(mesh.ne, bool)
    return np.isin(element_regions(project, mesh), list(ids))


def stress_parent(project, analysis):
    """The parent stress stage of an analysis, or None."""
    p = project.analysis(analysis.parent_id) if analysis is not None else None
    return p if p is not None and p.kind == "stress" else None


# ---------------------------------------------------------------------------
# structural elements
# ---------------------------------------------------------------------------
def active_structures(project, analysis):
    aid = getattr(analysis, "id", None)
    return [s for s in getattr(project, "structures", []) or []
            if len(s.points) >= 2 and (not s.analyses or aid in s.analyses)]


def _line_nodes(mesh, pts, tol):
    """Mesh nodes on a polyline, ordered along it."""
    pts = [tuple(p) for p in pts]
    seg_len = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    out = []
    for i, (x, y) in enumerate(mesh.nodes):
        if dist_point_polyline(x, y, pts) > tol:
            continue
        # distance along the polyline of the nearest point
        best, along, s0 = 1e30, 0.0, 0.0
        for (a, b), L in zip(zip(pts, pts[1:]), seg_len):
            if L <= 0:
                continue
            t = ((x - a[0]) * (b[0] - a[0]) + (y - a[1]) * (b[1] - a[1])) / (L * L)
            t = min(max(t, 0.0), 1.0)
            d = math.hypot(a[0] + t * (b[0] - a[0]) - x, a[1] + t * (b[1] - a[1]) - y)
            if d < best:
                best, along = d, s0 + t * L
            s0 += L
        out.append((along, i))
    out.sort()
    nodes = []
    for along, i in out:
        if not nodes or along - nodes[-1][0] > 1e-6 * max(1.0, along):
            nodes.append((along, i))
    return [i for _, i in nodes]


class StructureSet:
    """Stiffness and forces of the structural elements active in one stage."""

    def __init__(self, project, mesh, analysis, tol, parent_results=None):
        self.nd = 2 * mesh.nn
        self.items = []          # (structure, list of element dicts)
        rot = {}                 # beam node -> rotation dof
        prev = {}
        for s in (parent_results or {}).get("structures", []) or []:
            for el in s.get("elements", []):
                prev[(s["id"], el["n1"], el["n2"])] = el
        self.released = np.zeros(self.nd)    # forces of parent elements no longer present (excavated / removed)
        self.prestress = np.zeros(self.nd)
        active_ids = set()
        for st in active_structures(project, analysis):
            nodes = _line_nodes(mesh, st.points, tol)
            if len(nodes) < 2:
                raise ValueError(f"Structure '{st.name}' does not lie on the mesh: draw it inside the regions.")
            els = []
            for n1, n2 in zip(nodes, nodes[1:]):
                if st.type == "beam":
                    for n in (n1, n2):
                        rot.setdefault(n, None)
                key = (st.id, int(n1), int(n2))
                active_ids.add(key)
                old = prev.get(key)
                els.append({"n1": int(n1), "n2": int(n2), "f0": np.array(old["f"]) if old else np.zeros(6),
                            "new": old is None})
            self.items.append((st, els))
        for k, n in enumerate(sorted(rot)):
            rot[n] = self.nd + k
        self.rot = rot
        self.ndof = self.nd + len(rot)
        # parent elements that are gone: release their end forces onto the soil
        for (sid, n1, n2), el in prev.items():
            if (sid, n1, n2) not in active_ids:
                f = el["f"]
                for j, n in enumerate((n1, n2)):
                    self.released[2 * n] += f[3 * j]
                    self.released[2 * n + 1] += f[3 * j + 1]
        self.mesh = mesh
        self.off = set()         # geogrid elements switched off (in compression)
        for st, els in self.items:
            if st.type == "anchor" and st.prestress:
                for el in els:
                    if el["new"]:
                        c, s_, L = self._geom(el)
                        P = st.prestress / max(st.spacing, 1e-9)
                        # pull the two ends together; the bar starts with tension P
                        self.prestress[2 * el["n1"]] += P * c
                        self.prestress[2 * el["n1"] + 1] += P * s_
                        self.prestress[2 * el["n2"]] -= P * c
                        self.prestress[2 * el["n2"] + 1] -= P * s_
                        el["f0"] = el["f0"] + np.array([-P * c, -P * s_, 0.0, P * c, P * s_, 0.0])

    def _geom(self, el):
        a, b = self.mesh.nodes[el["n1"]], self.mesh.nodes[el["n2"]]
        d = b - a
        L = float(math.hypot(*d))
        return d[0] / L, d[1] / L, L

    def _dofs(self, st, el):
        n1, n2 = el["n1"], el["n2"]
        if st.type == "beam":
            return [2 * n1, 2 * n1 + 1, self.rot[n1], 2 * n2, 2 * n2 + 1, self.rot[n2]]
        return [2 * n1, 2 * n1 + 1, 2 * n2, 2 * n2 + 1]

    def _k_global(self, st, el):
        c, s, L = self._geom(el)
        if st.type == "beam":
            EA, EI = st.EA, st.EI
            k = np.array([
                [EA / L, 0, 0, -EA / L, 0, 0],
                [0, 12 * EI / L ** 3, 6 * EI / L ** 2, 0, -12 * EI / L ** 3, 6 * EI / L ** 2],
                [0, 6 * EI / L ** 2, 4 * EI / L, 0, -6 * EI / L ** 2, 2 * EI / L],
                [-EA / L, 0, 0, EA / L, 0, 0],
                [0, -12 * EI / L ** 3, -6 * EI / L ** 2, 0, 12 * EI / L ** 3, -6 * EI / L ** 2],
                [0, 6 * EI / L ** 2, 2 * EI / L, 0, -6 * EI / L ** 2, 4 * EI / L]])
            T = np.zeros((6, 6))
            for j in (0, 3):
                T[j:j + 2, j:j + 2] = [[c, s], [-s, c]]
                T[j + 2, j + 2] = 1.0
            return T.T @ k @ T, T, k
        ea = st.EA / max(st.spacing, 1e-9) if st.type == "anchor" else st.EA
        kk = ea / L
        v = np.array([-c, -s, c, s])
        return kk * np.outer(v, v), None, None

    def stiffness(self):
        rows, cols, vals = [], [], []
        for st, els in self.items:
            for i, el in enumerate(els):
                if (st.id, i) in self.off:
                    continue
                K, _, _ = self._k_global(st, el)
                d = self._dofs(st, el)
                for a in range(len(d)):
                    for b in range(len(d)):
                        rows.append(d[a]); cols.append(d[b]); vals.append(K[a, b])
        return coo_matrix((vals, (rows, cols)), shape=(self.ndof, self.ndof)).tocsr()

    def _end_forces(self, st, el, u):
        """Global end forces [fx1, fy1, m1, fx2, fy2, m2] of an element after displacement increment u."""
        K, _, _ = self._k_global(st, el)
        d = self._dofs(st, el)
        f = K @ u[d]
        if st.type != "beam":
            f = np.array([f[0], f[1], 0.0, f[2], f[3], 0.0])
        return el["f0"] + f

    def compressed_geogrids(self, u):
        """Geogrid elements in compression (to be switched off). Returns True when the set changed."""
        changed = False
        for st, els in self.items:
            if st.type != "geogrid":
                continue
            for i, el in enumerate(els):
                if (st.id, i) in self.off:
                    continue
                f = self._end_forces(st, el, u)
                c, s, _ = self._geom(el)
                if f[3] * c + f[4] * s < -1e-9:
                    self.off.add((st.id, i))
                    changed = True
        return changed

    def results(self, u):
        out = []
        for st, els in self.items:
            rows = []
            for i, el in enumerate(els):
                f = np.zeros(6) if (st.id, i) in self.off else self._end_forces(st, el, u)
                c, s, L = self._geom(el)
                a, b = self.mesh.nodes[el["n1"]], self.mesh.nodes[el["n2"]]
                N = f[3] * c + f[4] * s                     # tension positive
                V = -f[3] * s + f[4] * c
                rows.append({"n1": el["n1"], "n2": el["n2"], "x1": float(a[0]), "y1": float(a[1]),
                             "x2": float(b[0]), "y2": float(b[1]), "N": float(N), "V": float(V),
                             "M1": float(-f[2]), "M2": float(f[5]), "f": [float(v) for v in f]})
            Ns = [r["N"] for r in rows]
            Ms = [abs(m) for r in rows for m in (r["M1"], r["M2"])]
            out.append({"id": st.id, "name": st.name, "type": st.type, "elements": rows,
                        "max_N": float(max(Ns, key=abs)) if Ns else 0.0,
                        "max_M": float(max(Ms)) if Ms and st.type == "beam" else 0.0})
        return out


def stage_load(project, mesh, model, analysis, parent, sig0, u_gp, gravity_load):
    """Extra load of a stage from regions added (fill weight) or removed (excavation release)."""
    if parent is None or parent.kind != "stress":
        return np.zeros(2 * mesh.nn), np.zeros(mesh.ne, bool)
    now = inactive_elements(project, mesh, analysis)
    before = inactive_elements(project, mesh, parent)
    removed = ~before & now
    added = before & ~now
    F = np.zeros(2 * mesh.nn)
    if not (removed.any() or added.any()):
        return F, added
    mats = {m.id: m for m in project.materials}
    gamma = np.array([mats[i].unit_weight if mats[i].stress_model != "none" else 0.0 for i in mesh.mats], float)
    fe = gravity_load(mesh, gamma, u_gp)
    if added.any():
        F += mesh.vector(np.where(added[:, None], fe, 0.0))
    if removed.any():
        F -= mesh.vector(np.where(removed[:, None], fe, 0.0))
        rel = np.einsum("egji,egj,eg->ei", mesh.B, sig0, mesh.dV)
        F += mesh.vector(np.where(removed[:, None], rel, 0.0))
    return F, added
