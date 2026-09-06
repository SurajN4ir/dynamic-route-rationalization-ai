from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_code: str
    capacity: int | None
    source: str
    status: str
    created_at: datetime
    updated_at: datetime
