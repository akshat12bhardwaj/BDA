"""
Steps 11b/11c: shortest and fastest paths on a directed road graph (Dijkstra via scipy.sparse.csgraph).

Pure functions over arrays; no file or network access. Edge weights must be positive: distance in km, time in hours.
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

EARTH_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance; used only for edge lengths and sanity checks, never shown as road distance."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def build_csr(n: int, u: np.ndarray, v: np.ndarray, w: np.ndarray) -> csr_matrix:
    """Directed graph; parallel edges keep the minimum weight (csr_matrix would otherwise sum them)."""
    if len(w) and (w <= 0).any():
        raise ValueError("edge weights must be positive")
    order = np.lexsort((w, v, u))
    u, v, w = u[order], v[order], w[order]
    first = np.ones(len(u), bool)
    first[1:] = (u[1:] != u[:-1]) | (v[1:] != v[:-1])
    return csr_matrix((w[first], (u[first], v[first])), shape=(n, n))


def largest_strong_component(g: csr_matrix) -> np.ndarray:
    """Boolean mask of the largest strongly connected component (every node in it can reach every other)."""
    _, labels = connected_components(g, directed=True, connection="strong")
    return labels == np.bincount(labels).argmax()


def shortest_from(g: csr_matrix, source: int) -> tuple[np.ndarray, np.ndarray]:
    """Dijkstra from one source: (cost to every node, predecessor; -9999 = none). Unreachable cost = inf."""
    dist, pred = dijkstra(g, directed=True, indices=source, return_predecessors=True)
    return dist, pred


def path(pred: np.ndarray, source: int, target: int) -> list[int] | None:
    """Node sequence source -> target from a predecessor array, or None when target is unreachable."""
    if source == target:
        return [source]
    if pred[target] < 0:
        return None
    seq = [target]
    while seq[-1] != source:
        seq.append(int(pred[seq[-1]]))
        if len(seq) > len(pred):                       # defensive: a broken predecessor chain
            raise RuntimeError("predecessor cycle")
    return seq[::-1]


def edge_sum(g: csr_matrix, nodes: list[int]) -> float:
    """Sum of g's weights along a node path (e.g. the travel time of the shortest-distance path)."""
    if len(nodes) < 2:
        return 0.0
    a = np.asarray(nodes[:-1])
    return float(np.asarray(g[a, np.asarray(nodes[1:])]).sum())
