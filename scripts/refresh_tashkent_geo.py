#!/usr/bin/env python3
"""Обновить content/geo/tashkent-city-polygon.json из OSM (relation 2216724)."""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = PROJECT_ROOT / "content/geo/tashkent-city-polygon.json"
GEOJSON_OUT_PATH = PROJECT_ROOT / "static/geo/tashkent.geojson"
OSM_RELATION_ID = 2216724
USER_AGENT = "EventSurpriz-Animator/1.0 (refresh_tashkent_geo)"


def fetch_relation_geojson(osm_id: int) -> dict:
    url = f"https://nominatim.openstreetmap.org/lookup?osm_ids=R{osm_id}&format=json&polygon_geojson=1"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    if not data:
        raise RuntimeError(f"No Nominatim data for relation {osm_id}")
    return data[0]["geojson"]


def rings_from_geojson(geojson: dict) -> list[list[list[float]]]:
    geom_type = geojson.get("type")
    coords = geojson.get("coordinates", [])
    rings: list[list[list[float]]] = []
    if geom_type == "Polygon" and coords:
        rings.append(coords[0])
    elif geom_type == "MultiPolygon":
        for poly in coords:
            if poly:
                rings.append(poly[0])
    return rings


def ring_area(ring: list[list[float]]) -> float:
    area = 0.0
    for i, point in enumerate(ring):
        x1, y1 = point
        x2, y2 = ring[(i + 1) % len(ring)]
        area += x1 * y2 - x2 * y1
    return abs(area)


def to_latlng(ring: list[list[float]]) -> list[list[float]]:
    return [[point[1], point[0]] for point in ring]


def simplify_ring(ring_latlng: list[list[float]], max_points: int = 100) -> list[list[float]]:
    def perp_dist(point, start, end):
        ax, ay = start
        bx, by = end
        px, py = point
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        projx, projy = ax + t * dx, ay + t * dy
        return math.hypot(px - projx, py - projy)

    def rdp(points: list[list[float]], eps: float) -> list[list[float]]:
        if len(points) < 3:
            return points
        start, end = points[0], points[-1]
        idx, dist_max = 0, 0.0
        for i in range(1, len(points) - 1):
            dist = perp_dist(points[i], start, end)
            if dist > dist_max:
                idx, dist_max = i, dist
        if dist_max > eps:
            left = rdp(points[: idx + 1], eps)
            right = rdp(points[idx:], eps)
            return left[:-1] + right
        return [start, end]

    simplified = ring_latlng
    for tolerance in (0.003, 0.006, 0.01, 0.015, 0.02, 0.03, 0.05):
        simplified = rdp(ring_latlng, tolerance)
        if len(simplified) <= max_points:
            break
    if simplified and simplified[0] == simplified[-1]:
        simplified = simplified[:-1]
    return simplified


def main() -> None:
    geojson = fetch_relation_geojson(OSM_RELATION_ID)
    rings = rings_from_geojson(geojson)
    if not rings:
        raise RuntimeError("No polygon rings in OSM geojson")
    outer = max(rings, key=ring_area)
    polygon = simplify_ring(to_latlng(outer))
    lats = [p[0] for p in polygon]
    lngs = [p[1] for p in polygon]
    pad_lat, pad_lng = 0.05, 0.08
    payload = {
        "name": "Tashkent City (OSM R2216724)",
        "source": "OpenStreetMap relation 2216724 Toshkent shahri, ODbL",
        "description": "Официальная административная граница города Ташкент. Упрощена для карты.",
        "mask_outer": [
            [min(lats) - pad_lat, min(lngs) - pad_lng],
            [min(lats) - pad_lat, max(lngs) + pad_lng],
            [max(lats) + pad_lat, max(lngs) + pad_lng],
            [max(lats) + pad_lat, min(lngs) - pad_lng],
        ],
        "polygon": polygon,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(polygon)} points to {OUT_PATH}")

    # Детальный (неупрощённый) GeoJSON для точной отрисовки границы на карте.
    geojson_feature = {
        "type": "Feature",
        "properties": {
            "name": "Tashkent City (OSM R2216724)",
            "source": "OpenStreetMap relation 2216724 Toshkent shahri, ODbL",
        },
        "geometry": geojson,
    }
    GEOJSON_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_OUT_PATH.write_text(
        json.dumps(geojson_feature, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    total_points = sum(len(r) for r in rings)
    print(f"Wrote detailed GeoJSON ({total_points} points) to {GEOJSON_OUT_PATH}")


if __name__ == "__main__":
    main()
