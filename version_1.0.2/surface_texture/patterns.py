# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

"""Patrones de relieve. Cada uno devuelve una altura entre 0 (fondo) y 1 (lo más alto) por vértice.

Los 2D (moleteado, hexágonos, carbono, ladrillo, estrías, imagen) se proyectan sobre la pieza
(caja triplanar o cilindro). Los 3D (piedra, martillado, cuero, madera) se calculan en el espacio,
así que no tienen costuras en ninguna forma.
Todo con numpy, sin Blender: se puede probar suelto.
"""
import math

import numpy as np

SQ3 = math.sqrt(3.0)


# --------------------------------------------------------------------------- utilidades
def _tri(x):
    """Onda triangular 0..1..0 de periodo 1."""
    f = x - np.floor(x)
    return 1.0 - 2.0 * np.abs(f - 0.5)


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / max(e1 - e0, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash(ix, iy, iz, seed=0):
    """Número pseudoaleatorio 0..1 por celda entera (rápido, reproducible)."""
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791)
    h = (h ^ (seed * 2654435761)) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


# --------------------------------------------------------------------------- 3D
def value_noise(P, seed=0):
    i = np.floor(P).astype(np.int64)
    f = P - i
    u = f * f * (3 - 2 * f)
    out = np.zeros(len(P))
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1 - u[:, 2]
                out += wx * wy * wz * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out


def fbm(P, octaves=4, seed=0):
    total, amp, norm = np.zeros(len(P)), 1.0, 0.0
    for o in range(octaves):
        total += amp * value_noise(P * (2.0 ** o), seed + o)
        norm += amp
        amp *= 0.5
    return total / norm


def voronoi(P, seed=0, chunk=150_000):
    """Distancias al punto más cercano (F1) y al segundo (F2), celdas de tamaño 1."""
    F1 = np.empty(len(P)); F2 = np.empty(len(P))
    offs = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)])
    for s in range(0, len(P), chunk):
        p = P[s:s + chunk]
        cell = np.floor(p).astype(np.int64)
        d = np.empty((len(p), 27))
        for k, o in enumerate(offs):
            c = cell + o
            fp = c + np.stack([_hash(c[:, 0], c[:, 1], c[:, 2], seed + j) for j in (11, 23, 37)], 1)
            d[:, k] = np.linalg.norm(p - fp, axis=1)
        d.sort(axis=1)
        F1[s:s + chunk] = d[:, 0]; F2[s:s + chunk] = d[:, 1]
    return F1, F2


def stone(P, s):
    return np.clip(fbm(P / s, 5) * 1.6 - 0.3, 0, 1)


def hammered(P, s):
    F1, _ = voronoi(P / s)
    return _smooth(0.0, 0.6, F1)                     # hoyuelos redondos


def leather(P, s):
    F1, F2 = voronoi(P / s, seed=5)
    cracks = _smooth(0.0, 0.18, F2 - F1)            # surcos entre celdas
    grain = fbm(P / (s * 0.25), 3, seed=9)
    return np.clip(cracks * (0.75 + 0.25 * grain), 0, 1)


def wood(P, s, center):
    q = P - center
    r = np.sqrt(q[:, 0] ** 2 + q[:, 1] ** 2) / s + 1.5 * fbm(q / (s * 4), 3, seed=3)
    rings = _tri(r) ** 2
    grain = fbm(q * np.array([1 / (s * 0.15), 1 / (s * 0.15), 1 / (s * 4)]), 2, seed=4)
    return np.clip(0.75 * rings + 0.25 * grain, 0, 1)


# --------------------------------------------------------------------------- 2D (u, v en tamaños de celda)
def knurl(u, v):
    return np.minimum(_tri(u + v), _tri(u - v))      # pirámides en rombo


def hexagons(u, v):
    """Panal: celdas planas con surco."""
    # dos rejillas rectangulares (1 × √3) desplazadas media celda: el centro más cercano
    # de las dos es el centro del hexágono
    rx, ry = 1.0, SQ3

    def wrap(t, r):
        return t - r * np.floor(t / r) - r / 2

    a = np.stack([wrap(u, rx), wrap(v, ry)], 1)
    b = np.stack([wrap(u - rx / 2, rx), wrap(v - ry / 2, ry)], 1)
    g = np.where((np.linalg.norm(a, axis=1) < np.linalg.norm(b, axis=1))[:, None], a, b)
    ax = np.abs(g[:, 0]); ay = np.abs(g[:, 1])
    dh = np.maximum(ax * 0.5 + ay * SQ3 / 2, ax)     # 0 en el centro, 0.5 en el borde
    return 1.0 - _smooth(0.36, 0.46, dh)


