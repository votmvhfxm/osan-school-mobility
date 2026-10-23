"""Match ordered route stops to official GBIS route geometry, including return legs."""
import numpy as np

def distances(point, points):
    points = np.radians(np.asarray(points, dtype=float))
    lat, lon = np.radians(point)
    a = np.sin((points[:, 0] - lat) / 2) ** 2 + np.cos(lat) * np.cos(points[:, 0]) * np.sin((points[:, 1] - lon) / 2) ** 2
    return 12742000 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

def align_stations(stations, shape, max_distance=150):
    if len(shape) < 2 or not stations:
        return {}
    candidates, costs, parents = [], [], []
    for station in stations:
        try:
            distance = distances((float(station["y"]), float(station["x"])), shape)
        except (ValueError, TypeError, KeyError):
            return {}
        valid = np.flatnonzero(distance <= max_distance)
        if not len(valid):
            return {}
        # Retain candidates across both directions of overlapping route sections.
        if len(valid) > 64:
            valid = valid[np.argpartition(distance[valid], 63)[:64]]
        valid = np.sort(valid)
        score = distance[valid] ** 2
        if not candidates:
            current = score + valid * 1e-8
            parent = np.full(len(valid), -1, dtype=int)
        else:
            transition = costs[-1][:, None] + np.zeros((len(candidates[-1]), len(valid)))
            transition[candidates[-1][:, None] > valid[None, :]] = np.inf
            parent = np.argmin(transition, axis=0)
            current = score + transition[parent, np.arange(len(valid))]
        if not np.isfinite(current).any():
            return {}
        candidates.append(valid)
        costs.append(current)
        parents.append(parent)
    choice = int(np.argmin(costs[-1]))
    indices = []
    for n in range(len(stations) - 1, -1, -1):
        indices.append(int(candidates[n][choice]))
        choice = int(parents[n][choice])
    return {int(station["seq"]): index for station, index in zip(stations, reversed(indices))}

def cumulative_lengths(shape):
    points = np.radians(np.asarray(shape, dtype=float))
    delta = np.diff(points, axis=0)
    a = np.sin(delta[:, 0] / 2) ** 2 + np.cos(points[:-1, 0]) * np.cos(points[1:, 0]) * np.sin(delta[:, 1] / 2) ** 2
    lengths = 12742000 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return np.concatenate(([0.0], np.cumsum(lengths)))

