from paperlite.identity import paper_id


def test_arxiv_version_normalizes_to_stable_id():
    assert paper_id("arxiv", "https://arxiv.org/abs/2401.00001v2") == "arxiv:2401.00001"


def test_biorxiv_version_normalizes_to_provider_doi_id():
    assert (
        paper_id("biorxiv", "https://www.biorxiv.org/content/10.1101/2024.01.01.000001v3")
        == "biorxiv:10.1101/2024.01.01.000001"
    )


def test_medrxiv_uses_medrxiv_namespace():
    assert (
        paper_id("medrxiv", "https://www.medrxiv.org/content/10.1101/2024.03.05.24303800v1")
        == "medrxiv:10.1101/2024.03.05.24303800"
    )


def test_journal_prefers_doi_over_url_hash():
    assert (
        paper_id("nature", "https://www.nature.com/articles/s41586-024-00001-0", "10.1038/s41586-024-00001-0")
        == "doi:10.1038/s41586-024-00001-0"
    )


def test_url_fallback_is_stable():
    assert paper_id("nature", "https://example.com/a") == paper_id("science", "https://example.com/a")
