from datetime import datetime

from paperlite.dedupe import dedupe_papers, merge_papers
from paperlite.models import Paper


def test_dedupe_merges_same_doi_evidence():
    first = Paper(
        id="doi:10.1038/test",
        source="crossref",
        source_type="journal",
        title="A paper",
        url="https://doi.org/10.1038/test",
        doi="10.1038/test",
        publisher="Springer Nature",
        source_records=[{"source": "crossref"}],
    )
    second = Paper(
        id="doi:10.1038/test",
        source="openalex",
        source_type="metadata",
        title="A paper",
        url="https://doi.org/10.1038/test",
        doi="10.1038/test",
        citation_count=12,
        concepts=["Biology"],
        source_records=[{"source": "openalex"}],
    )

    result = dedupe_papers([first, second])

    assert len(result) == 1
    assert result[0].publisher == "Springer Nature"
    assert result[0].citation_count == 12
    assert result[0].concepts == ["Biology"]
    assert result[0].source_records == [{"source": "crossref"}, {"source": "openalex"}]


def test_merge_fills_missing_identifiers():
    primary = Paper(id="pmid:1", source="pubmed", source_type="journal", title="Paper", url="https://pubmed/1")
    secondary = Paper(
        id="doi:10.1001/test",
        source="crossref",
        source_type="journal",
        title="Paper",
        url="https://doi.org/10.1001/test",
        doi="10.1001/test",
        issn=["0098-7484"],
    )

    merged = merge_papers(primary, secondary)

    assert merged.doi == "10.1001/test"
    assert merged.issn == ["0098-7484"]


def test_dedupe_merges_exact_normalized_title_with_same_year_without_identifier():
    first = Paper(
        id="source-a:1",
        source="source-a",
        source_type="journal",
        title="Imaging Dynamic Electrocatalytic Processes on Nano-Strained MoS2",
        url="https://example.com/a",
        published_at=datetime(2026, 4, 24),
        authors=["Ada"],
    )
    second = Paper(
        id="source-b:2",
        source="source-b",
        source_type="journal",
        title="Imaging dynamic electrocatalytic processes on nano strained MoS2",
        url="https://example.com/b",
        published_at=datetime(2026, 5, 1),
        abstract="Extra abstract.",
        authors=["Grace"],
    )
    different = Paper(
        id="source-c:3",
        source="source-c",
        source_type="journal",
        title="Imaging static electrocatalytic processes on nano strained MoS2",
        url="https://example.com/c",
        published_at=datetime(2026, 5, 1),
    )

    result = dedupe_papers([first, second, different])

    assert len(result) == 2
    assert result[0].abstract == "Extra abstract."
    assert result[0].authors == ["Ada", "Grace"]
