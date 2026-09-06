"""GeoJSON response shapes (RFC 7946), SRID 4326 (WGS84) throughout - see
docs/architecture/PHASE2_DESIGN.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GeoJSONPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # (lon, lat)


class GeoJSONLineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]]  # [(lon, lat), ...]
