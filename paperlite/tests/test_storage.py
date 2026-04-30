import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from paperlite.models import Paper
from paperlite import storage


def make_paper(id="philarchive:1", title="Stored paper"):
    return Paper(
        id=id,
        source=id.split(":", 1)[0],
        source_type="working_papers",
        title=title,
        abstract="Cached abstract.",
        authors=["Ada Lovelace"],
        url=f"https://example.com/{id}",
        doi="10.1234/example",
        published_at=datetime(2026, 4, 28, 9),
        categories=["philosophy"],
    )


def test_sqlite_cache_upserts_and_groups_by_source(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )

    first = storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key="philarchive",
        papers=[make_paper()],
        path=db_path,
    )
    duplicate = storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key="philarchive",
        papers=[make_paper()],
        path=db_path,
    )
    storage.record_source_result(
        run_id=run["run_id"],
        source_key="philarchive",
        endpoint_key="philarchive-rss",
        endpoint_mode="rss",
        count=1,
        warnings=["partial"],
        path=db_path,
    )
    storage.finish_crawl_run(run["run_id"], status="completed", total_items=1, warnings=["partial"], path=db_path)

    cached = storage.query_daily_cache(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        limit_per_source=10,
        path=db_path,
    )
    completed = storage.get_crawl_run(run["run_id"], path=db_path)

    assert first == 1
    assert duplicate == 0
    assert cached["selection_mode"] == "cache"
    assert cached["groups"][0]["source"] == "philarchive"
    assert cached["groups"][0]["items"][0]["id"] == "philarchive:1"
    assert cached["groups"][0]["items"][0]["_cache_date"] == "2026-04-28"
    assert completed["status"] == "completed"
    assert completed["source_results"][0]["warnings"] == ["partial"]


def test_daily_cache_dedupes_across_sources_without_deleting_entries(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["source-a", "source-b"],
        limit_per_source=50,
        path=db_path,
    )
    first = make_paper("source-a:1", title="Shared DOI paper")
    first.authors = ["Ada"]
    first.source_records = [{"source": "source-a"}]
    second = make_paper("source-b:2", title="Shared DOI paper")
    second.authors = ["Grace"]
    second.source_records = [{"source": "source-b"}]

    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key="source-a",
        papers=[first],
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key="source-b",
        papers=[second],
        path=db_path,
    )

    cached = storage.query_daily_cache(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        limit_per_source=10,
        path=db_path,
    )
    with storage.connect(db_path) as connection:
        raw_count = connection.execute("SELECT COUNT(*) FROM daily_entries").fetchone()[0]

    items = [item for group in cached["groups"] for item in group["items"]]
    assert raw_count == 2
    assert len(items) == 1
    assert items[0]["_canonical_key"].startswith("doi:")
    assert items[0]["_daily_sources"] == ["source-a", "source-b"]
    assert items[0]["authors"] == ["Ada", "Grace"]
    assert items[0]["source_records"] == [{"source": "source-a"}, {"source": "source-b"}]


def test_cache_filters_by_date_discipline_and_source(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-29",
        discipline_key="humanities",
        source_keys=["philarchive", "philsci"],
        limit_per_source=50,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key="philarchive",
        papers=[make_paper("philarchive:1")],
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-29",
        discipline_key="humanities",
        source_key="philsci",
        papers=[make_paper("philsci:1")],
        path=db_path,
    )

    only_philsci = storage.query_daily_cache(
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="humanities",
        source_keys=["philsci"],
        path=db_path,
    )

    assert [group["source"] for group in only_philsci["groups"]] == ["philsci"]
    assert only_philsci["groups"][0]["items"][0]["id"] == "philsci:1"


