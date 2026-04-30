from datetime import datetime

import httpx
import pytest

from paperlite.models import Paper
from paperlite.zotero import (
    ZoteroConfig,
    ZoteroNotConfiguredError,
    ZoteroRequestError,
    create_zotero_items,
    load_zotero_config,
    paper_to_zotero_item,
    zotero_status,
)


def make_paper(index: int = 1) -> Paper:
    return Paper(
        id=f"arxiv:{index}",
        source="arxiv",
        source_type="preprint",
        title=f"A useful model {index}",
        abstract="Abstract text.",
        authors=["Ada Lovelace", "Alan Turing"],
        url=f"https://example.com/{index}",
        pdf_url=f"https://example.com/{index}.pdf",
        doi=f"10.48550/arXiv.{index}",
        published_at=datetime(2024, 1, 2, 3, 4, 5),
        categories=["cs.LG"],
        concepts=["machine learning"],
        journal="arXiv",
        publisher="arXiv",
        pmid="123",
        pmcid="PMC123",
        openalex_id="https://openalex.org/W123",
    )


def test_zotero_status_does_not_expose_api_key():
    status = zotero_status(
        {
            "ZOTERO_API_KEY": "secret",
            "ZOTERO_LIBRARY_TYPE": "group",
            "ZOTERO_LIBRARY_ID": "42",
            "ZOTERO_COLLECTION_KEY": "ABC123",
        }
    )

    assert status == {
        "configured": True,
        "library_type": "group",
        "library_id": "42",
        "collection_key": "ABC123",
    }
    assert "secret" not in str(status)


def test_zotero_config_requires_key_and_library_id():
    with pytest.raises(ZoteroNotConfiguredError):
        load_zotero_config({})

    assert zotero_status({})["configured"] is False


def test_paper_to_zotero_item_maps_metadata_without_pdf_attachment():
    item = paper_to_zotero_item(make_paper(), collection_key="COLL")

    assert item["itemType"] == "preprint"
    assert item["title"] == "A useful model 1"
    assert item["creators"] == [
        {"creatorType": "author", "name": "Ada Lovelace"},
        {"creatorType": "author", "name": "Alan Turing"},
    ]
    assert item["abstractNote"] == "Abstract text."
    assert item["date"] == "2024-01-02"
    assert item["url"] == "https://example.com/1"
    assert item["DOI"] == "10.48550/arXiv.1"
    assert item["publicationTitle"] == "arXiv"
    assert item["collections"] == ["COLL"]
    assert {"tag": "paperlite"} in item["tags"]
    assert {"tag": "source:arxiv"} in item["tags"]
    assert {"tag": "cs.LG"} in item["tags"]
    assert "External PDF URL: https://example.com/1.pdf" in item["extra"]
    assert "PaperLite ID: arxiv:1" in item["extra"]
    assert "pdf_url" not in item
    assert "attachments" not in item


def test_create_zotero_items_posts_batches_with_write_token():
    config = ZoteroConfig(
        api_key="secret",
        library_type="user",
        library_id="123",
        collection_key="COLL",
        api_base_url="https://zotero.test",
    )
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        start = 0 if len(calls) == 1 else 50
        successful = {str(index): {"key": f"ITEM{start + index}"} for index in range(len(json))}
        return httpx.Response(
            200,
            json={"successful": successful, "failed": {}},
            request=httpx.Request("POST", url),
        )

    papers = [make_paper(index) for index in range(51)]
    result = create_zotero_items(papers, config=config, post=fake_post, timeout_seconds=2)

    assert len(calls) == 2
    assert calls[0]["url"] == "https://zotero.test/users/123/items"
    assert calls[0]["headers"]["Zotero-API-Key"] == "secret"
    assert calls[0]["headers"]["Zotero-API-Version"] == "3"
    assert calls[0]["headers"]["Zotero-Write-Token"] != calls[1]["headers"]["Zotero-Write-Token"]
    assert len(calls[0]["json"]) == 50
    assert len(calls[1]["json"]) == 1
    assert result["submitted"] == 51
    assert len(result["created"]) == 51
    assert result["failed"] == []


def test_create_zotero_items_maps_transport_and_json_errors():
    config = ZoteroConfig(
        api_key="secret",
        library_type="user",
        library_id="123",
        api_base_url="https://zotero.test",
    )

    def timeout_post(*_args, **_kwargs):
        raise httpx.TimeoutException("low level timeout")

    with pytest.raises(ZoteroRequestError) as timeout_error:
        create_zotero_items([make_paper()], config=config, post=timeout_post, timeout_seconds=2)

    assert "timed out" in str(timeout_error.value)
    assert "secret" not in str(timeout_error.value)

    def invalid_json_post(url, *, headers, json, timeout):
        return httpx.Response(200, content=b"not json", request=httpx.Request("POST", url))

    with pytest.raises(ZoteroRequestError) as json_error:
        create_zotero_items([make_paper()], config=config, post=invalid_json_post, timeout_seconds=2)

    assert "invalid JSON" in str(json_error.value)
    assert "secret" not in str(json_error.value)
