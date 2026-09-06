"""Geometry (de)serialization helpers.

GeoAlchemy2 hands back a WKBElement for every geometry column read through
the ORM; API responses need plain GeoJSON. This is the one place that
conversion happens, so every endpoint/schema does it the same way.
"""

from __future__ import annotations

from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping


def geometry_to_geojson(value: Any) -> dict[str, Any] | None:
    """Convert a GeoAlchemy2 WKBElement (or None) to a plain GeoJSON dict."""
    if value is None:
        return None
    shape = to_shape(value)
    return mapping(shape)


def geometry_to_geojson_required(value: Any) -> dict[str, Any]:
    """Same as geometry_to_geojson, for columns that are NOT NULL in the
    schema - saves every caller from re-asserting non-None."""
    result = geometry_to_geojson(value)
    if result is None:
        raise ValueError("Expected a non-null geometry value.")
    return result
