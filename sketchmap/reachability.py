from collections import deque

import numpy as np


def find_unreachable_floors(grid, walkable_ids, spawn_rc):
    rows, cols = grid.shape
    sr, sc = spawn_rc
    if not (0 <= sr < rows and 0 <= sc < cols) or int(grid[sr, sc]) not in walkable_ids:
        return []
    walk = np.isin(grid, list(walkable_ids))
    visited = np.zeros((rows, cols), dtype=bool)
    visited[sr, sc] = True
    queue = deque([(sr, sc)])
    while queue:
        r, c = queue.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and walk[nr, nc] and not visited[nr, nc]:
                visited[nr, nc] = True
                queue.append((nr, nc))
    return [(int(r), int(c)) for r, c in np.argwhere(walk & ~visited)]


def model_unreachable(model):
    if not model.spawns:
        return None
    sx, sy = model.spawns[0]
    grid = model.tile_matrix()
    for (x, y), (k, _f) in model.terrain.items():
        if k in ("water", "lava"):
            grid[y, x] = 9
    return [(c, r) for r, c in find_unreachable_floors(grid, {0}, (sy, sx))]
