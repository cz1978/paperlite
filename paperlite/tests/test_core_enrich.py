from datetime import datetime

from paperlite import core
from paperlite.models import Paper


def make_paper():
    return Paper(
        id="paper:1",
        source="nature",
        source_type="journal",
        title="A paper",
        abstract="",
        authors=[],
        url="https://example.com/paper",
        published_at=datetime(2026, 4, 28),
    )


def test_enrich_paper_uses_timeout_and_continues_after_source_failure(monkeypatch):
    calls = []

    class FailingEnricher:
        def enrich(self, paper, *, timeout_seconds=None):
            calls.append(("failing", timeout_seconds))
            raise TimeoutError("slow upstream")

    class WorkingEnricher:
        def enrich(self, paper, *, timeout_seconds=None):
            calls.append(("working", timeout_seconds))
            return paper.model_copy(update={"doi": "10.1234/example"})

    enrichers = {
        "failing": FailingEnricher(),
        "working": WorkingEnricher(),
    }
    monkeypatch.setattr(core, "get_enricher", lambda name: enrichers[name])

    enriched = core.enrich_paper(make_paper(), "failing,working", timeout_seconds=2.5)

    assert sorted(calls) == [("failing", 2.5), ("working", 2.5)]
    assert enriched.doi == "10.1234/example"
    assert enriched.raw["enrich_warnings"] == ["failing: TimeoutError: slow upstream"]


def test_enrich_paper_uses_identifier_pass_before_openalex_when_doi_is_missing(monkeypatch):
    calls = []

    class CrossrefEnricher:
        def enrich(self, paper, *, timeout_seconds=None):
            calls.append(("crossref", paper.doi))
            return paper.model_copy(update={"doi": "10.1038/example"})

    class OpenAlexEnricher:
        def enrich(self, paper, *, timeout_seconds=None):
            calls.append(("openalex", paper.doi))
            assert paper.doi == "10.1038/example"
            return paper.model_copy(update={"openalex_id": "https://openalex.org/W1"})

    enrichers = {
        "crossref": CrossrefEnricher(),
        "openalex": OpenAlexEnricher(),
    }
    monkeypatch.setattr(core, "get_enricher", lambda name: enrichers[name])

    enriched = core.enrich_paper(make_paper(), "openalex,crossref", timeout_seconds=2.5)

    assert calls == [("crossref", None), ("openalex", "10.1038/example")]
    assert enriched.doi == "10.1038/example"
    assert enriched.openalex_id == "https://openalex.org/W1"