def carbon(u, v):
    """Fibra de carbono (sarga 2×2)."""
    i = np.floor(u); j = np.floor(v)
    fu = u - i; fv = v - j
    along_u = ((i + j) % 4) < 2
    across = np.where(along_u, fv, fu)
    length = np.where(along_u, fu, fv)
    h = np.sin(np.pi * across) * (0.7 + 0.3 * np.sin(np.pi * length))
    return np.clip(h, 0, 1)


def bricks(u, v):
    row = np.floor(v)
    uu = u / 2.0 + 0.5 * (row % 2)
    fu = uu - np.floor(uu); fv = v - row
    edge = np.minimum(np.minimum(fu, 1 - fu) * 2.0, np.minimum(fv, 1 - fv))
    return _smooth(0.05, 0.13, edge)


def ribs(u, v):
    return 0.5 + 0.5 * np.cos(2 * np.pi * u)


class ImagePattern:
    """Mapa de alturas desde una imagen (gris: blanco alto, negro bajo), repetida."""

    def __init__(self, pixels, width, height, repeat=True):
        self.img = pixels.reshape(height, width)
        self.w, self.h = width, height
        self.repeat = repeat

    def __call__(self, u, v):
        if not self.repeat:
            inside = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)
            out = np.zeros(len(u))
            if inside.any():
                out[inside] = self._sample(u[inside], v[inside])
            return out
        return self._sample(u, v)

    def _sample(self, u, v):
        x = (u - np.floor(u)) * (self.w - 1)
        y = (v - np.floor(v)) * (self.h - 1)
        x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
        x1 = np.minimum(x0 + 1, self.w - 1); y1 = np.minimum(y0 + 1, self.h - 1)
        fx = x - x0; fy = y - y0
        im = self.img
        top = im[y0, x0] * (1 - fx) + im[y0, x1] * fx
        bot = im[y1, x0] * (1 - fx) + im[y1, x1] * fx
        return top * (1 - fy) + bot * fy


PATTERNS_2D = {'KNURL': knurl, 'HEX': hexagons, 'CARBON': carbon, 'BRICK': bricks, 'RIBS': ribs}
PATTERNS_3D = {'STONE', 'HAMMER', 'LEATHER', 'WOOD'}


# --------------------------------------------------------------------------- proyección
def project_box(P, N, s, fn, sharp=4.0):
    """Triplanar: cada cara toma el dibujo del plano al que más mira, con mezcla suave."""
    w = np.abs(N) ** sharp
    w /= np.maximum(w.sum(1, keepdims=True), 1e-12)
    q = P / s
    return (w[:, 0] * fn(q[:, 1], q[:, 2]) + w[:, 1] * fn(q[:, 0], q[:, 2]) + w[:, 2] * fn(q[:, 0], q[:, 1]))


def project_cylinder(P, N, s, fn, center):
    """Alrededor del eje Z que pasa por el centro: ideal para pomos, mandos y piezas redondas.
    Las tapas (caras que miran arriba o abajo) usan el plano."""
    q = P - center
    r = np.sqrt(q[:, 0] ** 2 + q[:, 1] ** 2)
    R = float(np.median(r[np.abs(N[:, 2]) < 0.5])) if (np.abs(N[:, 2]) < 0.5).any() else float(r.mean() or 1.0)
    n_cells = max(1, round(2 * math.pi * R / s))       # número entero de celdas: sin costura
    ang = np.arctan2(q[:, 1], q[:, 0])
    u = ang / (2 * math.pi) * n_cells
    side = fn(u, q[:, 2] / s)
    cap = fn(q[:, 0] / s, q[:, 1] / s)
    w = _smooth(0.55, 0.85, np.abs(N[:, 2]))
    return side * (1 - w) + cap * w


def height(P, N, pattern, scale, projection='BOX', center=None, image=None):
    if center is None:
        center = (P.min(0) + P.max(0)) / 2
    if pattern == 'STONE':
        return stone(P, scale)
    if pattern == 'HAMMER':
        return hammered(P, scale)
    if pattern == 'LEATHER':
        return leather(P, scale)
    if pattern == 'WOOD':
        return wood(P, scale, center)
    fn = image if pattern == 'IMAGE' else PATTERNS_2D[pattern]
    if fn is None:
        raise ValueError('Falta la imagen para el relieve.')
    if pattern == 'IMAGE' and not getattr(fn, 'repeat', True):
        # una sola vez, centrada, vista desde arriba (logos en tapas y placas)
        q = (P - center) / scale + 0.5
        return fn(q[:, 0], q[:, 1]) * _smooth(0.3, 0.6, N[:, 2])
    if projection == 'CYLINDER':
        return project_cylinder(P, N, scale, fn, center)
    return project_box(P, N, scale, fn)
