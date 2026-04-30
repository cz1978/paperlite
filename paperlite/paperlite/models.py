from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Paper(BaseModel):
    id: str
    source: str
    source_type: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    url: str
    pdf_url: Optional[str] = None
    doi: Optional[str] = None
    published_at: Optional[datetime] = None
    categories: list[str] = Field(default_factory=list)
    journal: Optional[str] = None
    venue: Optional[str] = None
    publisher: Optional[str] = None
    issn: list[str] = Field(default_factory=list)
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    openalex_id: Optional[str] = None
    citation_count: Optional[int] = None
    concepts: list[str] = Field(default_factory=list)
    source_records: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump(mode="json")
        return json.loads(self.json())
