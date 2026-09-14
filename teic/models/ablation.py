from __future__ import annotations

from pydantic import BaseModel


class AblationProfile(BaseModel):
    name: str
    description: str
    disable: list[str] = []
