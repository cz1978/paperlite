import json
from datetime import datetime

from paperlite.exporters import export_papers
from paperlite.models import Paper


def make_paper():
    return Paper(
        id="arxiv:2401.00001",
        source="arxiv",
        source_type="preprint",
        title="A useful model",
        abstract="Abstract text.",
        authors=["Ada Lovelace"],
        url="https://arxiv.org/abs/2401.00001",
        pdf_url="https://arxiv.org/pdf/2401.00001",
        doi="10.48550/arXiv.2401.00001",
        published_at=datetime(2024, 1, 2, 3, 4, 5),
        categories=["cs.LG"],
    )


def test_json_export_is_list_of_papers():
    data = json.loads(export_papers([make_paper()], "json"))

    assert data[0]["id"] == "arxiv:2401.00001"
    assert data[0]["categories"] == ["cs.LG"]


def test_jsonl_export_has_one_json_object_per_line():
    body = export_papers([make_paper(), make_paper()], "jsonl")

    assert len(body.splitlines()) == 2


def test_markdown_export_contains_title_and_url():
    body = export_papers([make_paper()], "markdown")

    assert "## A useful model" in body
    assert "https://arxiv.org/abs/2401.00001" in body


def test_rss_export_contains_item_guid():
    body = export_papers([make_paper()], "rss")

    assert "<rss version=\"2.0\">" in body
    assert "<guid>arxiv:2401.00001</guid>" in body


def test_ris_export_contains_zotero_import_metadata_without_attachment():
    body = export_papers([make_paper()], "ris")

    assert "TY  - RPRT" in body
    assert "TI  - A useful model" in body
    assert "AU  - Ada Lovelace" in body
    assert "DO  - 10.48550/arXiv.2401.00001" in body
    assert "N1  - External PDF URL: https://arxiv.org/pdf/2401.00001" in body
    assert "L1  -" not in body


def test_bibtex_export_contains_zotero_import_metadata_without_attachment():
    body = export_papers([make_paper()], "bibtex")

    assert "@misc{arxiv_2401_00001," in body
    assert "title = {A useful model}" in body
    assert "author = {Ada Lovelace}" in body
    assert "doi = {10.48550/arXiv.2401.00001}" in body
    assert "External PDF URL: https://arxiv.org/pdf/2401.00001" in body
    assert "file =" not in body