def test_cache_sanitizes_metadata_only_rss_abstracts(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2026-04-27",
        date_to="2026-04-27",
        discipline_key="energy",
        source_keys=["nature_nature_energy_current"],
        limit_per_source=50,
        path=db_path,
    )
    paper = make_paper("nature:energy:1", title="Sodium is not lithium")
    paper.source = "nature_nature_energy_current"
    paper.source_type = "journal"
    paper.abstract = (
        '<p>Nature Energy, Published online: 27 April 2026; '
        '<a href="https://www.nature.com/articles/s41560-026-02057-y">'
        "doi:10.1038/s41560-026-02057-y</a></p>Sodium is not lithium"
    )
    paper.doi = "10.1038/s41560-026-02057-y"
    paper.journal = "Nature Energy"
    paper.venue = "Nature Energy"

    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-27",
        discipline_key="energy",
        source_key="nature_nature_energy_current",
        papers=[paper],
        path=db_path,
    )
    cached = storage.query_daily_cache(
        date_from="2026-04-27",
        date_to="2026-04-27",
        discipline_key="energy",
        path=db_path,
    )
    with storage.connect(db_path) as connection:
        row = connection.execute("SELECT payload_json FROM paper_items WHERE paper_id = ?", (paper.id,)).fetchone()

    item = cached["groups"][0]["items"][0]
    stored = json.loads(row["payload_json"])
    assert item["abstract"] == ""
    assert stored["abstract"] == ""
    assert "<p>" not in json.dumps(item)
    assert "Published online" not in json.dumps(item)


def test_cache_strips_arxiv_announcement_boilerplate(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="math",
        source_keys=["arxiv"],
        limit_per_source=50,
        path=db_path,
    )
    paper = make_paper("arxiv:2604.24891v1", title="A semigroup approximation")
    paper.source = "arxiv"
    paper.source_type = "preprint"
    paper.doi = ""
    paper.abstract = (
        "arXiv:2604.24891v1 Announce Type: new Abstract: "
        "For a fixed positive integer $d$ and small real $p>0$, we sample a random subset "
        "of a lattice and prove a generated semigroup has a well approximated region with high probability. "
        "The result extends prior work from one dimension to higher-dimensional settings."
    )

    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-29",
        discipline_key="math",
        source_key="arxiv",
        papers=[paper],
        path=db_path,
    )
    cached = storage.query_daily_cache(
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="math",
        path=db_path,
    )

    item = cached["groups"][0]["items"][0]
    assert item["abstract"].startswith("For a fixed positive integer")
    assert "arXiv:2604.24891v1" not in item["abstract"]
    assert "Announce Type" not in item["abstract"]
    assert "Abstract:" not in item["abstract"]


def test_cache_infers_nature_doi_from_article_url(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="energy",
        source_keys=["nature_nature_energy_current"],
        limit_per_source=50,
        path=db_path,
    )
    paper = make_paper("url:nature-energy", title="Sodium is not lithium")
    paper.source = "nature_nature_energy_current"
    paper.source_type = "journal"
    paper.url = "https://www.nature.com/articles/s41560-026-02057-y"
    paper.doi = None
    paper.abstract = "This is a real abstract with enough words to be retained in the local cache for display."

    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-29",
        discipline_key="energy",
        source_key="nature_nature_energy_current",
        papers=[paper],
        path=db_path,
    )
    cached = storage.query_daily_cache(
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="energy",
        path=db_path,
    )

    item = cached["groups"][0]["items"][0]
    assert item["doi"] == "10.1038/s41560-026-02057-y"


def test_paper_embeddings_upsert_and_vector_search_sort(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="computer_science",
        source_keys=["arxiv"],
        limit_per_source=50,
        path=db_path,
    )
    rag = make_paper("arxiv:rag", title="RAG agent benchmark")
    rag.source = "arxiv"
    rag.source_type = "preprint"
    rag.doi = "10.1234/rag"
    rag.abstract = "Retrieval augmented generation benchmark with agent evaluation."
    protein = make_paper("arxiv:protein", title="Protein folding assay")
    protein.source = "arxiv"
    protein.source_type = "preprint"
    protein.doi = "10.1234/protein"
    protein.abstract = "A biology assay unrelated to retrieval systems."
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-29",
        discipline_key="computer_science",
        source_key="arxiv",
        papers=[rag, protein],
        path=db_path,
    )
    cached = storage.daily_cache_papers_for_rag(
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="computer_science",
        path=db_path,
    )
    rag = next(paper for paper in cached if paper.id == "arxiv:rag")
    protein = next(paper for paper in cached if paper.id == "arxiv:protein")

    rag_hash = storage.paper_embedding_hash(rag)
    storage.upsert_paper_embedding(
        paper_id=rag.id,
        content_hash=rag_hash,
        embedding_model="mock-embed",
        embedding=[1.0, 0.0],
        path=db_path,
    )
    storage.upsert_paper_embedding(
        paper_id=protein.id,
        content_hash=storage.paper_embedding_hash(protein),
        embedding_model="mock-embed",
        embedding=[0.0, 1.0],
        path=db_path,
    )

    result = storage.search_paper_embeddings(
        query_embedding=[0.9, 0.1],
        embedding_model="mock-embed",
        date_from="2026-04-29",
        date_to="2026-04-29",
        discipline_key="computer_science",
        top_k=2,
        path=db_path,
    )

    assert result["candidates"] == 2
    assert result["indexed"] == 2
    assert result["matches"][0]["paper"].id == "arxiv:rag"
    assert result["matches"][0]["score"] > result["matches"][1]["score"]

    changed = rag.model_copy(update={"abstract": "Updated RAG metadata."})
    changed_hash = storage.paper_embedding_hash(changed)
    storage.upsert_paper_embedding(
        paper_id=changed.id,
        content_hash=changed_hash,
        embedding_model="mock-embed",
        embedding=[0.5, 0.5],
        path=db_path,
    )
    stored = storage.get_paper_embedding(changed.id, path=db_path)

    assert changed_hash != rag_hash
    assert stored["content_hash"] == changed_hash
    assert stored["embedding"] == [0.5, 0.5]


