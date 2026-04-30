from datetime import datetime
from xml.etree import ElementTree as ET

from paperlite.connectors.crossref import paper_from_crossref_item
from paperlite.connectors.europepmc import paper_from_europepmc_item
from paperlite.connectors.journals import paper_from_journal_entry
from paperlite.connectors.openalex import OpenAlexConnector, paper_from_openalex_work
from paperlite.connectors.pubmed import paper_from_pubmed_article
from paperlite.identity import normalize_doi
from paperlite.models import Paper


def test_openalex_work_normalizes_to_paper():
    paper = paper_from_openalex_work(
        {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1038/test",
            "title": "A mapped paper",
            "publication_date": "2024-01-02",
            "abstract_inverted_index": {"hello": [0], "world": [1]},
            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1038/test",
                "pdf_url": "https://example.com/paper.pdf",
                "source": {
                    "display_name": "Nature",
                    "issn_l": "0028-0836",
                    "issn": ["0028-0836", "1476-4687"],
                },
            },
            "concepts": [{"display_name": "Machine learning"}],
            "cited_by_count": 42,
        }
    )

    assert paper.id == "doi:10.1038/test"
    assert paper.abstract == "hello world"
    assert paper.authors == ["Ada Lovelace"]
    assert paper.venue == "Nature"
    assert paper.citation_count == 42
    assert paper.openalex_id == "https://openalex.org/W123"


def test_crossref_item_normalizes_metadata():
    paper = paper_from_crossref_item(
        {
            "DOI": "10.1126/science.test",
            "URL": "https://doi.org/10.1126/science.test",
            "title": ["A Crossref paper"],
            "container-title": ["Science"],
            "publisher": "AAAS",
            "ISSN": ["0036-8075"],
            "type": "journal-article",
            "issued": {"date-parts": [[2024, 2, 3]]},
            "author": [{"given": "Grace", "family": "Hopper"}],
            "subject": ["Computer science"],
        }
    )

    assert paper.id == "doi:10.1126/science.test"
    assert paper.source_type == "journal"
    assert paper.publisher == "AAAS"
    assert paper.issn == ["0036-8075"]
    assert paper.published_at.isoformat() == "2024-02-03T00:00:00"


def test_journal_feed_entry_extracts_nature_prism_doi():
    paper = paper_from_journal_entry(
        {
            "title": "A Nature paper",
            "link": "https://www.nature.com/articles/s41560-026-02057-y",
            "id": "https://www.nature.com/articles/s41560-026-02057-y",
            "prism_doi": "10.1038/s41560-026-02057-y",
            "dc_identifier": "doi:10.1038/s41560-026-02057-y",
            "summary": (
                '<p>Nature Energy, Published online: 27 April 2026; '
                '<a href="https://www.nature.com/articles/s41560-026-02057-y">'
                "doi:10.1038/s41560-026-02057-y</a></p>Sodium is not lithium"
            ),
        },
        source="nature_nature_energy_current",
        journal="Nature Energy",
    )

    assert paper is not None
    assert paper.id == "doi:10.1038/s41560-026-02057-y"
    assert paper.doi == "10.1038/s41560-026-02057-y"
    assert paper.source_records[0]["doi"] == "10.1038/s41560-026-02057-y"


def test_journal_feed_entry_infers_nature_doi_from_article_url():
    paper = paper_from_journal_entry(
        {
            "title": "A Nature URL paper",
            "link": "https://www.nature.com/articles/d41586-026-01320-2",
            "id": "https://www.nature.com/articles/d41586-026-01320-2",
            "summary": "Nature news item.",
        },
        source="nature",
        journal="Nature",
    )

    assert paper is not None
    assert paper.id == "doi:10.1038/d41586-026-01320-2"
    assert paper.doi == "10.1038/d41586-026-01320-2"


def test_normalize_doi_preserves_valid_science_advances_suffix():
    assert normalize_doi("https://doi.org/10.1126/sciadv.adv3124") == "10.1126/sciadv.adv3124"
    assert normalize_doi("10.1101/2026.04.29.123456v2") == "10.1101/2026.04.29.123456"


def test_journal_feed_entry_infers_arxiv_doi_from_category_url():
    paper = paper_from_journal_entry(
        {
            "title": "An arXiv category paper",
            "link": "https://arxiv.org/abs/2604.24766",
            "id": "https://arxiv.org/abs/2604.24766",
            "summary": "A useful abstract.",
        },
        source="arxiv_cs",
        journal="arXiv Computer Science",
    )

    assert paper is not None
    assert paper.id == "doi:10.48550/arxiv.2604.24766"
    assert paper.doi == "10.48550/arxiv.2604.24766"
    assert paper.source_records[0]["doi"] == "10.48550/arxiv.2604.24766"


def test_journal_feed_entry_infers_ams_doi_from_article_url():
    paper = paper_from_journal_entry(
        {
            "title": "A climate paper",
            "link": "https://journals.ametsoc.org/view/journals/clim/39/11/JCLI-D-25-0190.1.xml",
            "id": "https://journals.ametsoc.org/view/journals/clim/39/11/JCLI-D-25-0190.1.xml",
            "summary": "Journal Name: Journal of Climate",
        },
        source="ams_journal_of_climate",
        journal="Journal of Climate",
    )

    assert paper is not None
    assert paper.id == "doi:10.1175/jcli-d-25-0190.1"
    assert paper.doi == "10.1175/jcli-d-25-0190.1"


