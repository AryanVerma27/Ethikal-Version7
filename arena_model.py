"""Geometry queries for the official arena's terrain and building prisms."""

from array import array
from collections import defaultdict
from itertools import pairwise
from heapq import heappop, heappush
import json
import math
from pathlib import Path
import sys
from time import perf_counter


class Arena:
    def __init__(self, root):
        root = Path(root) / "v2"
        world = json.loads((root / "world.json").read_text(encoding="utf-8"))
        self.bounds = world["bounds"]
        self.grid = world["terrain"]
        self.height = array("h", (root / self.grid["file"]).read_bytes())
        if sys.byteorder != "little":
            self.height.byteswap()
        self.buckets = defaultdict(list)
        for prism in world["prisms"]:
            rings = [list(zip(ring[::2], ring[1::2])) for ring in
                     [prism["ring"], *prism["holes"]]]
            ring = rings[0]
            if len(ring) < 3:
                continue
            xs, ys = zip(*ring)
            box = min(xs), min(ys), max(xs), max(ys)
            edges = [list(pairwise(points + points[:1])) for points in rings]
            item = (box, prism["base"], prism["top"], edges)
            for i in range(math.floor((box[0] - 12) / 24), math.floor((box[2] + 12) / 24) + 1):
                for j in range(math.floor((box[1] - 12) / 24), math.floor((box[3] + 12) / 24) + 1):
                    self.buckets[i, j].append(item)

    def ground(self, x, y):
        g = self.grid
        u = max(0, min(g["nx"] - 1.00001, (x - g["minX"]) / g["step"]))
        v = max(0, min(g["ny"] - 1.00001, (y - g["minY"]) / g["step"]))
        i, j = int(u), int(v)
        n = g["nx"]
        k = j * n + i
        a, b = u - i, v - j
        return g["scale"] * (
            (1 - b) * ((1 - a) * self.height[k] + a * self.height[k + 1])
            + b * ((1 - a) * self.height[k + n] + a * self.height[k + n + 1])
        )

    def blocked(self, x, y, low, high, radius=0):
        for (xmin, ymin, xmax, ymax), base, top, rings in self.buckets.get(
            (math.floor(x / 24), math.floor(y / 24)), ()
        ):
            if low >= top or high <= base:
                continue
            if not (xmin - radius <= x <= xmax + radius and ymin - radius <= y <= ymax + radius):
                continue
            contained = False
            for edges in rings:
                inside = False
                for (ax, ay), (bx, by) in edges:
                    dx, dy = bx - ax, by - ay
                    if (ay > y) != (by > y) and x < ax + dx * (y - ay) / dy:
                        inside = not inside
                    length = dx * dx + dy * dy
                    if radius and length:
                        t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / length))
                        if (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2 < radius ** 2:
                            return True
                contained ^= inside
            if contained:
                return True
        return False

    def clear(self, start, end, sag=0):
        x, y, z = start
        dx, dy, dz = (b - a for a, b in zip(start, end))
        count = max(1, math.ceil(math.hypot(dx, dy, dz) / 2.4))
        for i in range(1, count + 1):
            f = i / count
            px, py = x + dx * f, y + dy * f
            pz = z + dz * f + sag * f * (1 - f)
            if pz < self.ground(px, py) or self.blocked(px, py, pz, pz):
                return False
        return True

    def walkable(self, x, y, z, stats):
        r = min(stats["radius"] + 0.15, 10)
        b = self.bounds
        return (b["minX"] + r < x < b["maxX"] - r
                and b["minY"] + r < y < b["maxY"] - r
                and self.ground(x, y) <= z + stats["step_up"]
                and not self.blocked(x, y, z + 0.55, z + stats["height"], r))

    def detour(self, start, goal, stats, turn):
        """Find a short walkable path around the next obstacle."""
        x, y, z = start
        if abs(z - self.ground(x, y)) > 2:
            return None
        spacing = 6
        deadline = perf_counter() + .004
        opened = [(0, 0, 0, 0)]
        costs = {(0, 0): 0}
        parents = {}
        best = (0, 0)
        initial_gap = math.hypot(goal[0] - x, goal[1] - y)
        best_gap = initial_gap
        while opened and perf_counter() < deadline:
            _, cost, i, j = heappop(opened)
            if cost != costs[i, j]:
                continue
            px, py = x + i * spacing, y + j * spacing
            gap = math.hypot(goal[0] - px, goal[1] - py)
            if gap < best_gap:
                best, best_gap = (i, j), gap
            if gap <= 7 or initial_gap - gap >= 20:
                break
            for di, dj in ((1, 0), (0, turn), (-1, 0), (0, -turn),
                           (1, turn), (1, -turn), (-1, turn), (-1, -turn)):
                nxt = i + di, j + dj
                if max(abs(nxt[0]), abs(nxt[1])) > 9:
                    continue
                step = math.hypot(di, dj) * spacing
                next_cost = cost + step
                if next_cost >= costs.get(nxt, math.inf):
                    continue
                nx, ny = px + di * spacing, py + dj * spacing
                feet = z if not (i or j) else self.ground(px, py)
                for fraction in (1 / 3, 2 / 3, 1):
                    sx, sy = px + fraction * (nx - px), py + fraction * (ny - py)
                    if not self.walkable(sx, sy, feet, stats):
                        break
                    feet = self.ground(sx, sy)
                else:
                    costs[nxt] = next_cost
                    parents[nxt] = (i, j)
                    h = math.hypot(goal[0] - nx, goal[1] - ny)
                    heappush(opened, (next_cost + 1.25 * h, next_cost, *nxt))
        if best_gap > initial_gap - 5:
            return None
        path = []
        while best != (0, 0):
            path.append((x + best[0] * spacing, y + best[1] * spacing))
            best = parents[best]
        return path