def test_crawl_run_reuses_recent_completed_run(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    first = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )
    storage.finish_crawl_run(first["run_id"], status="completed", total_items=0, path=db_path)

    second = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        reuse_within_seconds=600,
        path=db_path,
    )

    assert second["run_id"] == first["run_id"]
    assert second["reused"] is True
    assert second["reuse_reason"] == "cooldown"
    assert second["cooldown_seconds_remaining"] > 0


def test_crawl_run_reuses_active_run(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    first = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )

    second = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        reuse_within_seconds=600,
        path=db_path,
    )

    assert second["run_id"] == first["run_id"]
    assert second["reused"] is True
    assert second["reuse_reason"] == "active"


def test_crawl_run_does_not_reuse_failed_run_in_cooldown(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    failed = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )
    storage.finish_crawl_run(failed["run_id"], status="failed", total_items=0, error="boom", path=db_path)

    retry = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        reuse_within_seconds=600,
        path=db_path,
    )

    assert retry["run_id"] != failed["run_id"]
    assert retry["reused"] is False
    assert retry["status"] == "queued"


def test_crawl_run_reuses_active_duplicate_without_cooldown(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    first = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive", "arxiv"],
        limit_per_source=50,
        path=db_path,
    )

    second = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["arxiv", "philarchive"],
        limit_per_source=50,
        path=db_path,
    )

    assert second["run_id"] == first["run_id"]
    assert second["reused"] is True
    assert second["reuse_reason"] == "active"


def test_crawl_run_active_key_is_single_flight_under_parallel_requests(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"

    def create_one():
        return storage.create_crawl_run(
            date_from="2026-04-28",
            date_to="2026-04-28",
            discipline_key="humanities",
            source_keys=["philarchive"],
            limit_per_source=50,
            path=db_path,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        runs = list(executor.map(lambda _index: create_one(), range(4)))

    assert {run["run_id"] for run in runs} == {runs[0]["run_id"]}
    with storage.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM crawl_runs WHERE status IN ('queued', 'running')").fetchone()[0]
    assert count == 1


def test_latest_failed_run_blocks_reuse_of_older_completed_run(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    completed = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )
    storage.finish_crawl_run(completed["run_id"], status="completed", total_items=0, path=db_path)
    failed = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )
    storage.finish_crawl_run(failed["run_id"], status="failed", total_items=0, error="boom", path=db_path)

    retry = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        reuse_within_seconds=600,
        path=db_path,
    )

    assert retry["run_id"] not in {completed["run_id"], failed["run_id"]}
    assert retry["reused"] is False
    assert retry["status"] == "queued"


