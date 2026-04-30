from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from paperlite.models import Paper


@dataclass(frozen=True)
class SourceRecord:
    key: str
    name: str
    source_kind: str
    publisher: str | None = None
    homepage: str | None = None
    issn: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    disciplines: list[str] = field(default_factory=list)
    tier: str | None = None
    status: str = "active"
    origin: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return self.source_kind

    @property
    def journal(self) -> str:
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "source_kind": self.source_kind,
            "publisher": self.publisher,
            "homepage": self.homepage,
            "issn": list(self.issn),
            "topics": list(self.topics),
            "disciplines": list(self.disciplines),
            "tier": self.tier,
            "status": self.status,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class EndpointConfig:
    key: str
    source_key: str
    mode: str
    url: str | None = None
    provider: str | None = None
    query: dict[str, Any] = field(default_factory=dict)
    format: str | None = None
    enabled: bool = True
    priority: int = 100
    status: str = "active"
    rate_limit_seconds: float | None = None
    timeout_seconds: float | None = None
    request_profile: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "source_key": self.source_key,
            "mode": self.mode,
            "url": self.url,
            "provider": self.provider,
            "query": dict(self.query),
            "format": self.format,
            "enabled": self.enabled,
            "priority": self.priority,
            "status": self.status,
            "rate_limit_seconds": self.rate_limit_seconds,
            "timeout_seconds": self.timeout_seconds,
            "request_profile": self.request_profile,
        }


@dataclass(frozen=True)
class SourceConfig:
    key: str
    type: str
    journal: str | None = None
    publisher: str | None = None
    url: str | None = None
    endpoint_key: str | None = None
    mode: str | None = None
    issn: list[str] = field(default_factory=list)
    tier: str | None = None
    topics: list[str] = field(default_factory=list)
    disciplines: list[str] = field(default_factory=list)
    timeout_seconds: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseConnector:
    name: str
    source_type: str
    connector_kind = "base"
    capabilities: tuple[str, ...] = ("latest", "search")

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        raise NotImplementedError

    def search(
        self,
        query: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
    ) -> list[Paper]:
        q = str(query).lower()
        return [
            paper for paper in self.fetch_latest(since=since, until=until, limit=max(limit * 5, 50))
            if q in paper.title.lower() or q in paper.abstract.lower()
        ][:limit]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "connector_kind": self.connector_kind,
            "capabilities": list(self.capabilities),
        }


class ApiConnector(BaseConnector):
    connector_kind = "api"


class FeedConnector(BaseConnector):
    connector_kind = "feed"


class Enricher:
    name: str
    capabilities: tuple[str, ...] = ("enrich",)

    def enrich(self, paper: Paper) -> Paper:
        raise NotImplementedError


SourceConnector = BaseConnector
