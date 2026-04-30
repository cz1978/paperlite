from paperlite.connectors.journals import JournalFeedConnector, paper_from_journal_entry


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_journal_entry_normalizes_to_paper():
    entry = {
        "title": "  A top journal article\n ",
        "link": "https://www.nature.com/articles/s41586-024-00001-0",
        "summary": "  Abstract text. ",
        "published_parsed": (2024, 1, 2, 3, 4, 5, 1, 2, 0),
        "authors": [{"name": "Ada Lovelace"}],
        "tags": [{"term": "Machine learning"}],
    }

    paper = paper_from_journal_entry(entry, "nature", "Nature")

    assert paper is not None
    assert paper.source == "nature"
    assert paper.source_type == "journal"
    assert paper.journal == "Nature"
    assert paper.title == "A top journal article"
    assert paper.abstract == "Abstract text."
    assert paper.authors == ["Ada Lovelace"]
    assert paper.categories == ["Machine learning"]
    assert paper.published_at.isoformat() == "2024-01-02T03:04:05"


def test_journal_entry_uses_doi_when_present():
    entry = {
        "title": "Paper",
        "link": "https://example.com/paper",
        "doi": "https://doi.org/10.1126/science.test",
    }

    paper = paper_from_journal_entry(entry, "science", "Science")

    assert paper.id == "doi:10.1126/science.test"
    assert paper.doi == "10.1126/science.test"


def test_journal_entry_uses_publication_month_from_description():
    entry = {
        "title": "Paper",
        "link": "https://www.sciencedirect.com/science/article/pii/S0309170826001181",
        "description": "<p>Publication date: July 2026</p>",
    }

    paper = paper_from_journal_entry(entry, "elsevier_journal", "Elsevier Journal")

    assert paper.published_at.isoformat() == "2026-07-01T00:00:00"


def test_journal_feed_connector_preserves_duplicate_dc_identifier_doi(monkeypatch):
    xml = """
    <rdf:RDF
      xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns="http://purl.org/rss/1.0/"
      xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel rdf:about="http://bmjleader.bmj.com">
        <title>BMJ Leader current issue</title>
        <items><rdf:Seq><rdf:li rdf:resource="http://bmjleader.bmj.com/cgi/content/short/10/1/1?rss=1" /></rdf:Seq></items>
      </channel>
      <item rdf:about="http://bmjleader.bmj.com/cgi/content/short/10/1/1?rss=1">
        <title>Case for managerial academic careers</title>
        <link>http://bmjleader.bmj.com/cgi/content/short/10/1/1?rss=1</link>
        <description><![CDATA[<sec><st>Abstract</st><p>Useful BMJ abstract.</p></sec>]]></description>
        <dc:date>2026-03-25T00:45:24-07:00</dc:date>
        <dc:identifier>info:doi/10.1136/leader-2024-001191</dc:identifier>
        <dc:identifier>hwp:master-id:leader;leader-2024-001191</dc:identifier>
      </item>
    </rdf:RDF>
    """
    captured = {}

    def fake_get_feed_url(url, *, timeout_seconds, request_profile):
        captured["request_profile"] = request_profile
        return FakeResponse(xml)

    monkeypatch.setattr("paperlite.connectors.journals.get_feed_url", fake_get_feed_url)

    papers = JournalFeedConnector(
        name="bmj_bmj_leader",
        feed_url="http://bmjleader.bmj.com/rss/current.xml",
        journal="BMJ Leader",
    ).fetch_latest(limit=1, request_profile="browser_compat")

    assert papers[0].doi == "10.1136/leader-2024-001191"
    assert papers[0].id == "doi:10.1136/leader-2024-001191"
    assert papers[0].published_at.isoformat() == "2026-03-25T07:45:24"
    assert "Useful BMJ abstract." in papers[0].abstract
    assert captured["request_profile"] == "browser_compat"