def test_connect_migrates_old_schema_before_marking_version(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_meta (key, value) VALUES ('schema_version', '3')")
        connection.execute("CREATE TABLE paper_items (paper_id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL, payload_json TEXT NOT NULL)")
        connection.execute("CREATE TABLE crawl_runs (run_id TEXT PRIMARY KEY, status TEXT NOT NULL)")

    with storage.connect(db_path) as connection:
        schema_version = connection.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()["value"]
        paper_columns = {row["name"] for row in connection.execute("PRAGMA table_info(paper_items)").fetchall()}
        crawl_columns = {row["name"] for row in connection.execute("PRAGMA table_info(crawl_runs)").fetchall()}

    assert schema_version == str(storage.SCHEMA_VERSION)
    assert {"published_at", "updated_at"} <= paper_columns
    assert {"date_from", "date_to", "discipline_key", "source_keys_json", "warnings_json", "request_key"} <= crawl_columns


def test_list_crawl_runs_filters_by_status_and_discipline(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    humanities = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )
    energy = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="energy",
        source_keys=["nature_energy"],
        limit_per_source=50,
        path=db_path,
    )
    storage.finish_crawl_run(humanities["run_id"], status="completed", total_items=1, path=db_path)
    storage.finish_crawl_run(energy["run_id"], status="failed", total_items=0, error="boom", path=db_path)

    completed = storage.list_crawl_runs(status="completed", path=db_path)
    energy_runs = storage.list_crawl_runs(discipline_key="energy", path=db_path)

    assert [run["run_id"] for run in completed] == [humanities["run_id"]]
    assert [run["run_id"] for run in energy_runs] == [energy["run_id"]]
    assert energy_runs[0]["error"] == "boom"


def test_crawl_schedules_can_be_due_and_marked(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    schedule = storage.create_or_update_crawl_schedule(
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        interval_minutes=60,
        lookback_days=1,
        run_now=True,
        path=db_path,
    )

    due = storage.due_crawl_schedules(path=db_path)
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        path=db_path,
    )
    storage.mark_crawl_schedule_started(
        schedule["schedule_id"],
        run_id=run["run_id"],
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        path=db_path,
    )
    storage.mark_crawl_schedule_finished(schedule["schedule_id"], warnings=["ok"], path=db_path)
    stored = storage.get_crawl_schedule(schedule["schedule_id"], path=db_path)

    assert due[0]["schedule_id"] == schedule["schedule_id"]
    assert stored["last_run_id"] == run["run_id"]
    assert stored["warnings"] == ["ok"]