def test_pubmed_xml_normalizes_abstract_ids_and_mesh():
    root = ET.fromstring(
        """
        <PubmedArticle>
          <MedlineCitation>
            <PMID>12345</PMID>
            <Article>
              <Journal>
                <ISSN>0028-4793</ISSN>
                <Title>New England Journal of Medicine</Title>
                <JournalIssue>
                  <PubDate><Year>2024</Year><Month>Jan</Month><Day>04</Day></PubDate>
                </JournalIssue>
              </Journal>
              <ArticleTitle>Clinical paper</ArticleTitle>
              <Abstract><AbstractText>Useful abstract.</AbstractText></Abstract>
              <AuthorList>
                <Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author>
              </AuthorList>
            </Article>
            <MeshHeadingList>
              <MeshHeading><DescriptorName>Immunotherapy</DescriptorName></MeshHeading>
            </MeshHeadingList>
          </MedlineCitation>
          <PubmedData>
            <ArticleIdList>
              <ArticleId IdType="doi">10.1056/test</ArticleId>
              <ArticleId IdType="pmc">PMC123</ArticleId>
            </ArticleIdList>
          </PubmedData>
        </PubmedArticle>
        """
    )

    paper = paper_from_pubmed_article(root)

    assert paper.id == "doi:10.1056/test"
    assert paper.pmid == "12345"
    assert paper.pmcid == "PMC123"
    assert paper.abstract == "Useful abstract."
    assert paper.categories == ["Immunotherapy"]


def test_europepmc_item_normalizes_medical_metadata():
    paper = paper_from_europepmc_item(
        {
            "id": "98765",
            "source": "MED",
            "pmid": "98765",
            "pmcid": "PMC987",
            "doi": "10.1001/jama.test",
            "title": "Europe PMC paper",
            "abstractText": "An abstract.",
            "authorString": "Ada Lovelace, Grace Hopper",
            "journalTitle": "JAMA",
            "firstPublicationDate": "2024-03-04",
            "keywordList": {"keyword": ["clinical"]},
        }
    )

    assert paper.id == "doi:10.1001/jama.test"
    assert paper.source == "europepmc"
    assert paper.source_type == "journal"
    assert paper.authors == ["Ada Lovelace", "Grace Hopper"]
    assert paper.pmid == "98765"
    assert paper.categories == ["clinical"]


def test_chemrxiv_crossref_mapping_uses_preprint_namespace():
    paper = paper_from_crossref_item(
        {
            "DOI": "10.26434/chemrxiv-2026-test",
            "URL": "https://doi.org/10.26434/chemrxiv-2026-test",
            "title": ["ChemRxiv paper"],
            "type": "posted-content",
            "issued": {"date-parts": [[2026, 1, 2]]},
        },
        source="chemrxiv",
        source_type="preprint",
    )

    assert paper.id == "chemrxiv:10.26434/chemrxiv-2026-test"
    assert paper.source_type == "preprint"


def test_openalex_enrich_rejects_low_confidence_title_match(monkeypatch):
    target = Paper(
        id="url:nature-energy",
        source="nature_nature_energy_current",
        source_type="journal",
        title="Imaging dynamic electrocatalytic processes on nano-strained MoS 2 using interferometric electro-optical microscopy",
        abstract="",
        authors=[],
        url="https://www.nature.com/articles/s41560-026-02043-4",
        published_at=datetime(2026, 4, 24),
    )
    wrong = Paper(
        id="openalex:W163563437",
        source="openalex",
        source_type="metadata",
        title="Integrated Biosensor Systems: Automated Microfluidic Pathogen Detection Platforms And Microcantilever-Based Monitoring Of Biological Activity",
        abstract="",
        authors=[],
        url="https://hdl.handle.net/1813/14800",
        pdf_url="https://hdl.handle.net/1813/14800",
        published_at=datetime(2010, 4, 9),
        categories=["Biosensor", "Microfluidics"],
        concepts=["Biosensor", "Microfluidics"],
        openalex_id="https://openalex.org/W163563437",
        citation_count=1,
    )
    connector = OpenAlexConnector()
    monkeypatch.setattr(connector, "search", lambda *args, **kwargs: [wrong])

    enriched = connector.enrich(target, timeout_seconds=1)

    assert enriched.openalex_id is None
    assert enriched.pdf_url is None
    assert enriched.citation_count is None
    assert enriched.concepts == []


def test_openalex_enrich_accepts_high_confidence_title_match(monkeypatch):
    target = Paper(
        id="url:nature-energy",
        source="nature_nature_energy_current",
        source_type="journal",
        title="Imaging dynamic electrocatalytic processes on nano-strained MoS 2 using interferometric electro-optical microscopy",
        abstract="",
        authors=[],
        url="https://www.nature.com/articles/s41560-026-02043-4",
        published_at=datetime(2026, 4, 24),
    )
    found = Paper(
        id="openalex:W7155532906",
        source="openalex",
        source_type="metadata",
        title="Imaging dynamic electrocatalytic processes on nano-strained MoS2 using interferometric electro-optical microscopy",
        abstract="",
        authors=[],
        url="https://doi.org/10.1038/s41560-026-02043-4",
        doi="10.1038/s41560-026-02043-4",
        published_at=datetime(2026, 4, 24),
        journal="Nature Energy",
        venue="Nature Energy",
        openalex_id="https://openalex.org/W7155532906",
        citation_count=0,
    )
    connector = OpenAlexConnector()
    monkeypatch.setattr(connector, "search", lambda *args, **kwargs: [found])

    enriched = connector.enrich(target, timeout_seconds=1)

    assert enriched.doi == "10.1038/s41560-026-02043-4"
    assert enriched.openalex_id == "https://openalex.org/W7155532906"
    assert enriched.venue == "Nature Energy"
