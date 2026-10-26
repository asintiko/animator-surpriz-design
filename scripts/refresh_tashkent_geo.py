#!/usr/bin/env python3
"""Обновить зону обслуживания: content/geo/tashkent-city-polygon.json и static/geo/tashkent.geojson.

Зона — городские районы Ташкента из OSM без земель, недавно переданных городу из
Ташкентской области (Янгиташкентский район), и без анклава у Улугбека: работаем
только по самому городу. Нужен пакет shapely (только для этого скрипта).
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = PROJECT_ROOT / "content/geo/tashkent-city-polygon.json"
GEOJSON_OUT_PATH = PROJECT_ROOT / "static/geo/tashkent.geojson"
USER_AGENT = "EventSurpriz-Animator/1.0 (refresh_tashkent_geo)"
# Районы города Ташкент (OSM, admin_level=6). Без Yangi Toshkent Tumani (R17389398).
CITY_DISTRICT_RELATIONS = {
    1751444: "Яшнабадский",
    2434059: "Учтепинский",
    2439529: "Шайхантахурский",
    2441651: "Алмазарский",
    2441810: "Чиланзарский",
    2443769: "Яккасарайский",
    2447546: "Сергелийский",
    2447560: "Бектемирский",
    2447634: "Мирабадский",
    2448072: "Юнусабадский",
    5620904: "Мирзо-Улугбекский",
    12030887: "Янгихаётский",
}
# Стыки районов в OSM не идеальны: склеиваем с небольшим запасом и убираем его обратно.
SEAM_BUFFER_DEG = 0.0005
POLYGON_TOLERANCE_DEG = 0.0003


def fetch_relation_geojson(osm_id: int) -> dict:
    url = f"https://nominatim.openstreetmap.org/lookup?osm_ids=R{osm_id}&format=json&polygon_geojson=1"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    if not data:
        raise RuntimeError(f"No Nominatim data for relation {osm_id}")
    return data[0]["geojson"]


def city_outline():
    from shapely.geometry import Polygon, shape
    from shapely.ops import unary_union

    parts = []
    for osm_id in CITY_DISTRICT_RELATIONS:
        parts.append(shape(fetch_relation_geojson(osm_id)).buffer(SEAM_BUFFER_DEG))
        time.sleep(1.1)  # Nominatim usage policy: не чаще раза в секунду.
    union = unary_union(parts).buffer(-SEAM_BUFFER_DEG)
    polygons = list(union.geoms) if union.geom_type == "MultiPolygon" else [union]
    # Только основной контур: мелкие анклавы (посёлок Улугбек) в зону не входят.
    main = max(polygons, key=lambda polygon: polygon.area)
    return Polygon(main.exterior)


def main() -> None:
    outline = city_outline()
    detailed = [[round(lng, 7), round(lat, 7)] for lng, lat in outline.exterior.coords]
    polygon = [[round(lat, 6), round(lng, 6)] for lng, lat in outline.simplify(POLYGON_TOLERANCE_DEG).exterior.coords][:-1]
    lats = [p[0] for p in polygon]
    lngs = [p[1] for p in polygon]
    pad_lat, pad_lng = 0.05, 0.08
    source = "OpenStreetMap, районы города Ташкент без Янгиташкентского района, ODbL"
    payload = {
        "name": "Tashkent City districts (OSM)",
        "source": source,
        "description": "Зона обслуживания: город Ташкент без земель Ташкентской области и анклавов.",
        "mask_outer": [
            [min(lats) - pad_lat, min(lngs) - pad_lng],
            [min(lats) - pad_lat, max(lngs) + pad_lng],
            [max(lats) + pad_lat, max(lngs) + pad_lng],
            [max(lats) + pad_lat, min(lngs) - pad_lng],
        ],
        "polygon": polygon,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(polygon)} points to {OUT_PATH}")

    geojson_feature = {
        "type": "Feature",
        "properties": {"name": "Tashkent City districts (OSM)", "source": source},
        "geometry": {"type": "Polygon", "coordinates": [detailed]},
    }
    GEOJSON_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_OUT_PATH.write_text(json.dumps(geojson_feature, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote detailed GeoJSON ({len(detailed)} points) to {GEOJSON_OUT_PATH}")


if __name__ == "__main__":
    main()