def test_crawl_schedule_status_and_delete(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    schedule = storage.create_or_update_crawl_schedule(
        discipline_key="humanities",
        source_keys=["philarchive"],
        limit_per_source=50,
        interval_minutes=60,
        lookback_days=1,
        run_now=True,
        path=db_path,
    )

    paused = storage.update_crawl_schedule_status(schedule["schedule_id"], status="paused", path=db_path)
    due_paused = storage.due_crawl_schedules(path=db_path)
    active = storage.update_crawl_schedule_status(schedule["schedule_id"], status="active", path=db_path)
    due_active = storage.due_crawl_schedules(path=db_path)
    deleted = storage.delete_crawl_schedule(schedule["schedule_id"], path=db_path)

    assert paused["status"] == "paused"
    assert due_paused == []
    assert active["status"] == "active"
    assert due_active[0]["schedule_id"] == schedule["schedule_id"]
    assert deleted is True
    assert storage.get_crawl_schedule(schedule["schedule_id"], path=db_path) is None


def test_translation_cache_roundtrips_payload(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    payload = {
        "paper": make_paper().to_dict(),
        "target_language": "zh-CN",
        "style": "brief",
        "title_zh": "缓存标题",
        "brief": {"cn_flash_180": "缓存摘要", "card_headline": "缓存", "card_bullets": [], "card_tags": []},
        "cn_flash_180": "缓存摘要",
        "card_headline": "缓存",
        "card_bullets": [],
        "card_tags": [],
        "translation": "标题：缓存标题\n摘要：缓存摘要",
        "configured": True,
        "model": "deepseek-chat",
        "warnings": [],
        "cached": False,
    }

    storage.upsert_translation_cache(
        cache_key="cache-key",
        paper_id="philarchive:1",
        content_hash="content-hash",
        target_language="zh-CN",
        style="brief",
        payload=payload,
        path=db_path,
    )
    cached = storage.get_translation_cache("cache-key", path=db_path)

    assert cached is not None
    assert cached["cached"] is True
    assert cached["title_zh"] == "缓存标题"
    assert cached["brief"]["cn_flash_180"] == "缓存摘要"


def test_library_state_actions_and_events_roundtrip(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    paper = make_paper()

    empty_state = storage.get_library_state([paper], path=db_path)
    with storage.connect(db_path) as connection:
        item_count = connection.execute("SELECT COUNT(*) FROM library_items").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM library_events").fetchone()[0]

    assert empty_state["items"][0]["read"] is False
    assert item_count == 0
    assert event_count == 0

    read = storage.apply_library_action(action="read", papers=[paper], path=db_path)
    favorite = storage.apply_library_action(action="favorite", papers=[paper], path=db_path)
    hidden = storage.apply_library_action(action="hide", papers=[paper], path=db_path)

    key = hidden["updated"][0]["library_key"]
    state = storage.get_library_state([paper], path=db_path)["by_key"][key]
    events = storage.list_library_events(library_key=key, path=db_path)

    assert read["updated"][0]["read"] is True
    assert favorite["updated"][0]["favorite"] is True
    assert hidden["updated"][0]["hidden"] is True
    assert state["read"] is True
    assert state["favorite"] is True
    assert state["hidden"] is True
    assert {event["action"] for event in events} == {"read", "favorite", "hide"}
    assert storage.list_library_items(state="favorite", path=db_path)[0]["library_key"] == key

    unhidden = storage.apply_library_action(action="unhide", papers=[paper], path=db_path)
    assert unhidden["updated"][0]["hidden"] is False


def test_undo_library_actions_do_not_train_preference_model(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    paper = make_paper("arxiv:undo", title="RAG undo benchmark")

    storage.apply_library_action(action="read", papers=[paper], path=db_path)
    storage.apply_library_action(action="favorite", papers=[paper], path=db_path)
    storage.apply_library_action(action="hide", papers=[paper], path=db_path)
    storage.apply_library_action(action="unread", papers=[paper], path=db_path)
    storage.apply_library_action(action="unfavorite", papers=[paper], path=db_path)
    storage.apply_library_action(action="unhide", papers=[paper], path=db_path)

    key = storage.get_library_state([paper], path=db_path)["items"][0]["library_key"]
    state = storage.get_library_state([paper], path=db_path)["by_key"][key]
    events = storage.list_library_events(library_key=key, path=db_path)
    profile = storage.get_preference_profile(path=db_path)
    training = storage.export_preference_training_data(path=db_path)
    evaluation = storage.evaluate_preference_learning(path=db_path)

    assert state["read"] is False
    assert state["favorite"] is False
    assert state["hidden"] is False
    assert events == []
    assert profile["signal_counts"]["actions"] == {}
    assert profile["signal_counts"]["read_count"] == 0
    assert profile["signal_counts"]["favorite_count"] == 0
    assert profile["signal_counts"]["hidden_count"] == 0
    assert training["examples"] == []
    assert evaluation["example_count"] == 0


def test_preference_prompts_roundtrip_and_redact_secret(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"

    saved = storage.save_preference_prompt(
        text="Prefer RAG agents; api_key=super-secret sk-testsecret123456",
        weight=7,
        path=db_path,
    )
    listed = storage.list_preference_prompts(path=db_path)
    updated = storage.update_preference_prompt(
        prompt_id=saved["prompt_id"],
        text="Prefer evaluation benchmarks",
        enabled=False,
        weight=3,
        path=db_path,
    )
    disabled = storage.list_preference_prompts(enabled=False, path=db_path)
    deleted = storage.delete_preference_prompt(prompt_id=saved["prompt_id"], path=db_path)

    assert saved["enabled"] is True
    assert saved["weight"] == 5
    assert "super-secret" not in saved["text"]
    assert "sk-testsecret123456" not in saved["text"]
    assert "[redacted]" in saved["text"]
    assert listed[0]["prompt_id"] == saved["prompt_id"]
    assert updated["enabled"] is False
    assert updated["weight"] == 3
    assert disabled[0]["text"] == "Prefer evaluation benchmarks"
    assert deleted is True
    assert storage.list_preference_prompts(path=db_path) == []


def test_preference_profile_rebuilds_from_prompts_and_library_signals(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    positive = make_paper("arxiv:rag", title="RAG agent benchmark")
    positive.abstract = "A careful benchmark for retrieval augmented generation agents."
    negative = make_paper("noise:1", title="Cooking announcement")
    negative.abstract = "A community announcement with no research method."

    storage.save_preference_prompt(text="Prefer RAG agent evaluation", path=db_path)
    storage.apply_library_action(action="favorite", papers=[positive], path=db_path)
    storage.apply_library_action(action="zotero", papers=[positive], path=db_path)
    storage.apply_library_action(action="hide", papers=[negative], path=db_path)
    profile = storage.get_preference_profile(path=db_path)

    terms = {item["term"] for item in profile["profile"]["positive_terms"]}
    negative_terms = {item["term"] for item in profile["profile"]["negative_terms"]}
    counts = profile["signal_counts"]

    assert profile["profile_id"] == "default"
    assert "长期提示词" in profile["profile"]["summary"]
    assert {"rag", "agent", "evaluation"} <= terms
    assert "cooking" in negative_terms
    assert counts["enabled_prompt_count"] == 1
    assert counts["favorite_count"] == 1
    assert counts["hidden_count"] == 1
    assert counts["actions"]["favorite"] == 1
    assert counts["actions"]["zotero"] == 1
    assert counts["actions"]["hide"] == 1
    with storage.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM preference_profile").fetchone()[0] == 1


def test_preference_profile_uses_manual_filter_query_history(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"

    first = storage.record_preference_query(text="RAG agent benchmark", path=db_path)
    second = storage.record_preference_query(text="RAG agent benchmark", path=db_path)
    storage.record_preference_query(text="api_key=secret-token", path=db_path)
    queries = storage.list_preference_queries(path=db_path)
    profile = storage.get_preference_profile(path=db_path)

    terms = {item["term"]: item["weight"] for item in profile["profile"]["positive_terms"]}
    counts = profile["signal_counts"]

    assert first["use_count"] == 1
    assert second["use_count"] == 2
    assert queries[0]["text"] == "api_key=[redacted]" or queries[0]["text"] == "RAG agent benchmark"
    assert "secret-token" not in str(queries)
    assert "常用筛选词" in profile["profile"]["summary"]
    assert any(item["text"] == "RAG agent benchmark" and item["use_count"] == 2 for item in profile["profile"]["recent_queries"])
    assert terms["rag"] >= 4
    assert terms["agent"] >= 4
    assert counts["query_count"] == 2
    assert counts["query_use_count"] == 3


def test_preference_terms_filter_feed_and_latex_boilerplate(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    positive = make_paper("arxiv:rag-noise", title="RAG agent benchmark")
    positive.abstract = (
        "arXiv preprint abstract with mathbb geq ldots and of in to by "
        "plus retrieval augmented generation evaluation."
    )
    positive.doi = "10.48550/arxiv.2604.99999"
    negative = make_paper("noise:notice", title="Conference announcement")
    negative.abstract = "Abstract type announcement announce v1 with mathbb geq and no research method."

    storage.apply_library_action(action="favorite", papers=[positive], path=db_path)
    storage.apply_library_action(action="hide", papers=[negative], path=db_path)
    profile = storage.get_preference_profile(path=db_path)
    evaluation = storage.evaluate_preference_learning(path=db_path)

    positive_terms = {item["term"] for item in profile["profile"]["positive_terms"]}
    evaluation_terms = {item["term"] for item in evaluation["top_positive_terms"] + evaluation["top_negative_terms"]}
    noisy_terms = {"arxiv", "abstract", "mathbb", "geq", "ldots", "of", "in", "to", "by", "preprint", "type", "announce", "v1"}

    assert {"rag", "agent", "benchmark", "retrieval", "augmented", "generation", "evaluation"} & positive_terms
    assert not (noisy_terms & positive_terms)
    assert not (noisy_terms & evaluation_terms)


def test_relevant_preference_profile_filters_to_current_topic(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    rag = make_paper("arxiv:rag", title="RAG agent benchmark")
    rag.doi = "10.1234/rag"
    rag.abstract = "Retrieval augmented generation benchmark with agent evaluation."
    protein = make_paper("bio:protein", title="Protein folding screen")
    protein.doi = "10.1234/protein"
    protein.abstract = "A structural biology assay for protein folding."
    cooking = make_paper("noise:cooking", title="Cooking announcement")
    cooking.doi = "10.1234/cooking"

    storage.save_preference_prompt(text="Prefer RAG agent evaluation", path=db_path)
    storage.save_preference_prompt(text="Prefer protein folding biology", path=db_path)
    storage.record_preference_query(text="RAG benchmark", path=db_path)
    storage.record_preference_query(text="protein assay", path=db_path)
    storage.apply_library_action(action="favorite", papers=[rag], path=db_path)
    storage.apply_library_action(action="favorite", papers=[protein], path=db_path)
    storage.apply_library_action(action="hide", papers=[cooking], path=db_path)

    profile = storage.get_relevant_preference_profile(query="RAG agent benchmark", paper=rag, path=db_path)

    assert profile["signal_counts"]["matched_prompt_count"] == 1
    assert profile["signal_counts"]["matched_query_count"] == 1
    assert profile["signal_counts"]["matched_event_count"] == 1
    assert profile["profile"]["manual_prompts"] == ["Prefer RAG agent evaluation"]
    assert [item["text"] for item in profile["profile"]["recent_queries"]] == ["RAG benchmark"]
    terms = {item["term"] for item in profile["profile"]["positive_terms"]}
    assert {"rag", "agent", "benchmark"} <= terms
    assert "protein" not in terms
    assert profile["profile"]["negative_terms"] == []


def test_ai_filter_group_signals_are_weak_training_examples(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    recommended = make_paper("arxiv:keep", title="RAG agent benchmark")
    rejected = make_paper("noise:reject", title="Conference admin notice")
    corrected = make_paper("noise:corrected", title="RAG marketing announcement")
    recommended.doi = "10.1234/keep"
    rejected.doi = "10.1234/reject"
    corrected.doi = "10.1234/corrected"

    storage.apply_library_action(
        action="ai_recommend",
        papers=[recommended],
        event_payload={
            "noise_tags": [],
            "quality_score": 88,
            "preference_score": 91,
            "ai_decision": {"display_group": "recommend", "quality_score": 88, "preference_score": 91},
        },
        path=db_path,
    )
    storage.apply_library_action(
        action="ai_reject",
        papers=[rejected],
        event_payload={
            "noise_tags": ["announcement", "low_method_detail"],
            "quality_score": 20,
            "preference_score": 15,
            "ai_decision": {"display_group": "reject", "quality_score": 20, "preference_score": 15},
        },
        path=db_path,
    )
    storage.apply_library_action(
        action="hide",
        papers=[corrected],
        event_payload={
            "source": "daily_card",
            "ai_decision": {"display_group": "recommend", "quality_score": 45, "preference_score": 90},
            "noise_tags": ["marketing"],
            "quality_score": 45,
            "preference_score": 90,
        },
        path=db_path,
    )
    profile = storage.get_preference_profile(path=db_path)
    training = storage.export_preference_training_data(path=db_path)

    assert profile["signal_counts"]["actions"]["ai_recommend"] == 1
    assert profile["signal_counts"]["actions"]["ai_reject"] == 1
    by_id = {item["paper_id"]: item for item in training["examples"]}
    assert by_id["arxiv:keep"]["label"] == "weak_positive"
    assert by_id["arxiv:keep"]["weight"] == 1
    assert by_id["arxiv:keep"]["signal_quality"] == "model_assisted"
    assert by_id["arxiv:keep"]["quality_score"] == 88
    assert by_id["arxiv:keep"]["preference_score"] == 91
    assert by_id["arxiv:keep"]["correction_context"]["model_recommended"] is True
    assert by_id["noise:reject"]["label"] == "weak_negative"
    assert by_id["noise:reject"]["weight"] == -1
    assert by_id["noise:reject"]["noise_tags"] == ["announcement", "low_method_detail"]
    assert by_id["noise:reject"]["quality_score"] == 20
    assert by_id["noise:reject"]["preference_score"] == 15
    assert by_id["noise:reject"]["correction_context"]["model_rejected"] is True
    assert by_id["noise:corrected"]["label"] == "negative"
    assert by_id["noise:corrected"]["correction_context"]["model_recommended"] is True
    assert by_id["noise:corrected"]["correction_context"]["overridden_model_signal"] is True
    assert training["noise_policy"]["metadata_only"] is True
    assert training["noise_policy"]["weak_model_actions"] == ["ai_recommend", "ai_reject"]


def test_preference_learning_can_be_disabled_and_purified(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    paper = make_paper("arxiv:evolve", title="Agent evolution benchmark")
    paper.doi = "10.1234/evolve"

    settings = storage.update_preference_settings(updates={"learning_enabled": False}, path=db_path)
    query = storage.record_preference_query(text="agent evolution", path=db_path)
    favorite = storage.apply_library_action(action="favorite", papers=[paper], path=db_path)
    profile = storage.get_preference_profile(path=db_path)
    with storage.connect(db_path) as connection:
        event_count = connection.execute("SELECT COUNT(*) FROM library_events").fetchone()[0]
        query_count = connection.execute("SELECT COUNT(*) FROM preference_query_history").fetchone()[0]

    assert settings["settings"]["learning_enabled"] is False
    assert query["recorded"] is False
    assert favorite["updated"][0]["favorite"] is True
    assert event_count == 0
    assert query_count == 0
    assert profile["signal_counts"]["learning_enabled"] is False

    storage.update_preference_settings(updates={"learning_enabled": True, "model_signal_learning_enabled": True}, path=db_path)
    storage.apply_library_action(action="ai_recommend", papers=[paper], path=db_path)
    storage.apply_library_action(action="favorite", papers=[paper], path=db_path)
    purified = storage.purify_preference_signals(path=db_path)
    events = storage.list_library_events(path=db_path)

    assert purified["purify"]["removed_overridden_model_events"] >= 0
    assert {event["action"] for event in events} == {"favorite"}


def test_clear_preference_learning_data_preserves_library_state_and_prompts(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    paper = make_paper("arxiv:clear", title="RAG agent benchmark")

    prompt = storage.save_preference_prompt(text="Prefer RAG agents", path=db_path)
    storage.record_preference_query(text="agent benchmark", path=db_path)
    storage.apply_library_action(action="favorite", papers=[paper], path=db_path)
    before = storage.get_preference_profile(path=db_path)
    cleared = storage.clear_preference_learning_data(path=db_path)
    item = storage.list_library_items(state="favorite", path=db_path)[0]

    assert before["signal_counts"]["query_count"] == 1
    assert before["signal_counts"]["actions"]["favorite"] == 1
    assert cleared["cleared"] is True
    assert cleared["removed_queries"] == 1
    assert cleared["removed_events"] == 1
    assert cleared["profile"]["signal_counts"]["query_count"] == 0
    assert cleared["profile"]["signal_counts"]["events_considered"] == 0
    assert cleared["profile"]["signal_counts"]["enabled_prompt_count"] == 1
    assert item["favorite"] is True
    assert storage.list_preference_prompts(path=db_path)[0]["prompt_id"] == prompt["prompt_id"]
    assert storage.list_library_events(path=db_path) == []
    assert storage.list_preference_queries(path=db_path) == []


def test_preference_evaluation_uses_local_events_without_llm(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    positive = make_paper("arxiv:eval-positive", title="RAG agent benchmark")
    positive.doi = "10.1234/eval-positive"
    positive.abstract = "A retrieval augmented generation benchmark with concrete evaluation."
    negative = make_paper("noise:eval-negative", title="Conference announcement")
    negative.doi = "10.1234/eval-negative"
    negative.abstract = "A brief announcement with no method details."

    storage.apply_library_action(action="favorite", papers=[positive], path=db_path)
    storage.apply_library_action(
        action="hide",
        papers=[negative],
        event_payload={"noise_tags": ["announcement", "low_method_detail"]},
        path=db_path,
    )
    evaluation = storage.evaluate_preference_learning(path=db_path)
    storage.clear_preference_learning_data(path=db_path)
    cleared = storage.evaluate_preference_learning(path=db_path)

    assert evaluation["example_count"] == 2
    assert evaluation["positive_count"] == 1
    assert evaluation["negative_count"] == 1
    assert evaluation["precision_at_k"] == 0.5
    assert evaluation["noise_tag_distribution"] == {"announcement": 1, "low_method_detail": 1}
    assert "rag" in {item["term"] for item in evaluation["top_positive_terms"]}
    assert "conference" in {item["term"] for item in evaluation["top_negative_terms"]}
    assert cleared["example_count"] == 0
    assert cleared["precision_at_k"] is None


def test_saved_views_roundtrip(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"

    saved = storage.save_view(
        name="Morning skim",
        filters={"date_from": "2026-04-28", "discipline": "humanities", "hide_read": True},
        path=db_path,
    )
    updated = storage.save_view(
        name="Morning skim",
        filters={"date_from": "2026-04-29", "discipline": "medicine", "sources": ["pubmed"]},
        path=db_path,
    )
    views = storage.list_saved_views(path=db_path)
    deleted = storage.delete_saved_view(name="Morning skim", path=db_path)

    assert saved["view_id"] == updated["view_id"]
    assert views == [updated]
    assert updated["filters"]["discipline"] == "medicine"
    assert deleted is True
    assert storage.list_saved_views(path=db_path) == []
