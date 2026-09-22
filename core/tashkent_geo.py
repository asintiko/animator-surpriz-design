"""Зона обслуживания: город Ташкент (официальная граница OSM)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from .config import CONTENT_ROOT

_POLYGON_PATH = CONTENT_ROOT / "geo" / "tashkent-city-polygon.json"


class TashkentGeoError(ValueError):
    """Некорректные геоданные зоны обслуживания."""


def _load_geo_file() -> dict[str, Any]:
    if not _POLYGON_PATH.is_file():
        raise FileNotFoundError(f"Tashkent geo file not found: {_POLYGON_PATH}")
    payload = json.loads(_POLYGON_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TashkentGeoError("Tashkent geo file must be a JSON object")
    return payload


def _parse_ring(raw: Any, *, label: str) -> list[tuple[float, float]]:
    polygon: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        raise TashkentGeoError(f"{label}: expected array of coordinates")
    for index, point in enumerate(raw):
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise TashkentGeoError(f"{label}: invalid point at index {index}")
        lat = float(point[0])
        lng = float(point[1])
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            raise TashkentGeoError(f"{label}: coordinates out of range at index {index}")
        polygon.append((lat, lng))
    if len(polygon) < 3:
        raise TashkentGeoError(f"{label}: polygon must have at least 3 points")
    return polygon


def _validate_bbox(polygon: Sequence[tuple[float, float]]) -> None:
    lats = [point[0] for point in polygon]
    lngs = [point[1] for point in polygon]
    if min(lats) >= max(lats) or min(lngs) >= max(lngs):
        raise TashkentGeoError("Service area bbox is invalid")


@lru_cache(maxsize=1)
def get_service_area_polygon() -> tuple[tuple[float, float], ...]:
    payload = _load_geo_file()
    polygon = _parse_ring(payload.get("polygon"), label="polygon")
    _validate_bbox(polygon)
    return tuple(polygon)


@lru_cache(maxsize=1)
def get_mask_outer_ring() -> tuple[tuple[float, float], ...]:
    payload = _load_geo_file()
    outer = _parse_ring(payload.get("mask_outer"), label="mask_outer")
    _validate_bbox(outer)
    return tuple(outer)


TASHKENT_CITY_POLYGON: tuple[tuple[float, float], ...] = get_service_area_polygon()
TASHKENT_MASK_OUTER: tuple[tuple[float, float], ...] = get_mask_outer_ring()


def _polygon_centroid(polygon: Sequence[tuple[float, float]]) -> tuple[float, float]:
    lat_sum = sum(point[0] for point in polygon)
    lng_sum = sum(point[1] for point in polygon)
    count = len(polygon)
    return lat_sum / count, lng_sum / count


def _compute_bbox(polygon: Sequence[tuple[float, float]]) -> list[list[float]]:
    lats = [point[0] for point in polygon]
    lngs = [point[1] for point in polygon]
    return [[min(lats), min(lngs)], [max(lats), max(lngs)]]


TASHKENT_BBOX: list[list[float]] = _compute_bbox(TASHKENT_CITY_POLYGON)
TASHKENT_CENTROID: tuple[float, float] = _polygon_centroid(TASHKENT_CITY_POLYGON)


def is_inside_tashkent(lat: float | None, lng: float | None) -> bool:
    """Точка в зоне: город Ташкент (OSM)."""
    if lat is None or lng is None:
        return False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return False
    return _point_in_polygon(lat_f, lng_f, TASHKENT_CITY_POLYGON)


def clamp_to_tashkent(lat: float, lng: float) -> tuple[float, float]:
    if is_inside_tashkent(lat, lng):
        return lat, lng

    centroid_lat, centroid_lng = TASHKENT_CENTROID
    for step in range(1, 51):
        ratio = step / 50.0
        candidate_lat = lat + (centroid_lat - lat) * ratio
        candidate_lng = lng + (centroid_lng - lng) * ratio
        if is_inside_tashkent(candidate_lat, candidate_lng):
            return candidate_lat, candidate_lng

    return centroid_lat, centroid_lng


def polygon_for_template() -> list[list[float]]:
    return [[point[0], point[1]] for point in TASHKENT_CITY_POLYGON]


def mask_outer_for_template() -> list[list[float]]:
    return [[point[0], point[1]] for point in TASHKENT_MASK_OUTER]


def bbox_for_template() -> list[list[float]]:
    return [[TASHKENT_BBOX[0][0], TASHKENT_BBOX[0][1]], [TASHKENT_BBOX[1][0], TASHKENT_BBOX[1][1]]]


def _point_in_polygon(
    lat: float,
    lng: float,
    polygon: Sequence[tuple[float, float]],
) -> bool:
    epsilon = 1e-5

    def on_segment(
        py: float,
        px: float,
        ay: float,
        ax: float,
        by: float,
        bx: float,
    ) -> bool:
        cross = abs((px - ax) * (by - ay) - (py - ay) * (bx - ax))
        if cross > epsilon:
            return False
        min_x = min(ax, bx) - epsilon
        max_x = max(ax, bx) + epsilon
        min_y = min(ay, by) - epsilon
        max_y = max(ay, by) + epsilon
        return min_x <= px <= max_x and min_y <= py <= max_y

    inside = False
    count = len(polygon)
    j = count - 1
    for i in range(count):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        if on_segment(lat, lng, yi, xi, yj, xj):
            return True
        intersects = ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside
