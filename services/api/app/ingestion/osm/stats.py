"""Ingestion run statistics - the same object is populated identically in
dry-run and real-ingestion mode (doc TASK-202 §10/§17), so dry-run's
numbers are a genuine preview, not a separate/fake code path.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class IngestionStats:
    dry_run: bool
    source: str
    input_path: str

    source_features_read: int = 0
    eligible_road_features: int = 0
    rejected_features: int = 0
    rejections_by_reason: Counter[str] = field(default_factory=Counter)

    intersections_created: int = 0
    intersections_updated: int = 0
    roads_created: int = 0
    roads_updated: int = 0
    segments_created: int = 0
    segments_updated: int = 0
    skipped_duplicates: int = 0
    validation_failures: int = 0

    duration_s: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "source": self.source,
            "input_path": self.input_path,
            "source_features_read": self.source_features_read,
            "eligible_road_features": self.eligible_road_features,
            "rejected_features": self.rejected_features,
            "rejections_by_reason": dict(self.rejections_by_reason),
            "intersections_created": self.intersections_created,
            "intersections_updated": self.intersections_updated,
            "roads_created": self.roads_created,
            "roads_updated": self.roads_updated,
            "segments_created": self.segments_created,
            "segments_updated": self.segments_updated,
            "skipped_duplicates": self.skipped_duplicates,
            "validation_failures": self.validation_failures,
            "duration_s": round(self.duration_s, 3),
        }
